from __future__ import annotations

import io
import json
import unittest
from unittest import mock
from urllib.error import HTTPError

from htb_terminal.http import ApiError, HtbApiClient


def _ok_response(payload: object) -> mock.MagicMock:
    body = json.dumps(payload).encode("utf-8")
    response = mock.MagicMock()
    response.status = 200
    response.headers.get.return_value = "application/json"
    response.read.return_value = body
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def _http_error(code: int, body: bytes = b"", headers: dict[str, str] | None = None) -> HTTPError:
    return HTTPError(
        url="https://example.test/api/v4/x",
        code=code,
        msg="error",
        hdrs=headers or {},
        fp=io.BytesIO(body),
    )


class HtbApiClientTests(unittest.TestCase):
    def setUp(self):
        self.client = HtbApiClient("https://example.test/api/v4", "token", max_retries=3)

    def test_successful_machine_list_response(self):
        payload = {"data": [{"id": 1, "name": "BoardLight", "os": "Linux"}]}
        with mock.patch("htb_terminal.http.urlopen", return_value=_ok_response(payload)) as opened:
            result = self.client.get("/machine/paginated", query={"page": 1})

        self.assertEqual(payload, result)
        request = opened.call_args.args[0]
        self.assertEqual("https://example.test/api/v4/machine/paginated?page=1", request.full_url)
        self.assertEqual("Bearer token", request.headers["Authorization"])

    def test_version_override_swaps_api_segment(self):
        with mock.patch("htb_terminal.http.urlopen", return_value=_ok_response({})) as opened:
            self.client.get("/machines", query={"todo": 1}, version="v5")

        request = opened.call_args.args[0]
        self.assertEqual("https://example.test/api/v5/machines?todo=1", request.full_url)

    def test_version_override_is_a_noop_without_a_version_segment(self):
        client = HtbApiClient("https://example.test/custom", "token")
        with mock.patch("htb_terminal.http.urlopen", return_value=_ok_response({})) as opened:
            client.get("/machines", version="v5")

        request = opened.call_args.args[0]
        self.assertEqual("https://example.test/custom/machines", request.full_url)

    def test_retries_on_429_with_backoff_then_succeeds(self):
        payload = {"data": []}
        side_effects = [
            _http_error(429),
            _http_error(429),
            _ok_response(payload),
        ]
        with (
            mock.patch("htb_terminal.http.urlopen", side_effect=side_effects) as opened,
            mock.patch("htb_terminal.http.time.sleep") as sleep,
        ):
            result = self.client.get("/machine/paginated")

        self.assertEqual(payload, result)
        self.assertEqual(3, opened.call_count)
        self.assertEqual([mock.call(1.0), mock.call(2.0)], sleep.call_args_list)

    def test_429_honors_retry_after_header(self):
        side_effects = [
            _http_error(429, headers={"Retry-After": "7"}),
            _ok_response({}),
        ]
        with (
            mock.patch("htb_terminal.http.urlopen", side_effect=side_effects),
            mock.patch("htb_terminal.http.time.sleep") as sleep,
        ):
            self.client.get("/machine/active")

        sleep.assert_called_once_with(7.0)

    def test_429_raises_after_retries_exhausted(self):
        with (
            mock.patch("htb_terminal.http.urlopen", side_effect=_http_error(429)) as opened,
            mock.patch("htb_terminal.http.time.sleep"),
        ):
            with self.assertRaises(ApiError) as ctx:
                self.client.get("/machine/paginated")

        self.assertEqual(429, ctx.exception.status)
        self.assertEqual(4, opened.call_count)  # initial attempt + 3 retries

    def test_failed_auth_401_raises_without_retry(self):
        error = _http_error(401, body=b'{"message": "Unauthorized"}')
        with (
            mock.patch("htb_terminal.http.urlopen", side_effect=error) as opened,
            mock.patch("htb_terminal.http.time.sleep") as sleep,
        ):
            with self.assertRaises(ApiError) as ctx:
                self.client.get("/machine/active")

        self.assertEqual(401, ctx.exception.status)
        self.assertIn("Unauthorized", str(ctx.exception))
        self.assertEqual(1, opened.call_count)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
