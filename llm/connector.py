# https://github.com/serv0id/skipera
import json
import requests
from config import PERPLEXITY_API_URL, PERPLEXITY_API_KEY, PERPLEXITY_MODEL
from pydantic import BaseModel
from typing import List, Literal
from loguru import logger


class ResponseFormat(BaseModel):
    question_id: str
    option_id: List[str]
    type: Literal["Single", "Multi"]


class ResponseList(BaseModel):
    responses: List[ResponseFormat]


class PerplexityConnector(object):
    def __init__(self):
        self.API_URL: str = PERPLEXITY_API_URL
        self.API_KEY: str = PERPLEXITY_API_KEY

    def get_response(self, questions: dict) -> dict:
        """
        Sends the questions to Perplexity and asks for the answers
        in a JSON format.
        """
        logger.debug("Making an API Request to Perplexity..")
        response = requests.post(url=self.API_URL, headers={
            "Authorization": f"Bearer {self.API_KEY}"
        }, json={
            "model": PERPLEXITY_MODEL,
            "messages": [
                {"role": "system", "content": "Answer the provided many questions."
                                              "Be precise and concise. The questions are in a dict format"
                                              "with the key representing the question id and the value a"
                                              "JSON dict containing several things."
                                              "Questions may have single-choice or multiple-choice answers,"
                                              "which would be specified by the user in the JSON data."
                                              "The question/option values might have HTML data but ignore that."},
                {"role": "user", "content": json.dumps(questions)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"schema": ResponseList.model_json_schema()}
            }
        }).json()

        return json.loads(response["choices"][0]["message"]["content"])
