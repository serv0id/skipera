import json
import os
from pydantic import BaseModel
from typing import Any, List, Literal, Optional
from loguru import logger
from litellm import completion

from .. import config


class ResponseFormat(BaseModel):
    question_id: str
    question_type: Literal["MULTIPLE_CHOICE", "CHECKBOX", "TEXT_REFLECT"]
    chosen: Optional[List[str]] = None
    answer: Optional[str] = None


class ResponseList(BaseModel):
    responses: List[ResponseFormat]


DEFAULT_RESPONSE_SCHEMA = ResponseList.model_json_schema()

# provider -> (litellm model prefix, api key, model override, env var litellm reads the key from)
PROVIDERS = {
    "perplexity": ("perplexity", config.PERPLEXITY_API_KEY, config.PERPLEXITY_MODEL, "PERPLEXITYAI_API_KEY"),
    "openai": ("openai", config.OPENAI_API_KEY, config.OPENAI_MODEL, "OPENAI_API_KEY"),
    "anthropic": ("anthropic", config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL, "ANTHROPIC_API_KEY"),
    "nvidia": ("nvidia_nim", config.NVIDIA_API_KEY, config.NVIDIA_MODEL, "NVIDIA_NIM_API_KEY"),
    "gemini": ("gemini", config.GEMINI_API_KEY, config.GEMINI_MODEL, "GEMINI_API_KEY"),
}


def get_connector() -> "LiteLLMConnector":
    for name, (_, api_key, _, _) in PROVIDERS.items():
        if api_key:
            return LiteLLMConnector(name)
    raise RuntimeError("No API Key specified.")


class LiteLLMConnector(object):
    def __init__(self, provider: str):
        prefix, api_key, model, env_var = PROVIDERS[provider]
        self.model = f"{prefix}/{model}"
        os.environ[env_var] = api_key

    def get_response(
            self,
            prompt: dict | str,
            system_prompt: str,
            response_schema: dict[str, Any] | None = None
    ) -> dict | str:
        """
        Sends a prompt via LiteLLM and optionally asks for a JSON schema response.
        """
        logger.debug(f"Making an API request to {self.model}...")
        kwargs = {}
        if response_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": response_schema, "strict": False},
            }

        response = completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt) if isinstance(prompt, dict) else prompt},
            ],
            timeout=300.0,
            **kwargs,
        )

        content = response["choices"][0]["message"]["content"]
        if response_schema is not None:
            return json.loads(content)
        return content.strip()
