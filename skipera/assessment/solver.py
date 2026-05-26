import time
import os
import json
from datetime import datetime, timezone

import requests

from .. import config
from .types import QUESTION_TYPE_MAP, MODEL_MAP, deep_blank_model, WHITELISTED_QUESTION_TYPES
from ..config import GRAPHQL_URL, CONFIG_DIR
from .queries import (GET_STATE_QUERY, SAVE_RESPONSES_QUERY, SUBMIT_DRAFT_QUERY,
                      INITIATE_ATTEMPT_QUERY, ASSIGNMENT_FEEDBACK_QUERY)
from loguru import logger
from ..llm.connector import DEFAULT_RESPONSE_SCHEMA, PerplexityConnector, GeminiConnector
from ..session_utils import get_csrf_headers, random_delay


SYSTEM_PROMPT = (
    "Answer the provided questions. Be precise and concise.\n"
    "The questions are in a dict format where each key represents the question id, and the value is a JSON dict containing:\n"
    "- 'Question': the question text (which might have HTML tags, ignore them).\n"
    "- 'Options': a list of options (for MULTIPLE_CHOICE and CHECKBOX types) with option_id and value.\n"
    "- 'Type': one of 'MULTIPLE_CHOICE', 'CHECKBOX', or 'TEXT_REFLECT'.\n"
    "- 'previous_attempts': (optional, only for CHECKBOX) past attempt results.\n\n"
    "Rules for each question type:\n"
    "1. MULTIPLE_CHOICE: Single-choice question. Select exactly one option_id and place it in the 'chosen' list.\n"
    "2. CHECKBOX: Multi-choice question. Select one or more option_ids and place them in the 'chosen' list.\n"
    "3. TEXT_REFLECT: Question with no options. Answer the question prompt thoughtfully and precisely "
    "matching the question content. The response in the 'answer' field must be a high-quality, relevant response directly answering the prompt.\n\n"
    "IMPORTANT for CHECKBOX:\n"
    "If a question has 'previous_attempts', each entry records a prior submission of chosen option_ids:\n"
    "- 'response' is a list of option_ids that were chosen together.\n"
    "- 'hint' states that this combination was graded INCORRECT and shows the fractional score earned (e.g. 'Score: 1/3').\n"
    "Use these partial scores to logically deduce the status of options (e.g., if a combination of size 3 got 2/3 correct, then exactly 2 of those options are correct, and 1 is incorrect). Integrate all attempts to find an untested combination that satisfies these constraints."
)


TYPE_LOOKUP = {
    "MULTIPLE_CHOICE": ("multipleChoiceResponse", "chosen"),
    "CHECKBOX": ("checkboxResponse", "chosen"),
    "TEXT_REFLECT": ("textReflectResponse", "answer")
}


class GradedSolver(object):
    def __init__(self, session: requests.Session, course_id: str, item_id: str):
        self.session: requests.Session = session
        self.course_id: str = course_id
        self.item_id: str = item_id
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
        response_key, val_key = TYPE_LOOKUP[q_type]
        if q_type == "MULTIPLE_CHOICE":
            val = chosen[0] if chosen else None
        elif q_type == "CHECKBOX":
            val = chosen or []
        else:
            val = answer or None
        return {
            "questionId": part_id,
            "questionType": q_type,
            "questionResponse": {
                response_key: {
                    val_key: val
                }
            }
        }

    def solve(self) -> bool:
        # Overwrite minimum passing score
        target_grade = 0.8

        while True:
            state = self.get_state()

            if state.get("outcome") and state["outcome"].get("isPassed") and state["outcome"].get("earnedGrade", 0) >= target_grade:
                logger.success("Already passed with target grade!")
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

                if q_type == "TEXT_REFLECT":
                    if q.get("correct_answer"):
                        answer_responses.append(self._format_response(
                            part_id=part_id,
                            q_type="TEXT_REFLECT",
                            answer=q["correct_answer"]
                        ))
                    else:
                        unsolved_questions[part_id] = {
                            "Question": q["Question"],
                            "Options": [],
                            "Type": "TEXT_REFLECT"
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
                    if len(filtered_options) == 1:
                        answer_responses.append(self._format_response(
                            part_id=part_id,
                            q_type="MULTIPLE_CHOICE",
                            chosen=[filtered_options[0]["option_id"]]
                        ))
                        continue

                    unsolved_questions[part_id] = {
                        "Question": q["Question"],
                        "Options": filtered_options,
                        "Type": "MULTIPLE_CHOICE"
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
                        "Question": question_text,
                        "Options": filtered_options,
                        "Type": "CHECKBOX"
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
                if config.PERPLEXITY_API_KEY:
                    connector = PerplexityConnector()
                elif config.GEMINI_API_KEY:
                    connector = GeminiConnector()
                else:
                    raise RuntimeError("No API Key specified.")

                llm_result = connector.get_response(
                    unsolved_questions, system_prompt=SYSTEM_PROMPT, response_schema=DEFAULT_RESPONSE_SCHEMA)
                for ans in llm_result.get("responses", []):
                    answer_responses.append(self._format_response(
                        part_id=ans["question_id"],
                        q_type=ans["question_type"],
                        chosen=ans.get("chosen"),
                        answer=ans.get("answer")
                    ))
            else:
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
            feedback_result = self.get_feedback()
            if feedback_result:
                outcome = feedback_result["outcome"]
                latest_score = outcome.get("latestScore", 0)
                max_score = outcome.get("maxScore", 1)
                earned_grade = latest_score / max_score if max_score else 0

                self._update_data_from_feedback(
                    feedback_result["parts"], answer_responses)
                self._save_data()

                logger.info(
                    f"Earned grade: {earned_grade:.1%} | Target grade: {target_grade:.1%}"
                )

                if earned_grade >= target_grade:
                    logger.success("Passed!")
                    return True

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
            existing = self.questions_data.get(part_id, {})
            existing_options = existing.get("Options", [])

            existing_correctness = {}
            for opt in existing_options:
                if opt.get("correct") is not None:
                    existing_correctness[opt["value"]] = opt["correct"]

            options = []
            options_schema = question["questionSchema"].get("options") or []
            for option in options_schema:
                val = option["display"]["cmlValue"]
                options.append({
                    "option_id": option["optionId"],
                    "value": val,
                    "correct": existing_correctness.get(val, None)
                })

            questions_formatted[part_id] = {
                "Question": question["questionSchema"]["prompt"]["cmlValue"],
                "Options": options,
                "Type": QUESTION_TYPE_MAP[question["__typename"]][1],
            }

            if "correct_answer" in existing:
                questions_formatted[part_id]["correct_answer"] = existing["correct_answer"]

            if "incorrect_combinations" in existing:
                questions_formatted[part_id]["incorrect_combinations"] = existing["incorrect_combinations"]

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

    def get_feedback(self, max_retries: int = 3) -> dict | None:
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
            response_key, val_key = TYPE_LOOKUP[resp["questionType"]]
            response_lookup[resp["questionId"]] = resp["questionResponse"][response_key][val_key]

        for part in feedback_parts:
            feedback_part_id = part.get("partId", "")
            feedback_key = feedback_part_id.split("~")[-1]

            our_part_id = question_lookup.get(feedback_key)
            if not our_part_id:
                continue

            fb = part.get("feedback", {})
            correctness = fb.get("correctness")
            outcome = fb.get("autoGradedFeedbackOutcome") or {}
            submitted_chosen = response_lookup.get(our_part_id)
            our_q = self.questions_data[our_part_id]

            if our_q.get("correct_answer") or (our_q["Type"] == "MULTIPLE_CHOICE" and any(opt.get("correct") is True for opt in our_q.get("Options", []))) or (our_q["Type"] == "CHECKBOX" and not any(opt.get("correct") is None for opt in our_q.get("Options", []))):
                continue

            all_options = our_q.get("Options", [])
            question_type = our_q["Type"]

            if question_type == "TEXT_REFLECT":
                if correctness == "CORRECT":
                    our_q["correct_answer"] = submitted_chosen
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
