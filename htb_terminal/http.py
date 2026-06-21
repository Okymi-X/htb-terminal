from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from htb_terminal import __version__


class ApiError(RuntimeError):
    def __init__(self, status: int | None, message: str, body: Any | None = None):
        self.status = status
        self.body = body
        super().__init__(message)


@dataclass(frozen=True)
class ApiResponse:
    status: int
    content_type: str
    body: bytes

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))


class HtbApiClient:
    def __init__(self, base_url: str, token: str, timeout: int = 30, max_retries: int = 4):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries

    def get(
        self, path: str, query: dict[str, Any] | None = None, *, version: str | None = None
    ) -> Any:
        return self.request_json("GET", path, query=query, version=version)

    def post(
        self, path: str, data: dict[str, Any] | None = None, *, version: str | None = None
    ) -> Any:
        return self.request_json("POST", path, data=data, version=version)

    def download(
        self, path: str, query: dict[str, Any] | None = None, *, version: str | None = None
    ) -> bytes:
        return self.request("GET", path, query=query, version=version).body

    def request_json(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        *,
        version: str | None = None,
    ) -> Any:
        response = self.request(method, path, data=data, query=query, version=version)
        return response.json()

    def request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        *,
        version: str | None = None,
    ) -> ApiResponse:
        url = self._url(path, query, version)
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": f"htb-terminal/{__version__}",
        }
        payload = None
        if data is not None:
            payload = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=payload, headers=headers, method=method.upper())

        backoff = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return ApiResponse(
                        status=response.status,
                        content_type=response.headers.get("Content-Type", ""),
                        body=response.read(),
                    )
            except HTTPError as exc:
                if exc.code == 429 and attempt < self.max_retries:
                    wait = _retry_after_seconds(exc.headers) or backoff
                    print(
                        f"warning: rate limited (HTTP 429), retrying in {wait:.0f}s"
                        f" [{attempt + 1}/{self.max_retries}]",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    backoff *= 2
                    continue
                body = exc.read()
                parsed = _parse_error_body(body)
                message = _error_message(exc.code, parsed, body)
                raise ApiError(exc.code, message, parsed) from exc
            except URLError as exc:
                raise ApiError(None, f"Network error: {exc.reason}") from exc

        raise ApiError(429, "HTTP 429: rate limit retries exhausted")

    def _url(
        self, path: str, query: dict[str, Any] | None = None, version: str | None = None
    ) -> str:
        clean_path = path if path.startswith("/") else f"/{path}"
        url = f"{self._versioned_base(version)}{clean_path}"
        if query:
            url = f"{url}?{urlencode({k: v for k, v in query.items() if v is not None})}"
        return url

    def _versioned_base(self, version: str | None) -> str:
        """Swap the trailing ``/api/vN`` segment for a per-call version.

        HTB rolls out the API one version at a time, so a single command may
        mix versions (most endpoints are v4; a few have moved to v5). Bases
        without a recognizable version segment are returned unchanged.
        """
        if not version:
            return self.base_url
        return re.sub(r"/api/v\d+$", f"/api/{version}", self.base_url)


def _retry_after_seconds(headers: Any) -> float | None:
    value = headers.get("Retry-After") if headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _parse_error_body(body: bytes) -> Any | None:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _error_message(status: int, parsed: Any | None, raw: bytes) -> str:
    if isinstance(parsed, dict):
        message = parsed.get("message") or parsed.get("error")
        if message:
            return f"HTTP {status}: {message}"
    if raw:
        text = raw.decode("utf-8", errors="replace").strip()
        if text:
            return f"HTTP {status}: {text[:500]}"
    return f"HTTP {status}"

