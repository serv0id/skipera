import json
from config import PERPLEXITY_API_KEY, PERPLEXITY_MODEL
from pydantic import BaseModel
from typing import List, Literal
from loguru import logger
from perplexity import Perplexity


class ResponseFormat(BaseModel):
    question_id: str
    option_id: List[str]
    type: Literal["Single", "Multi"]


class PerplexityConnector(object):
    def __init__(self):
        self.API_KEY: str = PERPLEXITY_API_KEY
        self.MODEL: str = PERPLEXITY_MODEL
        self.client = Perplexity(api_key=self.API_KEY)

    def get_response(self, questions: dict):
        """
        Sends the questions to Perplexity and asks for the answers
        in a JSON format.
        """
        logger.debug("Making an API Request to Perplexity..")

        # noinspection PyTypeChecker
        response = self.client.responses.create(
            model=self.MODEL,
            instructions="Answer the provided many questions."
                         "Be precise and concise. The questions are in a dict format"
                         "with the key representing the question id and the value a"
                         "JSON dict containing several things."
                         "Questions may have single-choice or multiple-choice answers,"
                         "which would be specified by the user in the JSON data."
                         "The question/option values might have HTML data but ignore that."
                         "Return the output as a list of objects specified in the following "
                         f"format: {ResponseFormat.model_json_schema()}",
            input=json.dumps(questions),
            tools=[
                {
                    "type": "web_search"
                }
            ]
        )

        return json.loads(response.output[0].content[0].text)
