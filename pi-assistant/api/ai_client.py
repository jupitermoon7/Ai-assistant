"""
api/ai_client.py — AI / LLM Client
=====================================
A thin, provider-agnostic wrapper around any OpenAI-compatible API.

Supports:
- OpenAI  (https://api.openai.com/v1)
- Ollama  (http://localhost:11434/v1)
- Any other OpenAI-compatible endpoint (set AI_BASE_URL in .env)

Retry behaviour: all requests automatically retry up to ``max_retries`` times
with exponential back-off on transient errors (connection, 429, 5xx).

Usage
-----
    from api.ai_client import AIClient
    from core.config import config

    client = AIClient.from_config(config)

    # Simple completion
    response = client.chat("Tell me a joke")
    print(response)

    # Multi-turn conversation
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user",   "content": "What is 2+2?"},
    ]
    response = client.chat_messages(messages)
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.logger import get_logger

log = get_logger(__name__)


class AIClientError(Exception):
    """Raised when the AI API returns a non-retryable error."""


class AIClient:
    """
    OpenAI-compatible LLM client with automatic retries.

    Parameters
    ----------
    base_url    : API base URL (e.g. "https://api.openai.com/v1").
    api_key     : API key string (empty string for local Ollama).
    model       : Default model to use for requests.
    timeout     : Request timeout in seconds.
    max_retries : Maximum number of retry attempts on failure.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_retries = max_retries

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=timeout,
        )

    @classmethod
    def from_config(cls, config: Any) -> "AIClient":
        """
        Convenience constructor that reads all settings from the config object.

        Parameters
        ----------
        config : The application config singleton (core.config.Config).
        """
        return cls(
            base_url=config.get("ai.base_url", "https://api.openai.com/v1"),
            api_key=config.get("ai.api_key", ""),
            model=config.get("ai.default_model", "gpt-4o-mini"),
            timeout=config.get("ai.timeout", 30),
            max_retries=config.get("ai.max_retries", 3),
        )

    # ── High-level helpers ─────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        system_prompt: str = "You are a helpful personal AI assistant.",
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Send a single-turn chat message and return the response text.

        Parameters
        ----------
        user_message  : The user's input string.
        system_prompt : System instruction for the model.
        model         : Override the default model for this request.
        **kwargs      : Extra parameters forwarded to the API (temperature, etc.).

        Returns
        -------
        str : The model's reply text.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ]
        return self.chat_messages(messages, model=model, **kwargs)

    def chat_messages(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Send a full message list (multi-turn) and return the response text.

        Parameters
        ----------
        messages : List of dicts with "role" and "content" keys.
        model    : Override the default model.
        **kwargs : Extra API parameters (temperature, max_tokens, etc.).

        Returns
        -------
        str : The model's reply text.
        """
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": messages,
            **kwargs,
        }
        data = self._post_with_retry("/chat/completions", payload)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIClientError(f"Unexpected API response shape: {data}") from exc

    def list_models(self) -> list[str]:
        """
        Return the list of model names available at the configured endpoint.

        Useful for checking Ollama availability or confirming API connectivity.
        """
        try:
            response = self._client.get("/models")
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception as exc:
            log.warning(f"Could not list models: {exc}")
            return []

    def health_check(self) -> dict[str, Any]:
        """
        Verify API connectivity without consuming tokens.

        Returns a dict with "reachable" (bool) and optional "error".
        """
        try:
            models = self.list_models()
            return {"reachable": True, "model": self._model, "available_models": models[:5]}
        except Exception as exc:
            return {"reachable": False, "error": str(exc)}

    # ── Internal ───────────────────────────────────────────────────────────────

    def _post_with_retry(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to *path* with automatic retry on transient errors."""
        return self._do_post(path, payload)

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _do_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Low-level POST with retry decorator applied."""
        try:
            response = self._client.post(path, json=payload)
            if response.status_code == 401:
                raise AIClientError("API key is invalid or missing (HTTP 401)")
            if response.status_code == 429:
                raise AIClientError("Rate limited by the API provider (HTTP 429)")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise AIClientError(f"HTTP {exc.response.status_code}: {exc.response.text}") from exc

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "AIClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
