import json
import requests
from ..config import (PERPLEXITY_API_URL, PERPLEXITY_API_KEY,
                      PERPLEXITY_MODEL, GEMINI_API_KEY, GEMINI_MODEL)
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import Any, List, Literal, Optional
from loguru import logger


class ResponseFormat(BaseModel):
    question_id: str
    question_type: Literal["MULTIPLE_CHOICE", "CHECKBOX", "TEXT_REFLECT"]
    chosen: Optional[List[str]] = None
    answer: Optional[str] = None


class ResponseList(BaseModel):
    responses: List[ResponseFormat]


DEFAULT_RESPONSE_SCHEMA = ResponseList.model_json_schema()


class PerplexityConnector(object):
    def __init__(self):
        self.API_URL: str = PERPLEXITY_API_URL
        self.API_KEY: str = PERPLEXITY_API_KEY

    def get_response(
            self,
            prompt: dict | str,
            system_prompt: str,
            response_schema: dict[str, Any] | None = None
    ) -> dict | str:
        """
        Sends a prompt to Perplexity and optionally asks for a JSON schema response.
        """
        logger.debug("Making an API Request to Perplexity..")
        payload = {
            "model": PERPLEXITY_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(
                    prompt) if isinstance(prompt, dict) else prompt},
            ],
        }
        if response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"schema": response_schema}
            }

        response = requests.post(url=self.API_URL, headers={
            "Authorization": f"Bearer {self.API_KEY}"
        }, json=payload).json()

        content = response["choices"][0]["message"]["content"]
        if response_schema is not None:
            return json.loads(content)
        return content.strip()


class GeminiConnector(object):
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def get_response(
            self,
            prompt: dict | str,
            system_prompt: str,
            response_schema: dict[str, Any] | None = None
    ) -> dict | str:
        """
        Sends a prompt to Gemini and optionally asks for a JSON schema response.
        """
        logger.debug("Making an API request to Gemini...")
        config_args = {
            "system_instruction": system_prompt,
            "thinking_config": types.ThinkingConfig(
                thinking_level="MINIMAL",
            ),
        }
        if response_schema is not None:
            config_args["response_schema"] = response_schema

        config = types.GenerateContentConfig(
            **config_args
        )

        response = self.client.models.generate_content(
            model=GEMINI_MODEL,
            contents=json.dumps(prompt) if isinstance(
                prompt, dict) else prompt,
            config=config
        )

        raw_text = response.candidates[0].content.parts[0].text
        if response_schema is not None:
            return json.loads(raw_text)
        return raw_text.strip()
