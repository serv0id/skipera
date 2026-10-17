import time
import os
import json
import re
import html
from datetime import datetime, timezone

import httpx

from .. import config
from .types import QUESTION_TYPE_MAP, MODEL_MAP, deep_blank_model, WHITELISTED_QUESTION_TYPES
from ..config import GRAPHQL_URL, CONFIG_DIR
from .queries import (GET_STATE_QUERY, SAVE_RESPONSES_QUERY, SUBMIT_DRAFT_QUERY,
                      INITIATE_ATTEMPT_QUERY, ASSIGNMENT_FEEDBACK_QUERY)
from loguru import logger
from ..llm.connector import DEFAULT_RESPONSE_SCHEMA, PerplexityConnector, GeminiConnector, GroqConnector
from ..session_utils import get_csrf_headers, random_delay


def clean_cml_or_html(text: str) -> str:
    """Helper to convert Coursera CML or HTML markup into clean readable plain text."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r'</?(?:p|div|li|tr)[^>]*>', '\n', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


SYSTEM_PROMPT = (
    "Answer the provided questions. Be precise and concise.\n"
    "The input contains questions to solve. If a previous attempt scored below the required passing grade, "
    "it includes 'wrong_answers_review_page' with the feedback review page showing the incorrect answers and grader explanations from Coursera.\n"
    "Each question is a JSON dict containing:\n"
    "- 'Question': the question text.\n"
    "- 'Options': a list of options (for MULTIPLE_CHOICE and CHECKBOX types) with option_id and value.\n"
    "- 'Type': one of 'MULTIPLE_CHOICE', 'CHECKBOX', 'NUMERIC', 'MATH', 'TEXT_EXACT_MATCH', 'REGEX', 'TEXT_REFLECT', 'RICH_TEXT', or 'PLAIN_TEXT'.\n"
    "- 'previous_attempt': (optional) information on what was submitted in the previous attempt, whether it was INCORRECT, and grader feedback.\n"
    "- 'previous_attempts': (optional, for CHECKBOX) past attempt results with partial scores.\n\n"
    "Rules for each question type:\n"
    "1. MULTIPLE_CHOICE: Single-choice question. Select exactly one option_id and place it in the 'chosen' list. (CRITICAL: You MUST use the exact 'option_id' hash string, do NOT use indices like '1' or '2'!).\n"
    "2. CHECKBOX: Multi-choice question. Select one or more option_ids and place them in the 'chosen' list. (CRITICAL: You MUST use the exact 'option_id' hash strings!).\n"
    "3. NUMERIC: Calculation/numerical question with no options. Compute the exact value requested and place the number as a string in the 'answer' field (e.g., '3', '0.5', '-1.25'). Pay attention to instructions like 'without the $ symbol', decimals, rounding, or percentage vs proportion.\n"
    "4. MATH: Mathematical formula or exact fraction/symbolic question with no options. Provide the simplified fraction, expression, or exact number as requested in the 'answer' field (e.g., '5/8', '0.6', 'x^2'). Follow prompt instructions strictly (e.g., 'simplified fraction').\n"
    "5. TEXT_EXACT_MATCH, REGEX: Fill-in-the-blank or exact keyword question. Provide the exact required word, phrase, or pattern in the 'answer' field.\n"
    "6. TEXT_REFLECT, RICH_TEXT, PLAIN_TEXT: Open-ended written response questions with no options. Answer the question prompt thoroughly, thoughtfully, and precisely matching all requirements and guidelines specified in the prompt. Place your response in the 'answer' field.\n\n"
    "CRITICAL CORRECTION INSTRUCTIONS:\n"
    "When 'wrong_answers_review_page' or 'previous_attempt' is provided, the previous submission was graded below the target grade.\n"
    "Carefully review the wrong answers and grader feedback! Do NOT repeat known incorrect answers or rejected options. Use the feedback explanations to calculate/select the correct answer for each question."
)


TYPE_LOOKUP = {
    "MULTIPLE_CHOICE": ("multipleChoiceResponse", "chosen"),
    "CHECKBOX": ("checkboxResponse", "chosen"),
    "TEXT_REFLECT": ("textReflectResponse", "answer"),
    "PLAIN_TEXT": ("plainTextResponse", "plainText"),
    "RICH_TEXT": ("richTextResponse", "richText"),
    "NUMERIC": ("numericResponse", "answer"),
    "MATH": ("mathResponse", "answer"),
    "TEXT_EXACT_MATCH": ("textExactMatchResponse", "answer"),
    "REGEX": ("regexResponse", "answer"),
}

OPEN_ENDED_OR_VALUE_TYPES = {
    "TEXT_REFLECT", "RICH_TEXT", "PLAIN_TEXT",
    "NUMERIC", "MATH", "TEXT_EXACT_MATCH", "REGEX"
}


class GradedSolver(object):
    def __init__(self, session: httpx.Client, course_id: str, item_id: str, slug: str | None = None):
        self.session: httpx.Client = session
        self.course_id: str = course_id
        self.item_id: str = item_id
        self.slug: str | None = slug
        self.attempt_id = None
        self.draft_id = None
        self.discarded_questions = []

        self.data_dir = CONFIG_DIR / "gradedData"
        os.makedirs(self.data_dir, exist_ok=True)

        self.data_file = os.path.join(
            self.data_dir, f"{course_id}~{item_id}.json")
        self.questions_data: dict = self._load_data()

    def _load_data(self) -> dict:
        if os.path.exists(self.data_file):
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_data(self) -> None:
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self.questions_data, f, ensure_ascii=False, indent=4)

    def _get_response_text(self, options: list[dict], response: str | list[str]) -> str | list[str]:
        if isinstance(response, list):
            return [opt["value"] for opt in options if opt["option_id"] in response]
        else:
            for opt in options:
                if opt["option_id"] == response:
                    return opt["value"]
            return response

    def _format_response(self, part_id: str, q_type: str, chosen: list = None, answer: str = None) -> dict:
        if chosen and isinstance(chosen, str):
            chosen = [chosen]
            
        if q_type == "MULTIPLE_CHOICE":
            val = chosen[0] if chosen else None
            return {
                "questionId": part_id,
                "questionType": q_type,
                "questionResponse": {
                    "multipleChoiceResponse": {
                        "chosen": val
                    }
                }
            }
        elif q_type == "CHECKBOX":
            val = chosen or []
            return {
                "questionId": part_id,
                "questionType": q_type,
                "questionResponse": {
                    "checkboxResponse": {
                        "chosen": val
                    }
                }
            }
        elif q_type == "RICH_TEXT":
            val = answer or ""
            if not val.strip().startswith("<"):
                paragraphs = "".join(f"<p>{p.strip()}</p>" for p in val.split("\n\n") if p.strip())
                val = paragraphs or f"<p>{val}</p>"
            return {
                "questionId": part_id,
                "questionType": "RICH_TEXT",
                "questionResponse": {
                    "richTextResponse": {
                        "richText": {
                            "html": {
                                "value": val
                            }
                        }
                    }
                }
            }
        elif q_type == "PLAIN_TEXT":
            val = answer or ""
            return {
                "questionId": part_id,
                "questionType": "PLAIN_TEXT",
                "questionResponse": {
                    "plainTextResponse": {
                        "plainText": val
                    }
                }
            }
        elif q_type == "TEXT_REFLECT":
            val = answer or ""
            return {
                "questionId": part_id,
                "questionType": "TEXT_REFLECT",
                "questionResponse": {
                    "textReflectResponse": {
                        "answer": val
                    }
                }
            }
        elif q_type in {"NUMERIC", "MATH", "TEXT_EXACT_MATCH", "REGEX"}:
            if answer is not None:
                val = str(answer).strip()
            elif chosen and len(chosen) > 0 and chosen[0] is not None:
                val = str(chosen[0]).strip()
            else:
                val = ""
            response_key, val_key = TYPE_LOOKUP[q_type]
            return {
                "questionId": part_id,
                "questionType": q_type,
                "questionResponse": {
                    response_key: {
                        val_key: val
                    }
                }
            }
        else:
            response_key, val_key = TYPE_LOOKUP.get(q_type, (f"{q_type.lower()}Response", "answer"))
            val = answer if answer is not None else (chosen[0] if chosen else "")
            return {
                "questionId": part_id,
                "questionType": q_type,
                "questionResponse": {
                    response_key: {
                        val_key: str(val).strip() if val is not None else ""
                    }
                }
            }

    def build_wrong_answers_page(self, feedback_data: dict, submitted_responses: list, earned_grade: float, target_grade: float) -> str:
        """
        Builds a comprehensive review page detailing all questions that were answered incorrectly,
        the submitted answers, and the grader feedback/explanations from Coursera.
        """
        outcome = feedback_data.get("outcome") or {}
        latest_score = outcome.get("latestScore", 0)
        max_score = outcome.get("maxScore", 1)
        parts = feedback_data.get("parts", [])

        response_lookup = {}
        for resp in submitted_responses:
            q_type = resp["questionType"]
            if q_type == "RICH_TEXT":
                try:
                    response_lookup[resp["questionId"]] = resp["questionResponse"]["richTextResponse"]["richText"]["html"]["value"]
                except (KeyError, TypeError):
                    response_lookup[resp["questionId"]] = ""
            elif q_type == "PLAIN_TEXT":
                try:
                    response_lookup[resp["questionId"]] = resp["questionResponse"]["plainTextResponse"]["plainText"]
                except (KeyError, TypeError):
                    response_lookup[resp["questionId"]] = ""
            else:
                response_key, val_key = TYPE_LOOKUP.get(q_type, ("", ""))
                if response_key and val_key:
                    try:
                        response_lookup[resp["questionId"]] = resp["questionResponse"][response_key][val_key]
                    except (KeyError, TypeError):
                        pass

        lines = [
            "=" * 70,
            "COURSERA ASSESSMENT FEEDBACK & WRONG ANSWERS REVIEW PAGE",
            "=" * 70,
            f"Score Earned  : {latest_score} / {max_score} ({earned_grade:.1%})",
            f"Target Grade  : {target_grade:.1%}",
            f"Result        : BELOW TARGET GRADE - CORRECTION REQUIRED",
        ]
        if self.slug and self.item_id:
            lines.append(f"Review URL    : https://www.coursera.org/learn/{self.slug}/exam/{self.item_id}/feedback")
        lines.append("-" * 70)
        lines.append("The following questions were answered INCORRECTLY in the previous attempt.")
        lines.append("Read the Grader Feedback and explanations carefully to correct each answer:")
        lines.append("-" * 70)

        wrong_count = 0
        for idx, part in enumerate(parts, start=1):
            fb = part.get("feedback") or {}
            correctness = fb.get("correctness")
            outcome_part = fb.get("autoGradedFeedbackOutcome") or {}
            part_score = outcome_part.get("score", 0)
            part_max = outcome_part.get("maxScore", 1)

            is_wrong = correctness in {"INCORRECT", "PARTIALLY_CORRECT"} or (part_score is not None and part_max is not None and part_score < part_max)
            if not is_wrong:
                continue

            wrong_count += 1
            schema = part.get("questionSchema") or {}
            prompt = clean_cml_or_html(schema.get("prompt", {}).get("cmlValue") or schema.get("prompt", {}).get("htmlWithMetadata", {}).get("html", ""))

            options = []
            for opt in schema.get("options") or []:
                val = clean_cml_or_html(opt.get("display", {}).get("cmlValue") or opt.get("display", {}).get("htmlWithMetadata", {}).get("html", ""))
                options.append({"id": opt.get("optionId"), "value": val})

            feedback_part_id = part.get("partId", "")
            feedback_key = feedback_part_id.split("~")[-1]

            submitted_str = ""
            chosen_ids = set()
            if "multipleChoiceResponse" in part and part["multipleChoiceResponse"]:
                cid = part["multipleChoiceResponse"].get("chosen")
                if cid:
                    chosen_ids.add(cid)
                    cval = next((o["value"] for o in options if o["id"] == cid), cid)
                    submitted_str = f'"{cval}" (option_id: {cid})'
            elif "checkboxResponse" in part and part["checkboxResponse"]:
                cids = part["checkboxResponse"].get("chosen") or []
                chosen_strs = []
                for cid in cids:
                    chosen_ids.add(cid)
                    cval = next((o["value"] for o in options if o["id"] == cid), cid)
                    chosen_strs.append(f'"{cval}" (option_id: {cid})')
                submitted_str = ", ".join(chosen_strs)
            elif "numericResponse" in part and part["numericResponse"]:
                submitted_str = str(part["numericResponse"].get("answer", "") or "")
            elif "mathResponse" in part and part["mathResponse"]:
                submitted_str = str(part["mathResponse"].get("answer", "") or "")
            elif "textExactMatchResponse" in part and part["textExactMatchResponse"]:
                submitted_str = str(part["textExactMatchResponse"].get("answer", "") or "")
            elif "regexResponse" in part and part["regexResponse"]:
                submitted_str = str(part["regexResponse"].get("answer", "") or "")
            elif "plainTextResponse" in part and part["plainTextResponse"]:
                submitted_str = part["plainTextResponse"].get("plainText", "")
            elif "richTextResponse" in part and part["richTextResponse"]:
                submitted_str = clean_cml_or_html(part["richTextResponse"].get("richText", {}).get("html", {}).get("value", ""))

            if not submitted_str:
                for k, v in response_lookup.items():
                    if k.split("~")[-1] == feedback_key:
                        if isinstance(v, list):
                            chosen_strs = []
                            for cid in v:
                                chosen_ids.add(cid)
                                cval = next((o["value"] for o in options if o["id"] == cid), cid)
                                chosen_strs.append(f'"{cval}" (option_id: {cid})')
                            submitted_str = ", ".join(chosen_strs)
                        elif isinstance(v, str) and options:
                            chosen_ids.add(v)
                            cval = next((o["value"] for o in options if o["id"] == v), v)
                            submitted_str = f'"{cval}" (option_id: {v})'
                        else:
                            submitted_str = str(v)
                        break

            if not submitted_str:
                submitted_str = "(None or Blank)"

            grader_fb = clean_cml_or_html(fb.get("feedback", {}).get("cmlValue") or fb.get("feedback", {}).get("htmlWithMetadata", {}).get("html", ""))

            lines.append(f"\n[QUESTION {idx}] (Score: {part_score}/{part_max}) - {correctness or 'INCORRECT'}")
            lines.append(f"Prompt: {prompt}")
            lines.append(f"Your Previous Submitted Answer: {submitted_str}")
            if grader_fb:
                lines.append(f"Grader Feedback / Explanation: {grader_fb}")

            if options:
                lines.append("Options Available:")
                for opt in options:
                    flag = " [FAILED IN PREVIOUS ATTEMPT - INCORRECT]" if opt["id"] in chosen_ids else ""
                    lines.append(f"  - (option_id: {opt['id']}) {opt['value']}{flag}")
            lines.append("-" * 70)

        lines.append(f"\nTotal Incorrect Questions: {wrong_count}")
        lines.append("=" * 70)
        return "\n".join(lines)

    def solve(self) -> bool:
        # Overwrite minimum passing score
        target_grade = 0.8
        wrong_answers_page = None
        page_file = self.data_dir / f"{self.course_id}~{self.item_id}_wrong_answers.txt"
        if page_file.exists():
            try:
                wrong_answers_page = page_file.read_text(encoding="utf-8")
            except Exception:
                pass

        while True:
            state = self.get_state()

            if state.get("outcome") and state["outcome"].get("isPassed"):
                logger.success("Already passed!")
                return True

            allowed = state["allowedAction"]

            if allowed == "START_NEW_ATTEMPT":
                if not self.initiate_attempt():
                    logger.error(
                        "Could not start an attempt. Please file an issue.")
                    return False
                continue

            elif allowed == "RESUME_DRAFT":
                logger.info("Resuming existing draft.")

            elif allowed is None:
                rate_limiter = state.get("attempts", {}).get("rateLimiterConfig") or {}
                increase_at = rate_limiter.get("attemptsRemainingIncreasesAt")
                retry_msg = ""
                if increase_at:
                    try:
                        dt_target = datetime.fromisoformat(increase_at.replace("Z", "+00:00"))
                        dt_now = datetime.now(timezone.utc)
                        delta = dt_target - dt_now
                        if delta.total_seconds() > 0:
                            hours = delta.days * 24 + delta.seconds // 3600
                            minutes = (delta.seconds % 3600) // 60
                            time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                            retry_msg = f" (Retry in {time_str})"
                        else:
                            retry_msg = " (Retry available now)"
                    except Exception:
                        retry_msg = f" (Retry from {increase_at})"

                if state.get("outcome") and state["outcome"].get("isPassed"):
                    logger.warning(f"Passed, but below target grade.{retry_msg}")
                    return True
                else:
                    logger.warning(f"No more attempts remaining!{retry_msg}")
                    return False

            else:
                logger.error(f"Unexpected allowedAction: {allowed}")
                return False

            self.discarded_questions = []
            questions = self.retrieve_questions(state)
            self._save_data()
            unsolved_questions = {}
            answer_responses = []

            for part_id, q in questions.items():
                q_type = q["Type"]
                options = q.get("Options", [])
                latest_fb = q.get("latest_feedback", {})

                if q_type in OPEN_ENDED_OR_VALUE_TYPES:
                    if q.get("correct_answer"):
                        answer_responses.append(self._format_response(
                            part_id=part_id,
                            q_type=q_type,
                            answer=q["correct_answer"]
                        ))
                    else:
                        unsolved_questions[part_id] = {
                            "question_id": part_id,
                            "Question": q["Question"],
                            "Options": [],
                            "Type": q_type
                        }
                        if latest_fb and latest_fb.get("correctness") != "CORRECT":
                            unsolved_questions[part_id]["previous_attempt"] = {
                                "status": latest_fb.get("correctness") or "INCORRECT",
                                "score": f"{latest_fb.get('score', 0)}/{latest_fb.get('max_score', 1)}",
                                "submitted_answer": latest_fb.get("submitted_chosen"),
                                "grader_feedback": latest_fb.get("feedback_text")
                            }
                elif q_type == "MULTIPLE_CHOICE":
                    known_correct_id = next((opt["option_id"] for opt in options if opt.get("correct") is True), None)
                    if known_correct_id:
                        answer_responses.append(self._format_response(
                            part_id=part_id,
                            q_type="MULTIPLE_CHOICE",
                            chosen=[known_correct_id]
                        ))
                        continue

                    filtered_options = [opt for opt in options if opt.get("correct") is not False]
                    if not filtered_options:
                        filtered_options = options

                    if len(filtered_options) == 1:
                        answer_responses.append(self._format_response(
                            part_id=part_id,
                            q_type="MULTIPLE_CHOICE",
                            chosen=[filtered_options[0]["option_id"]]
                        ))
                        continue

                    unsolved_questions[part_id] = {
                        "question_id": part_id,
                        "Question": q["Question"],
                        "Options": filtered_options,
                        "Type": "MULTIPLE_CHOICE"
                    }
                    if latest_fb and latest_fb.get("correctness") != "CORRECT":
                        submitted_id = latest_fb.get("submitted_chosen")
                        submitted_text = self._get_response_text(options, submitted_id) if submitted_id else None
                        unsolved_questions[part_id]["previous_attempt"] = {
                            "status": latest_fb.get("correctness") or "INCORRECT",
                            "score": f"{latest_fb.get('score', 0)}/{latest_fb.get('max_score', 1)}",
                            "submitted_option_id": submitted_id,
                            "submitted_option_text": submitted_text,
                            "grader_feedback": latest_fb.get("feedback_text")
                        }
                elif q_type == "CHECKBOX":
                    all_resolved = all(opt.get("correct") is not None for opt in options)
                    if all_resolved:
                        known_correct_checkbox_ids = [opt["option_id"] for opt in options if opt.get("correct") is True]
                        answer_responses.append(self._format_response(
                            part_id=part_id,
                            q_type="CHECKBOX",
                            chosen=known_correct_checkbox_ids
                        ))
                        continue

                    filtered_options = [opt for opt in options if opt.get("correct") is not False]
                    known_correct_vals = [opt["value"] for opt in filtered_options if opt.get("correct") is True]
                    question_text = q["Question"]
                    if known_correct_vals:
                        question_text += "\n\n(IMPORTANT NOTE: The following options are already known to be CORRECT and MUST be included in your chosen list:\n"
                        for val in known_correct_vals:
                            question_text += f"- {val}\n"
                        question_text += ")"

                    unsolved_questions[part_id] = {
                        "question_id": part_id,
                        "Question": question_text,
                        "Options": filtered_options,
                        "Type": "CHECKBOX"
                    }
                    if latest_fb and latest_fb.get("correctness") != "CORRECT":
                        submitted_ids = latest_fb.get("submitted_chosen") or []
                        submitted_texts = self._get_response_text(options, submitted_ids) if submitted_ids else []
                        unsolved_questions[part_id]["previous_attempt"] = {
                            "status": latest_fb.get("correctness") or "INCORRECT",
                            "score": f"{latest_fb.get('score', 0)}/{latest_fb.get('max_score', 1)}",
                            "submitted_options": submitted_texts,
                            "grader_feedback": latest_fb.get("feedback_text")
                        }

                    incorrect_combs = q.get("incorrect_combinations", [])
                    if incorrect_combs:
                        virtual_feedbacks = []
                        for comb_entry in incorrect_combs:
                            comb = comb_entry["combination"]
                            score_info = f" (Score: {comb_entry.get('score')}/{comb_entry.get('max_score')})"
                            chosen_ids = [opt["option_id"] for opt in filtered_options if opt["value"] in comb]
                            if chosen_ids:
                                virtual_feedbacks.append({
                                    "response": chosen_ids,
                                    "correctness": "INCORRECT",
                                    "hint": f"This combination of options was submitted and graded INCORRECT{score_info}."
                                })
                        if virtual_feedbacks:
                            unsolved_questions[part_id]["previous_attempts"] = virtual_feedbacks

            if unsolved_questions:
                if wrong_answers_page:
                    logger.info("Grade was below target — sending wrong answers feedback page to LLM for correction.")
                    llm_prompt = {
                        "wrong_answers_review_page": wrong_answers_page,
                        "questions_to_solve": unsolved_questions
                    }
                    current_system_prompt = SYSTEM_PROMPT + (
                        "\n\n=======================================================\n"
                        "CRITICAL NOTICE: PREVIOUS ATTEMPT SCORED BELOW TARGET GRADE!\n"
                        "The Coursera feedback review page showing the WRONG ANSWERS and grader explanations is provided in 'wrong_answers_review_page'.\n"
                        "Carefully analyze each wrong answer and its grader feedback. Fix every error and select the correct answer for each question!\n"
                        "======================================================="
                    )
                else:
                    llm_prompt = unsolved_questions
                    current_system_prompt = SYSTEM_PROMPT

                llm_result = None
                if config.PERPLEXITY_API_KEY:
                    connector = PerplexityConnector()
                elif config.GEMINI_API_KEY:
                    connector = GeminiConnector()
                elif getattr(config, "GROQ_API_KEYS", []):
                    # Try each Groq API key until one works
                    for key in config.GROQ_API_KEYS:
                        connector = GroqConnector(api_key=key)
                        try:
                            llm_result = connector.get_response(
                                llm_prompt,
                                system_prompt=current_system_prompt,
                                response_schema=DEFAULT_RESPONSE_SCHEMA,
                            )
                            break  # success
                        except Exception as e:
                            logger.warning(f"Groq key failed ({key[:4]}...): {e}")
                    else:
                        raise RuntimeError("All Groq API keys exhausted.")
                elif config.GROQ_API_KEY:
                    connector = GroqConnector()
                else:
                    raise RuntimeError("No API Key specified.")
                # If we haven't obtained llm_result yet (i.e., using Perplexity or Gemini), fetch it now
                if llm_result is None:
                    llm_result = connector.get_response(
                        llm_prompt,
                        system_prompt=current_system_prompt,
                        response_schema=DEFAULT_RESPONSE_SCHEMA,
                    )
                for ans in llm_result.get("responses", []):
                    q_id = ans.get("question_id")
                    q_info = unsolved_questions.get(q_id)
                    if not q_info:
                        continue
                    answer_responses.append(
                        self._format_response(
                            part_id=q_id,
                            q_type=q_info["Type"],
                            chosen=ans.get("chosen"),
                            answer=ans.get("answer"),
                        )
                    )
            else:
                if wrong_answers_page is not None:
                    logger.warning(
                        "No more unsolved questions to improve, but earned grade is below target. Stopping to avoid draining attempts."
                    )
                    return False
                logger.info(
                    "All questions already correct — resubmitting same answers.")

            if not self.save_responses(answer_responses):
                logger.error("Could not save responses. Please file an issue.")
                return False
            if not self.submit_draft():
                logger.error(
                    "Could not submit the assignment. Please file an issue.")
                return False

            time.sleep(5.0)
            feedback_result = self.get_feedback(max_retries=8)
            if feedback_result:
                outcome = feedback_result.get("outcome") or {}
                latest_score = outcome.get("latestScore", 0)
                max_score = outcome.get("maxScore", 1)
                earned_grade = latest_score / max_score if max_score else 0

                self._update_data_from_feedback(
                    feedback_result.get("parts", []), answer_responses)
                self._save_data()

                logger.info(
                    f"Earned grade: {earned_grade:.1%} | Target grade: {target_grade:.1%}"
                )

                if outcome.get("isPassed") or earned_grade >= target_grade:
                    if page_file.exists():
                        try:
                            page_file.unlink()
                        except Exception:
                            pass
                    logger.success("Passed!")
                    return True
                else:
                    logger.warning(
                        f"Earned grade {earned_grade:.1%} is lower than target grade {target_grade:.1%}. Building wrong answers feedback page..."
                    )
                    wrong_answers_page = self.build_wrong_answers_page(
                        feedback_result, answer_responses, earned_grade, target_grade
                    )
                    try:
                        page_file = self.data_dir / f"{self.course_id}~{self.item_id}_wrong_answers.txt"
                        page_file.write_text(wrong_answers_page, encoding="utf-8")
                        with open("wrong_answers.txt", "w", encoding="utf-8") as f:
                            f.write(wrong_answers_page)
                    except Exception as e:
                        logger.debug(f"Could not save wrong_answers.txt: {e}")

            random_delay()

    def get_state(self) -> dict:
        """
        Retrieves the current state of the assessment.
        """
        res = self.session.post(url=GRAPHQL_URL, headers=get_csrf_headers(self.session), params={
            "opname": "QueryState"
        }, json={
            "operationName": "QueryState",
            "variables": {
                "courseId": self.course_id,
                "itemId": self.item_id
            },
            "query": GET_STATE_QUERY
        }).json()

        return res["data"]["SubmissionState"]["queryState"]

    def initiate_attempt(self) -> bool:
        """
        Initiates a new attempt for the assessment.
        """
        res = self.session.post(url=GRAPHQL_URL, headers=get_csrf_headers(self.session), params={
            "opname": "Submission_StartAttempt"
        }, json={
            "operationName": "Submission_StartAttempt",
            "variables": {
                "courseId": self.course_id,
                "itemId": self.item_id
            },
            "query": INITIATE_ATTEMPT_QUERY
        })

        return "Submission_StartAttemptSuccess" in res.text

    def retrieve_questions(self, state: dict) -> dict:
        """
        Retrieves the questions from the in-progress draft and merges
        with persisted data. Returns the whitelisted questions dict.
        """
        draft = state["attempts"]["inProgressAttempt"]

        self.attempt_id = draft["id"]
        self.draft_id = draft["draft"]["id"]
        questions = draft["draft"]["parts"]
        questions_formatted = {}

        for question in questions:
            # discard unknown question types
            if not question["__typename"] in QUESTION_TYPE_MAP:
                continue

            if not question["__typename"] in WHITELISTED_QUESTION_TYPES:
                self.discarded_questions.append({
                    "questionId": question["partId"],
                    "questionType": QUESTION_TYPE_MAP[question["__typename"]][1],
                    "questionResponse": {
                        QUESTION_TYPE_MAP[question["__typename"]][0]:
                        deep_blank_model(MODEL_MAP[question["__typename"]])
                    }
                })
                continue

            part_id = question["partId"]
            q_key = part_id.split("~")[-1]
            existing = self.questions_data.get(part_id)
            if not existing:
                for k, v in self.questions_data.items():
                    if k.split("~")[-1] == q_key:
                        existing = v
                        break
            if not existing:
                existing = {}

            existing_options = existing.get("Options", [])

            existing_correctness = {}
            for opt in existing_options:
                if opt.get("correct") is not None:
                    existing_correctness[opt["value"]] = opt["correct"]

            options = []
            options_schema = question.get("questionSchema", {}).get("options") or []
            for option in options_schema:
                val = option.get("display", {}).get("cmlValue") or option.get("display", {}).get("htmlWithMetadata", {}).get("html", "")
                options.append({
                    "option_id": option.get("optionId", ""),
                    "value": val,
                    "correct": existing_correctness.get(val, None)
                })

            prompt_obj = question.get("questionSchema", {}).get("prompt", {})
            prompt_text = prompt_obj.get("cmlValue") or prompt_obj.get("htmlWithMetadata", {}).get("html", "")

            questions_formatted[part_id] = {
                "Question": prompt_text,
                "Options": options,
                "Type": QUESTION_TYPE_MAP[question["__typename"]][1],
            }

            if "correct_answer" in existing:
                questions_formatted[part_id]["correct_answer"] = existing["correct_answer"]

            if "incorrect_combinations" in existing:
                questions_formatted[part_id]["incorrect_combinations"] = existing["incorrect_combinations"]

            if "latest_feedback" in existing:
                questions_formatted[part_id]["latest_feedback"] = existing["latest_feedback"]

        self.questions_data.update(questions_formatted)

        return questions_formatted

    def save_responses(self, answer_responses: list) -> bool:
        """
        Saves the responses for the assessment to the draft.
        """
        res = self.session.post(url=GRAPHQL_URL, headers=get_csrf_headers(self.session), params={
            "opname": "Submission_SaveResponses"
        }, json={
            "operationName": "Submission_SaveResponses",
            "variables": {
                "input": {
                    "courseId": self.course_id,
                    "itemId": self.item_id,
                    "attemptId": self.attempt_id,
                    "questionResponses": [*answer_responses, *self.discarded_questions]
                }
            },
            "query": SAVE_RESPONSES_QUERY
        })

        if "Submission_SaveResponsesSuccess" in res.text:
            try:
                data = res.json()
                self.draft_id = (data["data"]["Submission_SaveResponses"]
                                 ["submissionState"]["attempts"]
                                 ["inProgressAttempt"]["draft"]["id"])
            except (KeyError, TypeError):
                pass
            return True

        logger.debug([*answer_responses, *self.discarded_questions])
        logger.debug(res.json())
        return False

    def submit_draft(self) -> bool:
        """
        Submits the draft for evaluation after the submission is saved.
        """
        res = self.session.post(url=GRAPHQL_URL, headers=get_csrf_headers(self.session), params={
            "opname": "Submission_SubmitLatestDraft"
        }, json={
            "operationName": "Submission_SubmitLatestDraft",
            "query": SUBMIT_DRAFT_QUERY,
            "variables": {
                "input": {
                    "courseId": self.course_id,
                    "itemId": self.item_id,
                    "submissionId": self.draft_id
                }
            }
        })

        return "Submission_SubmitLatestDraftSuccess" in res.text

    def get_feedback(self, max_retries: int = 8) -> dict | None:
        """
        Fetches AssignmentFeedback for per-question correctness.
        """
        for i in range(max_retries):
            res = self.session.post(url=GRAPHQL_URL, headers=get_csrf_headers(self.session), params={
                "opname": "AssignmentFeedback"
            }, json={
                "operationName": "AssignmentFeedback",
                "variables": {
                    "courseId": self.course_id,
                    "itemId": self.item_id
                },
                "query": ASSIGNMENT_FEEDBACK_QUERY
            }).json()

            try:
                feedback = res["data"]["SubmissionState"]["queryState"]["feedback"]
            except (KeyError, TypeError):
                logger.debug(f"Unexpected feedback response: {res}")
                return None

            if feedback is not None:
                parts = feedback.get("parts")
                if parts is not None and all(part.get("feedback") is not None for part in parts):
                    return feedback

            logger.warning(
                f"Feedback not ready yet (attempt {i + 1}/{max_retries})")
            time.sleep(3.0)
            random_delay()

        logger.warning("Feedback did not become available in time.")
        return None

    def _update_data_from_feedback(self, feedback_parts: list,
                                   submitted_responses: list) -> None:
        """
        Update resolved options, correct answers, and incorrect combinations.
        """
        question_lookup = {}
        for part_id in self.questions_data:
            key = part_id.split("~")[-1]
            question_lookup[key] = part_id

        response_lookup = {}
        for resp in submitted_responses:
            q_type = resp["questionType"]
            if q_type == "RICH_TEXT":
                try:
                    response_lookup[resp["questionId"]] = resp["questionResponse"]["richTextResponse"]["richText"]["html"]["value"]
                except (KeyError, TypeError):
                    response_lookup[resp["questionId"]] = ""
            elif q_type == "PLAIN_TEXT":
                try:
                    response_lookup[resp["questionId"]] = resp["questionResponse"]["plainTextResponse"]["plainText"]
                except (KeyError, TypeError):
                    response_lookup[resp["questionId"]] = ""
            else:
                response_key, val_key = TYPE_LOOKUP.get(q_type, ("", ""))
                if response_key and val_key:
                    response_lookup[resp["questionId"]] = resp["questionResponse"][response_key][val_key]

        for part in feedback_parts:
            feedback_part_id = part.get("partId", "")
            feedback_key = feedback_part_id.split("~")[-1]

            our_part_id = question_lookup.get(feedback_key)
            if not our_part_id:
                for k in self.questions_data:
                    if k.split("~")[-1] == feedback_key:
                        our_part_id = k
                        break
            if not our_part_id:
                continue

            fb = part.get("feedback", {})
            correctness = fb.get("correctness")
            outcome = fb.get("autoGradedFeedbackOutcome") or {}
            submitted_chosen = response_lookup.get(our_part_id)
            our_q = self.questions_data[our_part_id]

            grader_fb = clean_cml_or_html(fb.get("feedback", {}).get("cmlValue") or fb.get("feedback", {}).get("htmlWithMetadata", {}).get("html", ""))
            our_q["latest_feedback"] = {
                "correctness": correctness,
                "score": outcome.get("score"),
                "max_score": outcome.get("maxScore"),
                "feedback_text": grader_fb,
                "submitted_chosen": submitted_chosen,
            }

            if our_q.get("correct_answer") or (our_q["Type"] == "MULTIPLE_CHOICE" and any(opt.get("correct") is True for opt in our_q.get("Options", []))) or (our_q["Type"] == "CHECKBOX" and not any(opt.get("correct") is None for opt in our_q.get("Options", []))):
                continue

            all_options = our_q.get("Options", [])
            question_type = our_q["Type"]

            if question_type in OPEN_ENDED_OR_VALUE_TYPES:
                if correctness == "CORRECT" or (not correctness and (outcome.get("score") == outcome.get("maxScore") and outcome.get("maxScore", 0) > 0)):
                    our_q["correct_answer"] = submitted_chosen
                else:
                    our_q["correct_answer"] = None
                continue

            is_single = question_type == "MULTIPLE_CHOICE"

            chosen_texts = set()
            if submitted_chosen:
                texts = self._get_response_text(all_options, submitted_chosen)
                chosen_texts = {texts} if isinstance(texts, str) else set(texts)

            schema_options = (part.get("questionSchema") or {}).get("options") or []
            if schema_options:
                for opt in schema_options:
                    val = opt["display"].get("cmlValue")
                    if not val:
                        continue
                    for our_opt in all_options:
                        if our_opt["value"] == val:
                            if "correctlyAnswered" in opt:
                                our_opt["correct"] = opt["correctlyAnswered"] == (val in chosen_texts)

            if correctness == "CORRECT":
                for our_opt in all_options:
                    our_opt["correct"] = our_opt["value"] in chosen_texts
            elif correctness == "INCORRECT":
                if is_single and chosen_texts:
                    chosen_text = next(iter(chosen_texts))
                    for our_opt in all_options:
                        if our_opt["value"] == chosen_text:
                            our_opt["correct"] = False
                            break
                elif not is_single and chosen_texts:
                    our_q.setdefault("incorrect_combinations", [])
                    comb = sorted(list(chosen_texts))
                    
                    if not any(existing_comb["combination"] == comb for existing_comb in our_q["incorrect_combinations"]):
                        our_q["incorrect_combinations"].append({
                            "combination": comb,
                            "score": outcome.get("score"),
                            "max_score": outcome.get("maxScore")
                        })
