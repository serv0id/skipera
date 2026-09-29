import json
import requests
from config import (PERPLEXITY_API_URL, PERPLEXITY_API_KEY,
                    PERPLEXITY_MODEL, GEMINI_API_KEY, GEMINI_MODEL, SYSTEM_PROMPT)
from google import genai
from google.genai import types
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
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(questions)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"schema": ResponseList.model_json_schema()}
            }
        }).json()

        return json.loads(response["choices"][0]["message"]["content"])


class GeminiConnector(object):
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def get_response(self, questions: dict) -> dict:
        """
        Sends the questions to Gemini and asks for the answers
        in a JSON format.
        """
        logger.debug("Making an API request to Gemini...")
        response = self.client.models.generate_content(
            model=GEMINI_MODEL,
            contents=json.dumps(questions),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_schema=ResponseList.model_json_schema()
            )
        )

        raw_text = response.candidates[0].content.parts[0].text
        return json.loads(raw_text)
