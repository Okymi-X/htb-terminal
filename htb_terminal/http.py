from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
    def __init__(self, base_url: str, token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def get(self, path: str, query: dict[str, Any] | None = None) -> Any:
        return self.request_json("GET", path, query=query)

    def post(self, path: str, data: dict[str, Any] | None = None) -> Any:
        return self.request_json("POST", path, data=data)

    def download(self, path: str, query: dict[str, Any] | None = None) -> bytes:
        return self.request("GET", path, query=query).body

    def request_json(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> Any:
        response = self.request(method, path, data=data, query=query)
        return response.json()

    def request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> ApiResponse:
        url = self._url(path, query)
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "htb-terminal/0.1",
        }
        payload = None
        if data is not None:
            payload = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=payload, headers=headers, method=method.upper())

        try:
            with urlopen(request, timeout=self.timeout) as response:
                return ApiResponse(
                    status=response.status,
                    content_type=response.headers.get("Content-Type", ""),
                    body=response.read(),
                )
        except HTTPError as exc:
            body = exc.read()
            parsed = _parse_error_body(body)
            message = _error_message(exc.code, parsed, body)
            raise ApiError(exc.code, message, parsed) from exc
        except URLError as exc:
            raise ApiError(None, f"Network error: {exc.reason}") from exc

    def _url(self, path: str, query: dict[str, Any] | None = None) -> str:
        clean_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{clean_path}"
        if query:
            url = f"{url}?{urlencode({k: v for k, v in query.items() if v is not None})}"
        return url


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

