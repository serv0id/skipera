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
from ..llm.connector import DEFAULT_RESPONSE_SCHEMA, TEXT_RESPONSE_SCHEMA, PerplexityConnector, GeminiConnector, DeepSeekConnector
from ..session_utils import get_csrf_headers, random_delay


SYSTEM_PROMPT_FOR_CHOICE = (
    "Answer the provided questions. Be precise and concise. "
    "The questions are in a dict format with the key representing the question id "
    "and the value a JSON dict containing the question, options, type, "
    "and optionally 'previous_attempts'. "
    "Questions may have single-choice or multiple-choice answers, "
    "which would be specified by the 'Type' field. "
    "The question/option values might have HTML data but ignore that. "
    "IMPORTANT: If a question has 'previous_attempts', each entry records a per-option "
    "grader result from prior submissions, with 'response' (the option_id(s)) and "
    "'correctness' (CORRECT or INCORRECT). "
    "For options marked INCORRECT: never choose them again. "
    "For options marked CORRECT: you MUST include them in your answer (for Multi-Choice) "
    "or pick that exact option (for Single-Choice). Format answer as JSON matching this schema: "
    "\"responseID\": {\"question_id\": \"<question_id>\", \"type\": \"Single\" or \"Multi\", \"option_id\": [\"<option_id1>\", \"<option_id2>\", ...]}. "
    "REMEMBER: Answer only contains the raw JSON — no extra text before or after. "
)

SYSTEM_PROMPT_FOR_TEXT = (
    "Answer the provided question. Be precise and concise. "
    "The question is in a dict format with the key representing the question id "
    "and the value a JSON dict containing the question and optionally 'previous_attempts'. "
    "The question value might have HTML data but ignore that. "
    "IMPORTANT: If the question has 'previous_attempts', each entry records a grader result"
    "from a prior submission. Use any feedback in those attempts to inform your answer. "
    "Format answer as JSON matching this schema: "
    "\"responseID\": {\"question_id\": \"<question_id>\", \"answer\": \"<your answer>\"}."
    "REMEMBER: Answer only contains the raw JSON — no extra text before or after. "
)


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

    def solve(self) -> bool:
        # Overwrite minimum passing score
        target_grade = 0.8

        while True:
            state = self.get_state()

            if state.get("outcome") and state["outcome"].get("isPassed") and state["outcome"].get("earnedGrade", 0) >= target_grade:
                logger.success("Already passed with target grade!")
                return True

            allowed = state["allowedAction"]
            attempts_remaining = state["attempts"]["attemptsRemaining"]

            if attempts_remaining == 0 or allowed == None:
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

            if allowed == "START_NEW_ATTEMPT":
                if not self.initiate_attempt():
                    logger.error(
                        "Could not start an attempt. Please file an issue.")
                    return False
                continue

            elif allowed == "RESUME_DRAFT":
                logger.info("Resuming existing draft.")

            else:
                logger.error(f"Unexpected allowedAction: {allowed}")
                return False

            self.discarded_questions = []
            questions = self.retrieve_questions(state)
            self._save_data()
            questions_for_llm = {}
            text_questions_for_llm = {}
            correct_answers = {}

            for part_id, q in questions.items():
                options = q.get("Options", [])
                history = q.get("history", [])
                is_single = q["Type"] == "Single-Choice"
                is_text = q["Type"] in ("Numeric", "Text")

                if is_text:
                    known_correct_answer = None
                    previous_attempts = []
                    for entry in history:
                        correctness = entry.get("correctness")
                        if correctness == "CORRECT":
                            known_correct_answer = entry.get("answer")
                            break
                        elif correctness == "INCORRECT":
                            previous_attempts.append({
                                "answer": entry.get("answer"),
                                "hint": entry.get("hint"),
                            })

                    if known_correct_answer is not None:
                        correct_answers[part_id] = known_correct_answer
                    else:
                        q_data = {"Question": q["Question"]}
                        if previous_attempts:
                            q_data["previous_attempts"] = previous_attempts
                        text_questions_for_llm[part_id] = q_data
                    continue

                known = {}
                for entry in history:
                    for val, info in entry.get("options", {}).items():
                        if info.get("correct") is not None:
                            known.setdefault(val, {})["correct"] = info["correct"]
                        if info.get("hint"):
                            known.setdefault(val, {})["hint"] = info["hint"]

                known_correct_id = None
                if is_single:
                    for opt in options:
                        k = known.get(opt["value"], {})
                        if k.get("correct") is True:
                            known_correct_id = opt["option_id"]
                            break

                all_options_known = False
                known_correct_checkbox_ids = []
                if not is_single:
                    all_options_known = all(opt["value"] in known for opt in options)
                    if all_options_known:
                        known_correct_checkbox_ids = [
                            opt["option_id"] for opt in options
                            if known.get(opt["value"], {}).get("correct") is True
                        ]

                if is_single and known_correct_id:
                    correct_answers[part_id] = known_correct_id
                elif not is_single and all_options_known:
                    correct_answers[part_id] = known_correct_checkbox_ids
                else:
                    questions_for_llm[part_id] = {
                        "Question": q["Question"],
                        "Options": q["Options"],
                        "Type": q["Type"],
                    }

                    virtual_feedbacks = []
                    for opt in options:
                        k = known.get(opt["value"], {})
                        correctness = k.get("correct")
                        if correctness is None:
                            continue
                        virtual_feedbacks.append({
                            "response": opt["option_id"] if is_single else [opt["option_id"]],
                            "correctness": "CORRECT" if correctness else "INCORRECT"
                        })

                    if virtual_feedbacks:
                        questions_for_llm[part_id]["previous_attempts"] = virtual_feedbacks

            if questions_for_llm or text_questions_for_llm:
                if config.PERPLEXITY_API_KEY:
                    connector = PerplexityConnector()
                elif config.GEMINI_API_KEY:
                    connector = GeminiConnector()
                elif config.DEEPSEEK_API_KEY:
                    connector = DeepSeekConnector()
                else:
                    raise RuntimeError("No API Key specified.")
            else:
                connector = None
            llm_answers = None
            if questions_for_llm:
                while (llm_answers == None):
                    llm_result = connector.get_response(
                        questions_for_llm, system_prompt=SYSTEM_PROMPT_FOR_CHOICE, response_schema=DEFAULT_RESPONSE_SCHEMA)
                    llm_answers = llm_result["responses"]
            else:
                llm_answers = []
            
            text_llm_answers = None
            if text_questions_for_llm:
                while(text_llm_answers == None):
                    text_llm_result = connector.get_response(
                        text_questions_for_llm, system_prompt=SYSTEM_PROMPT_FOR_TEXT, response_schema=TEXT_RESPONSE_SCHEMA)
                    text_llm_answers = text_llm_result["responses"]
            else:
                text_llm_answers = []

            if not questions_for_llm and not text_questions_for_llm:
                logger.info(
                    "All questions already correct — resubmitting same answers.")

            answer_responses = []
            for answer in llm_answers:
                if type(answer) == str:
                    answer = llm_answers[answer]
                answer_responses.append({
                    "questionId": answer["question_id"],
                    "questionType": "MULTIPLE_CHOICE" if answer["type"] == "Single" else "CHECKBOX",
                    "questionResponse": {
                        "multipleChoiceResponse" if answer["type"] == "Single" else "checkboxResponse": {
                            "chosen": answer["option_id"][0] if answer["type"] == "Single" else answer["option_id"]
                        }
                    }
                })

            for answer in text_llm_answers:
                if type(answer) == str:
                    answer = text_llm_answers[answer]
                part_id = answer["question_id"]
                q = questions[part_id]
                typename = q["__typename"]
                response_field = QUESTION_TYPE_MAP[typename][0]
                question_type = QUESTION_TYPE_MAP[typename][1]
                model = MODEL_MAP[typename]
                blank = deep_blank_model(model)
                inner_key = list(blank.keys())[0]
                answer_responses.append({
                    "questionId": part_id,
                    "questionType": question_type,
                    "questionResponse": {
                        response_field: {
                            inner_key: answer["answer"]
                        }
                    }
                })

            for part_id, response in correct_answers.items():
                q = questions[part_id]
                if q["Type"] in ("Text", "Numeric"):
                    typename = q["__typename"]
                    response_field = QUESTION_TYPE_MAP[typename][0]
                    question_type = QUESTION_TYPE_MAP[typename][1]
                    model = MODEL_MAP[typename]
                    blank = deep_blank_model(model)
                    inner_key = list(blank.keys())[0]
                    answer_responses.append({
                        "questionId": part_id,
                        "questionType": question_type,
                        "questionResponse": {
                            response_field: {
                                inner_key: response
                            }
                        }
                    })
                else:
                    is_single = q["Type"] == "Single-Choice"
                    answer_responses.append({
                        "questionId": part_id,
                        "questionType": "MULTIPLE_CHOICE" if is_single else "CHECKBOX",
                        "questionResponse": {
                            "multipleChoiceResponse" if is_single else "checkboxResponse": {
                                "chosen": response
                            }
                        }
                    })

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

            options = []
            for option in question["questionSchema"].get("options", []):
                options.append({
                    "option_id": option["optionId"],
                    "value": option["display"]["cmlValue"]
                })

            part_id = question["partId"]

            existing = self.questions_data.get(part_id, {})
            existing_history = existing.get("history", [])

            questions_formatted[part_id] = {
                "Question": question["questionSchema"]["prompt"]["cmlValue"],
                "Options": options,
                "Type": "Single-Choice" if question["__typename"] == "Submission_MultipleChoiceQuestion" else
                        "Numeric" if question["__typename"] == "Submission_NumericQuestion" else
                        "Multi-Choice" if question["__typename"] == "Submission_CheckboxQuestion" else
                        "Text",
                "__typename": question["__typename"],
                "history": existing_history
            }

        self.questions_data.update(questions_formatted)

        return questions_formatted

    def save_responses(self, answers: list) -> bool:
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
                    "questionResponses": [*answers, *self.discarded_questions]
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

        logger.debug([*answers, *self.discarded_questions])
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

    def get_feedback(self, max_retries: int = 3, interval: float = 3.0) -> dict | None:
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
            time.sleep(interval)

        logger.warning("Feedback did not become available in time.")
        return None

    def _update_data_from_feedback(self, feedback_parts: list,
                                   submitted_responses: list) -> None:
        """
        Append a history entry per question from Coursera feedback.
        """
        question_lookup = {}
        for part_id in self.questions_data:
            key = part_id.split("~")[-1]
            question_lookup[key] = part_id

        response_lookup = {}
        for resp in submitted_responses:
            qr = resp.get("questionResponse", {})
            chosen = None
            for key in ("multipleChoiceResponse", "checkboxResponse"):
                if key in qr:
                    chosen = qr[key].get("chosen")
                    break
            response_lookup[resp["questionId"]] = chosen

        for part in feedback_parts:
            feedback_part_id = part.get("partId", "")
            feedback_key = feedback_part_id.split("~")[-1]

            our_part_id = question_lookup.get(feedback_key)
            if not our_part_id:
                continue

            fb = part.get("feedback", {})
            correctness = fb.get("correctness")
            outcome = fb.get("autoGradedFeedbackOutcome", {})
            submitted_chosen = response_lookup.get(our_part_id)
            our_q = self.questions_data[our_part_id]
            all_options = our_q.get("Options", [])
            is_single = our_q["Type"] == "Single-Choice"

            chosen_texts = set()
            if submitted_chosen:
                texts = self._get_response_text(all_options, submitted_chosen)
                chosen_texts = {texts} if isinstance(texts, str) else set(texts)

            options_info = {}
            schema_options = (part.get("questionSchema") or {}).get("options") or []
            if not schema_options:
                # Text question (numeric, text-match, regex, etc.) —
                # record answer + correctness for learning across attempts.
                is_text_q = our_q["Type"] in ("Numeric", "Text")
                if is_text_q and correctness:
                    typename = our_q.get("__typename")
                    if typename and typename in QUESTION_TYPE_MAP:
                        response_field = QUESTION_TYPE_MAP[typename][0]
                        response_data = part.get(response_field, {}) or {}
                        model = MODEL_MAP.get(typename)
                        if model:
                            inner_key = list(deep_blank_model(model).keys())[0]
                            submitted_answer = response_data.get(inner_key)
                        else:
                            submitted_answer = None
                    else:
                        submitted_answer = None
                    history_entry = {
                        "score": outcome.get("score"),
                        "maxScore": outcome.get("maxScore"),
                        "answer": submitted_answer,
                        "correctness": correctness,
                        "hint": (fb.get("feedback") or {}).get("cmlValue"),
                    }
                    our_q.setdefault("history", []).append(history_entry)
                continue

            for opt in schema_options:
                val = opt["display"].get("cmlValue")
                if not val:
                    continue
                entry = {"chosen": val in chosen_texts}
                if "correctlyAnswered" in opt:
                    entry["correct"] = opt["correctlyAnswered"]
                opt_fb = (opt.get("feedback") or {}).get("cmlValue")
                if opt_fb:
                    entry["hint"] = opt_fb
                options_info[val] = entry

            if is_single and chosen_texts:
                chosen_text = next(iter(chosen_texts))
                if correctness == "CORRECT":
                    for opt in all_options:
                        options_info.setdefault(opt["value"], {})["chosen"] = opt["value"] == chosen_text
                        options_info[opt["value"]]["correct"] = (opt["value"] == chosen_text)
                elif correctness == "INCORRECT":
                    options_info.setdefault(chosen_text, {})["chosen"] = True
                    options_info[chosen_text]["correct"] = False

                part_hint = (fb.get("feedback") or {}).get("cmlValue")
                if part_hint:
                    options_info.setdefault(chosen_text, {})["hint"] = part_hint

            history_entry = {
                "score": outcome.get("score"),
                "maxScore": outcome.get("maxScore"),
                "options": options_info,
            }
            our_q.setdefault("history", []).append(history_entry)
