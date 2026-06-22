from __future__ import annotations

import json
import logging
import os
from typing import Any, Final, Protocol, runtime_checkable

import httpx

from social_content_factory.schemas.brand import Brand

logger = logging.getLogger(__name__)

OLLAMA_DEFAULT_BASE_URL: Final[str] = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL: Final[str] = "phi4:14b"
OPENROUTER_DEFAULT_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 90.0


class LLMClientError(Exception):
    """Raised when an LLM call fails or returns an unusable response."""


class LLMClientConfigError(LLMClientError):
    """Raised when LLM client configuration is missing or invalid."""


@runtime_checkable
class LLMClient(Protocol):
    model: str

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class OllamaLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls, *, model_env_var: str | None = None) -> "OllamaLLMClient":
        base_url = os.environ.get("SCF_OLLAMA_BASE_URL", OLLAMA_DEFAULT_BASE_URL)
        model = OLLAMA_DEFAULT_MODEL
        if model_env_var:
            model = os.environ.get(model_env_var, OLLAMA_DEFAULT_MODEL)
        return cls(base_url=base_url, model=model)

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": options or {},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as http:
                response = await http.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise LLMClientError(f"Ollama request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMClientError(
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            content = response.json()["message"]["content"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise LLMClientError(f"unexpected Ollama response shape: {exc}") from exc

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMClientError(
                f"Ollama did not return valid JSON content: {content[:200]}"
            ) from exc

        if not isinstance(parsed, dict):
            raise LLMClientError(f"Ollama returned non-object payload: {parsed!r}")
        return parsed


class OpenRouterLLMClient:
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = OPENROUTER_DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls, *, model: str) -> "OpenRouterLLMClient":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise LLMClientConfigError(
                "OPENROUTER_API_KEY is not set; required for llm_provider=openrouter"
            )
        base_url = os.environ.get(
            "SCF_OPENROUTER_BASE_URL", OPENROUTER_DEFAULT_BASE_URL
        )
        return cls(model=model, api_key=api_key, base_url=base_url)

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        if options:
            payload.update(options)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "social-content-factory",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as http:
                response = await http.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise LLMClientError(f"OpenRouter request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMClientError(
                f"OpenRouter returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMClientError(
                f"unexpected OpenRouter response shape: {exc}"
            ) from exc

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMClientError(
                f"OpenRouter did not return valid JSON content: {content[:200]}"
            ) from exc

        if not isinstance(parsed, dict):
            raise LLMClientError(f"OpenRouter returned non-object payload: {parsed!r}")
        return parsed


def make_llm_client(brand: Brand, *, model_env_var: str | None = None) -> LLMClient:
    if brand.llm_provider == "openrouter":
        if not brand.llm_model:
            raise LLMClientConfigError(
                "brand has llm_provider=openrouter but no llm_model configured"
            )
        logger.info(
            "llm_client routed brand=%s provider=openrouter model=%s",
            brand.key, brand.llm_model,
        )
        return OpenRouterLLMClient.from_env(model=brand.llm_model)

    client = OllamaLLMClient.from_env(model_env_var=model_env_var)
    logger.info(
        "llm_client routed brand=%s provider=phi4 model=%s",
        brand.key, client.model,
    )
    return client
