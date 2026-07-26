"""
api/external.py — Generic External Service Client
===================================================
A reusable HTTP client wrapper for calling any external REST API.

Provides automatic retries, consistent error handling, and optional
bearer-token authentication in a single base class.  Concrete service
clients (weather, Home Assistant, Google Calendar, etc.) should subclass
``ExternalServiceClient`` rather than using httpx directly.

Usage — defining a new service client
--------------------------------------
    from api.external import ExternalServiceClient

    class WeatherClient(ExternalServiceClient):
        BASE_URL = "https://api.openweathermap.org/data/2.5"

        def get_current(self, city: str) -> dict:
            return self.get("/weather", params={"q": city, "appid": self._api_key})

    # Instantiate with your key
    weather = WeatherClient(api_key=config.get("weather.api_key"))
    data = weather.get_current("London")

Usage — one-off requests
-------------------------
    from api.external import ExternalServiceClient

    client = ExternalServiceClient(base_url="https://httpbin.org")
    result = client.get("/json")
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


class ExternalServiceError(Exception):
    """Raised when an external service returns a non-retryable error."""


class ExternalServiceClient:
    """
    Base class for all external REST API clients.

    Subclass this and set ``BASE_URL`` to build service-specific clients.

    Parameters
    ----------
    base_url    : Base URL for all requests (overrides ``BASE_URL`` class attr).
    api_key     : Bearer token / API key (added as Authorization header).
    timeout     : Request timeout in seconds.
    max_retries : Number of retry attempts on transient failures.
    extra_headers : Any additional headers merged into every request.
    """

    BASE_URL: str = ""   # Override in subclasses

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout: int = 15,
        max_retries: int = 3,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        url = base_url or self.BASE_URL
        if not url:
            raise ValueError(
                "base_url must be provided either as a constructor argument "
                "or as the BASE_URL class attribute."
            )

        self._api_key = api_key
        self._max_retries = max_retries

        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)

        self._client = httpx.Client(
            base_url=url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )

    # ── Request helpers ────────────────────────────────────────────────────────

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Send a GET request and return the parsed JSON response.

        Parameters
        ----------
        path   : URL path relative to base_url.
        params : Query string parameters.
        **kwargs : Extra arguments forwarded to httpx.

        Returns
        -------
        Parsed JSON (dict, list, etc.).
        """
        return self._request("GET", path, params=params, **kwargs)

    def post(
        self,
        path: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Send a POST request with a JSON body and return the parsed response.

        Parameters
        ----------
        path   : URL path relative to base_url.
        data   : Request body (serialised as JSON).
        params : Optional query parameters.
        """
        return self._request("POST", path, json=data, params=params, **kwargs)

    def put(
        self,
        path: str,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Send a PUT request."""
        return self._request("PUT", path, json=data, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        """Send a DELETE request."""
        return self._request("DELETE", path, **kwargs)

    def health_check(self) -> dict[str, Any]:
        """
        Basic connectivity check — override in subclasses for a proper probe.

        Returns a dict with "reachable" (bool) and optional "error".
        """
        try:
            # A HEAD request to the root is the lightest possible probe
            response = self._client.head("/")
            return {"reachable": response.status_code < 500}
        except Exception as exc:
            return {"reachable": False, "error": str(exc)}

    # ── Internal ───────────────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Execute an HTTP request with retry logic."""
        try:
            response = self._client.request(method, path, **kwargs)
            if response.status_code == 401:
                raise ExternalServiceError(
                    f"Unauthorised (HTTP 401) calling {method} {path}. "
                    "Check the API key for this service."
                )
            response.raise_for_status()

            # Return JSON if the response has a JSON content-type, else raw text
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                return response.json()
            return response.text

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body = exc.response.text[:200]   # truncate huge error pages
            log.error(f"HTTP {status} from {method} {path}: {body}")
            raise ExternalServiceError(f"HTTP {status}: {body}") from exc

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "ExternalServiceClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
