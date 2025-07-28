import requests
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

    def solve(self):
        state = self.get_state()

        if state["allowedAction"] == "RESUME_DRAFT":
            logger.error("An attempt is in progress, please abort it manually.")

        elif state["allowedAction"] == "START_NEW_ATTEMPT":
            if state["attempts"]["attemptsRemaining"] == 0:
                logger.error("No more attempts can be made!")
            else:
                self.attempt_id = self.initiate_attempt()
                questions = self.retrieve_questions()
                connector = PerplexityConnector()
                answers = connector.get_response(questions)

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
        draft = state["attempts"]["inProgressAttempt"]["draft"]

        self.draft_id = draft["id"]
        questions = draft["parts"]
        questions_formatted = {}

        for question in questions:
            if not question["__typename"] in ["Submission_CheckboxQuestion", "Submission_MultipleChoiceQuestion"]:
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
