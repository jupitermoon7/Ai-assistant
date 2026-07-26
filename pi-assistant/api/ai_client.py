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

Tool/function calling: pass ``tools`` and the client returns either a plain
string reply OR a list of tool-call dicts for the caller to execute.

Usage
-----
    from api.ai_client import AIClient
    from core.config import config

    client = AIClient.from_config(config)

    # Simple completion
    response = client.chat("Tell me a joke")
    print(response)

    # Multi-turn with tools
    result = client.chat_messages(messages, tools=TOOL_DEFINITIONS)
    if isinstance(result, list):
        # result is a list of {"id", "name", "arguments"} dicts
        ...
    else:
        print(result)  # plain string reply
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

class _RateLimitError(Exception):
    """Internal — raised on HTTP 429 so tenacity can retry with backoff."""


class AIClient:
    """
    OpenAI-compatible LLM client with automatic retries and tool-call support.

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
        Does not support tool calls — use chat_messages() for that.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ]
        result = self.chat_messages(messages, model=model, **kwargs)
        # chat() always returns a string (no tools passed)
        return result if isinstance(result, str) else str(result)

    def chat_messages(
        self,
        messages: list[dict],
        model: str | None = None,
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> str | list[dict]:
        """
        Send a full message list and return either:
        - str  — the assistant's reply text (no tool calls requested)
        - list — a list of tool-call dicts: [{"id", "name", "arguments"}, ...]

        Parameters
        ----------
        messages : List of dicts with "role" and "content" keys.
        model    : Override the default model.
        tools    : OpenAI tool definitions list. When provided, the model may
                   return tool calls instead of a text reply.
        **kwargs : Extra API parameters (temperature, max_tokens, etc.).
        """
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": messages,
            **kwargs,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        data = self._post_with_retry("/chat/completions", payload)

        try:
            choice  = data["choices"][0]
            message = choice["message"]
            finish  = choice.get("finish_reason", "")

            # The model wants to call tools
            if finish == "tool_calls" or message.get("tool_calls"):
                calls = []
                for tc in message["tool_calls"]:
                    calls.append({
                        "id":        tc["id"],
                        "name":      tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                        # Preserve the raw message for appending to history
                        "_raw_message": message,
                    })
                return calls

            # Plain text reply
            return message.get("content") or ""

        except (KeyError, IndexError) as exc:
            raise AIClientError(f"Unexpected API response shape: {data}") from exc

    def list_models(self) -> list[str]:
        """Return model names available at the configured endpoint."""
        try:
            response = self._client.get("/models")
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception as exc:
            log.warning(f"Could not list models: {exc}")
            return []

    def health_check(self) -> dict[str, Any]:
        """Verify API connectivity without consuming tokens."""
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
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException, _RateLimitError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def _do_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Low-level POST with retry decorator applied."""
        try:
            response = self._client.post(path, json=payload)
            if response.status_code == 401:
                raise AIClientError(
                    "API key is invalid or missing (HTTP 401). "
                    "Check that OPENAI_API_KEY is set correctly in your .env file."
                )
            if response.status_code == 429:
                log.warning("Rate limited by AI provider — retrying with backoff…")
                raise _RateLimitError(
                    "Rate limited by the AI provider (HTTP 429). "
                    "If this keeps happening, check your OpenAI billing at "
                    "platform.openai.com/settings/billing."
                )
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
