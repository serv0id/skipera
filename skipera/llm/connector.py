import json
import os
from pydantic import BaseModel
from typing import Any, List, Literal, Optional
from loguru import logger
from litellm import completion

from .. import config


class ResponseFormat(BaseModel):
    question_id: str
    question_type: Literal["MULTIPLE_CHOICE", "CHECKBOX", "TEXT_REFLECT",
                            "NUMERIC", "PLAIN_TEXT", "TEXT_EXACT_MATCH", "REGEX",
                            "FILE_UPLOAD", "URL"]
    reasoning: str
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
        prefix, api_keys, model, env_var = PROVIDERS[provider]
        self.model = f"{prefix}/{model}"
        self.env_var = env_var
        self.api_keys = api_keys if isinstance(api_keys, list) else [api_keys]
        self.current_key_idx = 0
        if self.api_keys:
            os.environ[self.env_var] = self.api_keys[self.current_key_idx]

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

        if "nvidia" in self.model or "nemotron" in self.model:
            kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": False}
            }

        from litellm.exceptions import RateLimitError, AuthenticationError
        
        for attempt in range(len(self.api_keys) or 1):
            try:
                response = completion(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(prompt) if isinstance(prompt, dict) else prompt},
                    ],
                    timeout=300.0,
                    **kwargs,
                )
                break
            except (RateLimitError, AuthenticationError) as e:
                logger.warning(f"Key {self.current_key_idx} failed with {type(e).__name__}: {str(e)}")
                if len(self.api_keys) > 1:
                    self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
                    os.environ[self.env_var] = self.api_keys[self.current_key_idx]
                    logger.info(f"Swapped to next key (index {self.current_key_idx}). Retrying...")
                if attempt == len(self.api_keys) - 1:
                    raise e

        content = response["choices"][0]["message"]["content"]
        if response_schema is not None:
            return json.loads(content)
        return content.strip()
