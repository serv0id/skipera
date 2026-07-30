import json
import httpx
from ..config import (PERPLEXITY_API_URL, PERPLEXITY_API_KEY, PERPLEXITY_MODEL, 
                      GEMINI_API_KEY, GEMINI_MODEL,
                      OPENAI_API_URL, OPENAI_API_KEY, OPENAI_MODEL,
                      NVIDIA_API_URL, NVIDIA_API_KEY, NVIDIA_MODEL,
                      ANTHROPIC_API_URL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
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

        response = httpx.post(url=self.API_URL, headers={
            "Authorization": f"Bearer {self.API_KEY}"
        }, json=payload, timeout=300.0).json()

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
                thinking_level="low",
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


class OpenAIConnector(object):
    def __init__(self):
        self.API_URL: str = OPENAI_API_URL
        self.API_KEY: str = OPENAI_API_KEY

    def get_response(
            self,
            prompt: dict | str,
            system_prompt: str,
            response_schema: dict[str, Any] | None = None
    ) -> dict | str:
        logger.debug("Making an API Request to OpenAI..")
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt) if isinstance(prompt, dict) else prompt},
            ],
        }
        if response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": response_schema,
                    "strict": False
                }
            }

        response = httpx.post(url=self.API_URL, headers={
            "Authorization": f"Bearer {self.API_KEY}"
        }, json=payload, timeout=300.0).json()
        
        try:
            content = response["choices"][0]["message"]["content"]
        except Exception:
            logger.error(f"Failed to fetch from OpenAI: {response}")
            raise
            
        if response_schema is not None:
            return json.loads(content)
        return content.strip()


class NvidiaConnector(object):
    def __init__(self):
        self.API_URL: str = NVIDIA_API_URL
        self.API_KEY: str = NVIDIA_API_KEY

    def get_response(
            self,
            prompt: dict | str,
            system_prompt: str,
            response_schema: dict[str, Any] | None = None
    ) -> dict | str:
        logger.debug("Making an API Request to Nvidia..")
        if response_schema is not None:
            system_prompt += f"\n\nYou MUST return only a raw JSON object adhering to this schema: {json.dumps(response_schema)}"

        payload = {
            "model": NVIDIA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt) if isinstance(prompt, dict) else prompt},
            ],
        }
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        response = httpx.post(url=self.API_URL, headers={
            "Authorization": f"Bearer {self.API_KEY}"
        }, json=payload, timeout=300.0).json()

        try:
            content = response["choices"][0]["message"]["content"]
        except Exception:
            logger.error(f"Failed to fetch from Nvidia: {response}")
            raise

        if response_schema is not None:
            return json.loads(content)
        return content.strip()


class AnthropicConnector(object):
    def __init__(self):
        self.API_URL: str = ANTHROPIC_API_URL
        self.API_KEY: str = ANTHROPIC_API_KEY

    def get_response(
            self,
            prompt: dict | str,
            system_prompt: str,
            response_schema: dict[str, Any] | None = None
    ) -> dict | str:
        logger.debug("Making an API Request to Anthropic..")
        payload = {
            "model": ANTHROPIC_MODEL,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": json.dumps(prompt) if isinstance(prompt, dict) else prompt},
            ],
            "max_tokens": 4096
        }
        if response_schema is not None:
            payload["tools"] = [{
                "name": "response",
                "description": "Output the final response matching the given schema.",
                "input_schema": response_schema
            }]
            payload["tool_choice"] = {"type": "tool", "name": "response"}

        response = httpx.post(url=self.API_URL, headers={
            "x-api-key": self.API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }, json=payload, timeout=300.0).json()
        
        if "error" in response:
            logger.error(f"Anthropic error: {response}")
            raise ValueError(response["error"])

        if response_schema is not None:
            for block in response.get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == "response":
                    return block.get("input", {})
            
            return json.loads(response["content"][0]["text"])

        return response["content"][0]["text"].strip()
