import json
import re
import httpx
from ..config import (PERPLEXITY_API_URL, PERPLEXITY_API_KEY,
                      PERPLEXITY_MODEL, GEMINI_API_KEY, GEMINI_MODEL,
                      GROQ_API_URL, GROQ_API_KEY, GROQ_MODEL)
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import Any, List, Literal, Optional
from loguru import logger


class ResponseFormat(BaseModel):
    question_id: str
    question_type: Literal[
        "MULTIPLE_CHOICE", "CHECKBOX", "TEXT_REFLECT", "RICH_TEXT",
        "PLAIN_TEXT", "NUMERIC", "MATH", "TEXT_EXACT_MATCH", "REGEX"
    ]
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
        }, json=payload, timeout=60.0, verify=False).json()

        content = response["choices"][0]["message"]["content"]
        if response_schema is not None:
            c = content.strip()
            if c.startswith("```"):
                c = re.sub(r"^```(?:json)?\s*", "", c)
                c = re.sub(r"\s*```$", "", c)
            return json.loads(c)
        return content.strip()


class GroqConnector(object):
    def __init__(self, api_key: str | None = None):
        self.API_URL: str = GROQ_API_URL
        # Use provided api_key or fallback to config/default
        self.API_KEY: str = api_key if api_key is not None else GROQ_API_KEY

    def get_response(
            self,
            prompt: dict | str,
            system_prompt: str,
            response_schema: dict[str, Any] | None = None
    ) -> dict | str:
        """
        Sends a prompt to Groq and optionally asks for a JSON schema response.
        """
        logger.debug("Making an API Request to Groq..")
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(
                    prompt) if isinstance(prompt, dict) else prompt},
            ],
        }
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}
            payload["messages"][0]["content"] += f"\n\nYou MUST return a JSON object that adheres to the following JSON schema:\n{json.dumps(response_schema)}"

        resp = httpx.post(url=self.API_URL, headers={
            "Authorization": f"Bearer {self.API_KEY}"
        }, json=payload, timeout=60.0, verify=False)
        response = resp.json()

        if "error" in response:
            error_msg = response["error"].get("message", "Unknown error")
            raise RuntimeError(f"Groq API Error ({resp.status_code}): {error_msg}")

        content = response["choices"][0]["message"]["content"]
        if response_schema is not None:
            c = content.strip()
            if c.startswith("```"):
                c = re.sub(r"^```(?:json)?\s*", "", c)
                c = re.sub(r"\s*```$", "", c)
            return json.loads(c)
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
            c = raw_text.strip()
            if c.startswith("```"):
                c = re.sub(r"^```(?:json)?\s*", "", c)
                c = re.sub(r"\s*```$", "", c)
            return json.loads(c)
        return raw_text.strip()


def test_llm_setup() -> None:
    from .. import config
    if config.PERPLEXITY_API_KEY:
        logger.info("Using Perplexity for LLM.")
        return
    if config.GEMINI_API_KEY:
        logger.info("Using Gemini for LLM.")
        return
    
    # Otherwise check Groq
    groq_keys = getattr(config, "GROQ_API_KEYS", [])
    if not groq_keys and config.GROQ_API_KEY:
        groq_keys = [config.GROQ_API_KEY]
        
    if not groq_keys:
        logger.error("No LLM API Key specified! Please add a Gemini, Perplexity, or Groq API key.")
        raise SystemExit(1)
        
    logger.info(f"Testing {len(groq_keys)} Groq API keys to ensure at least one is working...")
    working_key_found = False
    last_error = None
    for key in groq_keys:
        try:
            conn = GroqConnector(api_key=key)
            conn.get_response("hello", system_prompt="reply with hi")
            working_key_found = True
            logger.success(f"Groq API key {key[:5]}... is working!")
            break 
        except Exception as e:
            last_error = e
            logger.debug(f"Groq API key {key[:5]}... failed test: {e}")
            
    if not working_key_found:
        logger.error(f"All provided Groq API keys failed ({last_error}). Please try again later or provide a new key.")
        raise SystemExit(1)
        
    # We do NOT overwrite config.GROQ_API_KEYS here.
    # This allows solver.py to rotate through all keys (in case one hits a rate limit later).

