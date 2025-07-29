import requests

from assessment.types import QUESTION_TYPE_MAP, MODEL_MAP
from config import GRAPHQL_URL
from assessment.queries import (GET_STATE_QUERY, SAVE_RESPONSES_QUERY, SUBMIT_DRAFT_QUERY,
                                GRADING_STATUS_QUERY, INITIATE_ATTEMPT_QUERY)
from loguru import logger
from llm.connector import PerplexityConnector


class GradedSolver(object):
    def __init__(self, session: requests.Session, course_id: str, item_id: str):
        self.session: requests.Session = session
        self.course_id: str = course_id
        self.item_id: str = item_id
        self.attempt_id = None
        self.draft_id = None
        self.discarded_questions = []

    def solve(self):
        state = self.get_state()

        if state["allowedAction"] == "RESUME_DRAFT":
            logger.error("An attempt is already in progress, please abort it manually.")
            self.attempt_id = self.initiate_attempt()  # remove this
            questions = self.retrieve_questions()
            connector = PerplexityConnector()
            answers = connector.get_response(questions)
            self.save_responses(answers["responses"])

        elif state["allowedAction"] == "START_NEW_ATTEMPT":
            if state["attempts"]["attemptsRemaining"] == 0:
                logger.error("No more attempts can be made!")
            else:
                self.attempt_id = self.initiate_attempt()
                questions = self.retrieve_questions()
                connector = PerplexityConnector()
                answers = connector.get_response(questions)
                if not self.save_responses(answers["responses"]):
                    logger.error("Could not save responses. Please file an issue.")
                else:
                    self.submit_draft()

        else:
            logger.error("Something went wrong! Please file an issue.")

    def get_state(self) -> dict:
        """
        Retrieves the current state of the assessment.
        """
        res = self.session.post(url=GRAPHQL_URL, params={
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

    def initiate_attempt(self) -> str:
        """
        Initiates a new attempt for the assessment.
        Returns the attempt ID.
        """
        res = self.session.post(url=GRAPHQL_URL, params={
            "opname": "Submission_StartAttempt"
        }, json={
            "operationName": "Submission_StartAttempt",
            "variables": {
                "courseId": self.course_id,
                "itemId": self.item_id
            },
            "query": INITIATE_ATTEMPT_QUERY
        }).json()

        return res["data"]["Submission_StartAttempt"]["submissionState"]["assignment"]["id"]

    def retrieve_questions(self) -> dict:
        """
        Retrieves the questions for the particular attempt
        which are to be sent to the LLM Connector.
        """
        state = self.get_state()
        draft = state["attempts"]["inProgressAttempt"]

        self.draft_id = draft["id"]
        questions = draft["draft"]["parts"]
        questions_formatted = {}

        for question in questions:
            if not question["__typename"] in ["Submission_CheckboxQuestion", "Submission_MultipleChoiceQuestion"]:
                self.discarded_questions.append({
                    "questionId": question["partId"],
                    "questionType": QUESTION_TYPE_MAP[question["__typename"]][1],
                    "questionResponse": {
                        QUESTION_TYPE_MAP[question["__typename"]][0]: MODEL_MAP[question["__typename"]].
                        model_construct().model_dump()
                    }
                })
                continue

            options = []
            for option in question["questionSchema"]["options"]:
                options.append({
                    "option_id": option["optionId"],
                    "value": option["display"]["cmlValue"]
                })

            questions_formatted[question["partId"]] = {"Question": question["questionSchema"]["prompt"]["cmlValue"],
                                                       "Options": options,
                                                       "Type": "Single-Choice" if
                                                       question["__typename"] == "Submission_MultipleChoiceQuestion"
                                                       else "Multi-Choice"}
        return questions_formatted

    def save_responses(self, answers: dict) -> bool:
        """
        Saves the responses for the assessment to the draft.
        """
        answer_responses = []

        for answer in answers:
            answer_responses.append({
                "questionId": answer["question_id"],
                "questionType": "MULTIPLE_CHOICE" if answer["type"] == "Single" else "CHECKBOX",
                "questionResponse": {
                    "multipleChoiceResponse" if answer["type"] == "Single" else "checkboxResponse": {
                        "chosen": answer["option_id"][0] if answer["type"] == "Single" else answer["option_id"]
                    }
                }
            })

        res = self.session.post(url=GRAPHQL_URL, params={
            "opname": "Submission_SaveResponses"
        }, json={
            "operationName": "Submission_SaveResponses",
            "variables": {
                "input": {
                    "courseId": self.course_id,
                    "itemId": self.item_id,
                    "attemptId": self.draft_id,
                    "questionResponses": [*answer_responses, *self.discarded_questions]
                }
            },
            "query": SAVE_RESPONSES_QUERY
        })

        if "Submission_SaveResponsesSuccess" in res.text:
            return True
        return False

    def submit_draft(self):
        """
        Submits the draft for evaluation after the submission is saved.
        """
        pass
