import json
import requests
from sympy import false
from ..config import (PERPLEXITY_API_URL, PERPLEXITY_API_KEY,
                      PERPLEXITY_MODEL, GEMINI_API_KEY, GEMINI_MODEL,
                      DEEPSEEK_API_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL)
from openai import OpenAI
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import Any, List, Literal
from loguru import logger


class ResponseFormat(BaseModel):
    question_id: str
    option_id: List[str]
    type: Literal["Single", "Multi"]


class ResponseList(BaseModel):
    responses: List[ResponseFormat]


DEFAULT_RESPONSE_SCHEMA = ResponseList.model_json_schema()


class TextResponseFormat(BaseModel):
    question_id: str
    answer: str


class TextResponseList(BaseModel):
    responses: list[TextResponseFormat]


TEXT_RESPONSE_SCHEMA = TextResponseList.model_json_schema()


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


class DeepSeekConnector(object):
    def __init__(self):
        self.API_URL: str = DEEPSEEK_API_URL
        self.API_KEY: str = DEEPSEEK_API_KEY

    def get_response(
            self,
            prompt: dict | str,
            system_prompt: str,
            response_schema: dict[str, Any] | None = None
    ) -> dict | str:
        """
        Sends a prompt to DeepSeek and optionally asks for a JSON schema response.
        """
        logger.debug("Making an API Request to DeepSeek..")
        client = OpenAI(
            api_key=self.API_KEY,
            base_url=self.API_URL
        )
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(
                    prompt) if isinstance(prompt, dict) else prompt},
            ],
            "stream": False,
            "reasoning_effort": "high",
            "extra_body": {"thinking": {"type": "enabled"}}
        }
        if response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"schema": response_schema}
            }

        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=payload["messages"],
            stream=payload["stream"],
            reasoning_effort=payload["reasoning_effort"],
            extra_body=payload["extra_body"],
            response_format=payload.get("response_schema", None)
        )
        
        content = response.choices[0].message.content
        result = dict()
        if response_schema is not None:
            try:
                result.update({"responses": json.loads(content)})
            except json.decoder.JSONDecodeError:
                result.update({"responses": None})
            return result
        return content.strip()
