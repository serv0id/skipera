# https://github.com/serv0id/skipera
import json

import requests
from config import PERPLEXITY_API_URL, PERPLEXITY_API_KEY, PERPLEXITY_MODEL


class PerplexityConnector(object):
    def __init__(self):
        self.API_URL: str = PERPLEXITY_API_URL
        self.API_KEY: str = PERPLEXITY_API_KEY

    def get_response(self, questions: dict) -> dict:
        """
        Sends the questions to Perplexity and asks for the answers
        in a JSON format.
        """
        response = requests.post(url=self.API_URL, headers={
            "Authorization": f"Bearer {self.API_KEY}"
        }, json={
            "model": PERPLEXITY_MODEL,
            "messages": [
                {"role": "user", "content": json.dumps(questions)},
                {"role": "system", "content": "Answer the following questions. Return only a JSON response"
                                              "with each key being the question number as a single integer"
                                              "and the value being the option number as a single integer."
                                              "Be precise and concise. The questions are in a dict format"
                                              "Questions may have single-choice or multiple-choice answers,"
                                              "which would be specified by the user in the JSON data."}
            ]
        }).json()

        return response
