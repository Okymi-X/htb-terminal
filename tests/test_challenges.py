from __future__ import annotations

import io
import json
import os
import struct
import tempfile
import unittest
import zipfile
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.error import HTTPError

from htb_terminal import cli, containers, handlers
from htb_terminal.http import ApiError, HtbApiClient
from htb_terminal.services.challenges import (
    ChallengeFilters,
    ChallengeService,
    challenge_row,
    challenge_summary,
    download_target,
    human_size,
)
from htb_terminal.services.paging import PageCache


def page(items: list[dict[str, Any]], *, page_no: int = 1, last_page: int = 1) -> dict[str, Any]:
    return {
        "data": items,
        "links": {"next": f"https://example.test/x?page={page_no + 1}" if page_no < last_page else None},
        "meta": {"current_page": page_no, "last_page": last_page},
    }


def chal(ident: int, **overrides: Any) -> dict[str, Any]:
    item = {
        "id": ident,
        "name": f"Challenge {ident}",
        "difficulty": "Easy",
        "state": "active",
        "category_name": "Web",
        "solves": 10,
        "is_owned": False,
        "rating": 4.5,
    }
    item.update(overrides)
    return item


class StubClient:
    """Records calls and replays canned payloads, like tests/test_machines.py."""

    def __init__(self, pages: dict[int, Any], *, info: dict[int, Any] | None = None):
        self.pages = pages
        self.info = info or {}
        self.page_queries: list[dict[str, Any]] = []
        self.posts: list[tuple[str, dict[str, Any] | None]] = []
        self.post_response: Any = {"message": "ok"}
        self.post_error: Exception | None = None
        self.info_calls: list[int] = []

    def get(self, path: str, query: dict[str, Any] | None = None, *, version: str | None = None) -> Any:
        if path == "/challenges":
            page_no = int((query or {}).get("page", 1))
            self.page_queries.append(dict(query or {}))
            value = self.pages[page_no]
            if isinstance(value, Exception):
                raise value
            return value
        if path.startswith("/challenge/info/"):
            cid = int(path.rsplit("/", 1)[1])
            self.info_calls.append(cid)
            value = self.info.get(cid, {})
            if isinstance(value, Exception):
                raise value
            return value
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path: str, data: dict[str, Any] | None = None, *, version: str | None = None) -> Any:
        self.posts.append((path, data))
        if self.post_error is not None:
            raise self.post_error
        return self.post_response

    def presigned_location(self, path: str, query=None, *, version=None) -> str:
        self.posts.append((f"presigned:{path}", None))
        return "https://storage.example.test/ch806.zip?signature=fake"

    def fetch_to_file(self, url: str, destination: Path) -> int:
        self.posts.append((f"fetch:{url}", None))
        payload = zipfile_payload()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return len(payload)


def zipfile_payload() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("readme.txt", "hello" * 64, compress_type=zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def encrypted_zip_payload() -> bytes:
    """A zip whose entries claim to be encrypted, like HTB challenge archives.

    ``zipfile`` cannot write encrypted archives, so flip the encryption bit in
    the local and central headers; extracting with any password then fails with
    the same "Bad password" error a real archive raises.
    """
    data = bytearray(zipfile_payload())
    struct.pack_into("<H", data, 6, struct.unpack_from("<H", data, 6)[0] | 0x1)
    position = 0
    while (index := data.find(b"PK\x01\x02", position)) != -1:
        struct.pack_into("<H", data, index + 8, struct.unpack_from("<H", data, index + 8)[0] | 0x1)
        position = index + 4
    return bytes(data)


class _BrokenResponse:
    def __init__(self) -> None:
        self._reads = 0

    def read(self, size: int | None = None) -> bytes:
        self._reads += 1
        if self._reads > 1:
            raise OSError("connection reset")
        return b"PK\x03\x04partial"

    def __enter__(self) -> _BrokenResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class TmpConfigMixin(unittest.TestCase):
    """Point the config, cache, and container-state files at a temp directory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cache_dir = self.root / "config" / "htb-terminal" / "cache"


class ChallengeListTests(TmpConfigMixin):
    def service(self, client: StubClient, *, ttl: float = 300.0) -> ChallengeService:
        return ChallengeService(client, cache=PageCache(self.cache_dir / "challenges.json", ttl=ttl))

    def test_walks_every_page_until_the_last(self) -> None:
        client = StubClient(
            {
                1: page([chal(1), chal(2)], page_no=1, last_page=3),
                2: page([chal(3), chal(4)], page_no=2, last_page=3),
                3: page([chal(5)], page_no=3, last_page=3),
            }
        )
        result = self.service(client).list(limit=None)

        self.assertEqual([1, 2, 3, 4, 5], [row["id"] for row in result["challenges"]])
        self.assertEqual(3, result["meta"]["pages_scanned"])
        self.assertEqual([1, 2, 3], [query["page"] for query in client.page_queries])
        self.assertEqual(100, client.page_queries[0]["per_page"])

    def test_limit_stops_paging_and_reports_truncation(self) -> None:
        client = StubClient({1: page([chal(1), chal(2), chal(3)], page_no=1, last_page=4)})
        result = self.service(client).list(limit=2)

        self.assertEqual([1, 2], [row["id"] for row in result["challenges"]])
        self.assertTrue(result["meta"]["truncated"])
        self.assertEqual(1, len(client.page_queries))

    def test_state_and_difficulty_go_to_the_api(self) -> None:
        client = StubClient({1: page([chal(1, difficulty="Easy")])})
        self.service(client).list(
            ChallengeFilters(state="active", difficulty="easy", category="Web"),
            limit=None,
        )

        query = client.page_queries[0]
        self.assertEqual("active", query["state"])
        self.assertEqual("easy", query["difficulty[]"])
        self.assertNotIn("category", query)

    def test_owned_and_search_filter_locally_on_is_owned(self) -> None:
        owned_client = StubClient({1: page([chal(1, is_owned=True), chal(2, is_owned=False)])})
        unowned_client = StubClient({1: page([chal(1, is_owned=True), chal(2)])})
        search_client = StubClient({1: page([chal(1, name="Broken Shell"), chal(2)])})

        # Each client returns a different payload, so bypass the shared page
        # cache: it stores raw server pages, not filtered rows.
        owned = self.service(owned_client).list(ChallengeFilters(owned=True), limit=None, use_cache=False)
        unowned = self.service(unowned_client).list(
            ChallengeFilters(owned=False), limit=None, use_cache=False
        )
        found = self.service(search_client).list(
            ChallengeFilters(search="broken"), limit=None, use_cache=False
        )

        self.assertEqual([1], [row["id"] for row in owned["challenges"]])
        self.assertEqual([2], [row["id"] for row in unowned["challenges"]])
        self.assertEqual([1], [row["id"] for row in found["challenges"]])

    def test_local_difficulty_match_normalizes_very_easy(self) -> None:
        client = StubClient(
            {1: page([chal(1, difficulty="Very Easy"), chal(2, difficulty="Easy")])}
        )
        result = self.service(client).list(
            ChallengeFilters(difficulty="very-easy"), limit=None, use_cache=False
        )

        self.assertEqual([1], [row["id"] for row in result["challenges"]])

    def test_server_filter_rejection_falls_back_to_local_filtering(self) -> None:
        client = StubClient({})
        client.get = mock.Mock(  # type: ignore[method-assign]
            side_effect=[
                ApiError(422, "HTTP 422: bad filter"),
                page([chal(1, difficulty="Easy"), chal(2, difficulty="Hard")]),
            ]
        )
        with redirect_stderr(io.StringIO()) as errors:
            result = self.service(client).list(ChallengeFilters(difficulty="easy"), limit=None)

        self.assertEqual([1], [row["id"] for row in result["challenges"]])
        self.assertIn("filtering locally", errors.getvalue())

    def test_429_backoff_then_success(self) -> None:
        client = HtbApiClient("https://example.test/api/v4", "token", max_retries=2)
        responses = [_http_error(429), _http_error(429), _ok_response(page([chal(1)]))]
        sleeps: list[float] = []
        with (
            mock.patch("htb_terminal.http.urlopen", side_effect=responses),
            mock.patch("htb_terminal.http.time.sleep", side_effect=sleeps.append),
            redirect_stderr(io.StringIO()) as errors,
        ):
            result = ChallengeService(
                client, cache=PageCache(self.cache_dir / "challenges.json")
            ).list(limit=None)

        self.assertEqual([1], [row["id"] for row in result["challenges"]])
        self.assertEqual([1.0, 2.0], sleeps)
        self.assertIn("rate limited", errors.getvalue())

    def test_429_exhaustion_serves_the_cached_page(self) -> None:
        # A negative TTL forces the read path to treat the cached page as stale,
        # which is exactly the state a 429-exhausted retry falls back to.
        cache = PageCache(self.cache_dir / "challenges.json", ttl=-1)
        self.service(StubClient({1: page([chal(7)])})).list(limit=None)

        flaky = StubClient({1: ApiError(429, "HTTP 429: rate limit retries exhausted")})
        with redirect_stderr(io.StringIO()) as errors:
            result = ChallengeService(flaky, cache=cache).list(limit=None)

        self.assertEqual([7], [row["id"] for row in result["challenges"]])
        self.assertEqual(1, result["meta"]["cached_pages"])
        self.assertIn("cached copy", errors.getvalue())

    def test_no_cache_flag_refetches(self) -> None:
        client = StubClient({1: page([chal(1)])})
        service = self.service(client)
        service.list(limit=None)
        service.list(limit=None, use_cache=False)

        self.assertEqual(2, len(client.page_queries))

    def test_a_repeated_page_stops_the_walk(self) -> None:
        repeated = {number: page([chal(1)], page_no=1, last_page=9) for number in range(1, 6)}
        result = self.service(StubClient(repeated)).list(limit=None, max_pages=5)

        self.assertEqual(2, result["meta"]["pages_scanned"])
        self.assertEqual(1, len(result["challenges"]))

    def test_page_cap_is_reported(self) -> None:
        pages = {
            number: page([chal(number)], page_no=number, last_page=9) for number in range(1, 6)
        }
        result = self.service(StubClient(pages)).list(limit=None, max_pages=3)

        self.assertTrue(result["meta"]["page_cap_reached"])
        self.assertEqual([1, 2, 3], [row["id"] for row in result["challenges"]])


class ChallengeInfoTests(unittest.TestCase):
    def test_summary_reports_play_info_and_file(self) -> None:
        summary = challenge_summary(
            {
                "id": 806,
                "name": "SpookyPass",
                "category_name": "Reversing",
                "difficulty": "Very Easy",
                "state": "retired_free",
                "points": "20",
                "solves": 30943,
                "authUserSolve": False,
                "play_methods": ["download"],
                "file_name": "SpookyPass.zip",
                "file_size": 2973,
                "description": "It&#039;s spooky",
                "play_info": {"status": None, "ip": None, "ports": []},
            }
        )["challenge"]

        self.assertEqual(20, summary["points"])
        self.assertEqual("SpookyPass.zip", summary["file"]["name"])
        self.assertEqual("2.9 KB", summary["file"]["size"])
        self.assertEqual(["download"], summary["play_methods"])
        self.assertEqual("It's spooky", summary["description"])
        self.assertIsNone(summary["play_info"])

    def test_summary_includes_container_play_info(self) -> None:
        summary = challenge_summary(
            {
                "id": 883,
                "name": "Broken Shell",
                "docker_ip": "154.57.164.71",
                "docker_ports": [41891],
                "play_info": {"status": "ready", "ip": "154.57.164.71", "ports": [41891]},
            }
        )["challenge"]

        self.assertEqual("ready", summary["play_info"]["status"])
        self.assertEqual([41891], summary["play_info"]["ports"])

    def test_human_size(self) -> None:
        self.assertEqual("512 B", human_size(512))
        self.assertEqual("1.0 KB", human_size(1024))
        self.assertIsNone(human_size(None))


class ChallengeDownloadTests(TmpConfigMixin):
    def test_default_target_is_challenges_ch_id(self) -> None:
        self.assertEqual(Path("challenges/ch806/ch806.zip"), download_target(806, None))
        self.assertEqual(Path("/tmp/out/ch806.zip"), download_target(806, Path("/tmp/out")))

    def test_download_verifies_zip_and_extracts(self) -> None:
        client = StubClient({})
        result = ChallengeService(client).download(806, out=self.root / "ch806.zip", extract=True)

        self.assertTrue(result["output"].endswith("ch806.zip"))
        self.assertGreater(result["size"], 0)
        self.assertEqual(1, result["files"])
        self.assertTrue((self.root / "ch806" / "readme.txt").exists())
        self.assertEqual("presigned:/challenge/download/806", client.posts[0][0])

    def test_download_rejects_a_non_zip_payload(self) -> None:
        client = StubClient({})
        client.fetch_to_file = lambda url, destination: _write(destination, b"<html>nope</html>")

        with self.assertRaises(RuntimeError) as ctx:
            ChallengeService(client).download(806, out=self.root / "ch806.zip")

        self.assertIn("not a zip archive", str(ctx.exception))

    def test_wrong_password_is_reported_with_a_hint(self) -> None:
        client = StubClient({})
        client.fetch_to_file = lambda url, destination: _write(destination, encrypted_zip_payload())
        with self.assertRaises(RuntimeError) as ctx:
            ChallengeService(client).download(
                806, out=self.root / "ch806.zip", extract=True, password="wrong"
            )

        self.assertIn("Bad password", str(ctx.exception))
        self.assertIn("--password", str(ctx.exception))


def _write(destination: Path, payload: bytes) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return len(payload)


class _FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str], status: int = 200):
        self._body = io.BytesIO(body)
        self.headers = headers
        self.status = status

    def read(self, size: int | None = None) -> bytes:
        return self._body.read(size)

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class PresignedDownloadTests(unittest.TestCase):
    """The S3 hop must not carry the API bearer token."""

    def test_redirect_is_followed_without_the_authorization_header(self) -> None:
        client = HtbApiClient("https://example.test/api/v4", "dummy-api-token")
        redirect = _http_error(302, headers={"Location": "https://storage.example.test/ch806.zip?sig=fake"})
        seen: list[Any] = []

        def fake_open(request, timeout):
            seen.append(request)
            raise redirect

        def fake_urlopen(request, timeout):
            seen.append(request)
            return _FakeResponse(b"PK\x03\x04payload", headers={})

        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "ch806.zip"
            with (
                mock.patch("htb_terminal.http._open_without_redirects", side_effect=fake_open),
                mock.patch("htb_terminal.http.urlopen", side_effect=fake_urlopen),
            ):
                location = client.presigned_location("/challenge/download/806")
                size = client.fetch_to_file(location, destination)

            self.assertEqual(b"PK\x03\x04payload", destination.read_bytes())

        self.assertEqual("https://storage.example.test/ch806.zip?sig=fake", location)
        self.assertEqual(len(b"PK\x03\x04payload"), size)
        api_request, s3_request = seen
        self.assertEqual("Bearer dummy-api-token", api_request.headers["Authorization"])
        self.assertNotIn("Authorization", s3_request.headers)
        self.assertEqual("https://storage.example.test/ch806.zip?sig=fake", s3_request.full_url)

    def test_partial_download_is_removed_on_failure(self) -> None:
        client = HtbApiClient("https://example.test/api/v4", "token")
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "ch806.zip"
            with mock.patch("htb_terminal.http.urlopen", return_value=_BrokenResponse()):
                with self.assertRaises(ApiError):
                    client.fetch_to_file("https://storage.example.test/x.zip", destination)

            self.assertFalse(destination.exists())

    def test_missing_redirect_is_an_api_error(self) -> None:
        client = HtbApiClient("https://example.test/api/v4", "token")
        with mock.patch(
            "htb_terminal.http._open_without_redirects",
            return_value=_FakeResponse(b"", headers={}),
        ):
            with self.assertRaises(ApiError) as ctx:
                client.presigned_location("/challenge/download/1")

        self.assertIn("did not return a download redirect", str(ctx.exception))


def _ok_response(payload: Any) -> mock.MagicMock:
    response = mock.MagicMock()
    response.status = 200
    response.headers.get.return_value = "application/json"
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def _http_error(code: int, body: bytes = b"", headers: dict[str, str] | None = None) -> HTTPError:
    return HTTPError(
        url="https://example.test/api/v4/challenges",
        code=code,
        msg="error",
        hdrs=headers or {},
        fp=io.BytesIO(body),
    )


class ContainerSlotTests(TmpConfigMixin):
    def store(self) -> containers.ContainerStore:
        return containers.ContainerStore(self.root / "config" / "htb-terminal" / "containers.json")

    def info_payload(self, cid: int, *, status: str | None = "ready") -> dict[str, Any]:
        return {
            "challenge": {
                "id": cid,
                "name": f"challenge {cid}",
                "play_info": {
                    "status": status,
                    "ip": "10.10.10.10" if status == "ready" else None,
                    "ports": [31337],
                    "expires_at": "2999-01-01T00:00:00Z",
                },
            }
        }

    def track_running(self, cid: int = 111) -> None:
        self.store().track(
            containers.ContainerEntry(
                challenge_id=cid,
                status="ready",
                ip="10.10.10.10",
                ports=(31337,),
                expires_at="2999-01-01T00:00:00Z",
            )
        )

    def test_start_refuses_while_another_container_is_tracked(self) -> None:
        self.track_running()
        client = StubClient({}, info={222: self.info_payload(222)})

        with self.assertRaises(RuntimeError) as ctx:
            ChallengeService(client).start(222)

        self.assertIn("already running", str(ctx.exception))
        self.assertIn("--force", str(ctx.exception))
        self.assertEqual([], client.posts)  # nothing was started

    def test_force_stops_the_previous_container_before_starting(self) -> None:
        self.track_running()
        client = StubClient({}, info={222: self.info_payload(222)})

        with redirect_stderr(io.StringIO()):
            result = ChallengeService(client).start(222, force=True)

        self.assertEqual(
            [("/container/stop", {"challenge_id": 111}), ("/container/start", {"challenge_id": 222})],
            client.posts,
        )
        self.assertEqual(222, result["challenge_id"])
        self.assertEqual("10.10.10.10", result["ip"])
        self.assertEqual([222], [entry.challenge_id for entry in self.store().load()])

    def test_start_polls_until_ready(self) -> None:
        pending = {"challenge": {"id": 222, "play_info": {"status": None, "ip": None}}}
        ready = self.info_payload(222)
        calls = {"n": 0}

        class PollingClient(StubClient):
            def get(self, path, query=None, *, version=None):
                calls["n"] += 1
                return pending if calls["n"] < 3 else ready

        with (
            mock.patch("htb_terminal.services.challenges.time.sleep") as sleep,
            redirect_stderr(io.StringIO()) as errors,
        ):
            result = ChallengeService(PollingClient({})).start(222)

        self.assertEqual(2, sleep.call_count)
        self.assertIn("waiting for container", errors.getvalue())
        self.assertEqual("ready", result["status"])
        self.assertEqual([31337], result["ports"])

    def test_a_timed_out_start_still_holds_the_slot(self) -> None:
        client = StubClient({}, info={222: self.info_payload(222, status=None)})

        with mock.patch(
            "htb_terminal.services.challenges.time.sleep"
        ), redirect_stderr(io.StringIO()):
            with self.assertRaises(RuntimeError):
                ChallengeService(client).start(222, wait=1, interval=1)

        # The container may still be booting, so the slot stays taken.
        self.assertEqual([222], [entry.challenge_id for entry in self.store().running()])

    def test_start_times_out_with_a_diagnosis(self) -> None:
        client = StubClient({}, info={222: self.info_payload(222, status=None)})

        with mock.patch(
            "htb_terminal.services.challenges.time.sleep"
        ), redirect_stderr(io.StringIO()):
            with self.assertRaises(RuntimeError) as ctx:
                ChallengeService(client).start(222, wait=1, interval=1)

        self.assertIn("did not become ready", str(ctx.exception))

    def test_expired_tracking_does_not_block_a_new_start(self) -> None:
        self.store().track(
            containers.ContainerEntry(
                challenge_id=111,
                status="ready",
                ip="10.10.10.10",
                expires_at="2000-01-01T00:00:00Z",
            )
        )
        client = StubClient({}, info={222: self.info_payload(222)})

        result = ChallengeService(client).start(222)

        self.assertEqual(222, result["challenge_id"])
        self.assertIn(222, [entry.challenge_id for entry in self.store().load()])

    def test_status_reports_tracked_instance_with_time_to_expiry(self) -> None:
        self.track_running()
        client = StubClient({}, info={111: self.info_payload(111)})

        rows = ChallengeService(client).status()["containers"]

        self.assertEqual(1, len(rows))
        self.assertEqual(111, rows[0]["id"])
        self.assertEqual("ready", rows[0]["status"])
        self.assertEqual("31337", rows[0]["ports_text"])
        self.assertTrue(rows[0]["tracked"])
        self.assertIsNotNone(rows[0]["expires"])

    def test_status_reports_an_untracked_live_container(self) -> None:
        client = StubClient({}, info={333: self.info_payload(333)})

        rows = ChallengeService(client).status(333)["containers"]

        self.assertEqual(333, rows[0]["id"])
        self.assertFalse(rows[0]["tracked"])
        self.assertEqual("ready", rows[0]["status"])

    def test_status_for_an_id_with_no_play_state_is_an_error(self) -> None:
        client = StubClient({}, info={999: {"challenge": {"id": 999, "play_info": {}}}})

        with self.assertRaises(RuntimeError) as ctx:
            ChallengeService(client).status(999)

        self.assertIn("no play state", str(ctx.exception))

    def test_status_without_tracking_is_an_error(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            ChallengeService(StubClient({})).status()

        self.assertIn("No tracked challenge containers", str(ctx.exception))

    def test_stop_defaults_to_the_tracked_container(self) -> None:
        self.track_running()
        client = StubClient({})

        result = ChallengeService(client).stop()

        self.assertEqual({"challenge_id": 111, "message": "ok"}, result)
        self.assertEqual([("/container/stop", {"challenge_id": 111})], client.posts)
        self.assertEqual([], self.store().load())


class ChallengeOwnTests(unittest.TestCase):
    def test_accepted_flag_returns_the_server_message(self) -> None:
        client = StubClient({})
        client.post_response = {"message": "Congratulations! You solved Broken Shell."}

        result = ChallengeService(client).own(883, "HTB{ok}")

        self.assertTrue(result["accepted"])
        self.assertIn("Congratulations", result["message"])
        self.assertEqual(
            [("/challenge/own", {"challenge_id": 883, "flag": "HTB{ok}"})],
            client.posts,
        )

    def test_rejected_flag_raises(self) -> None:
        client = StubClient({})
        client.post_response = {"message": "Incorrect flag"}

        with self.assertRaises(RuntimeError) as ctx:
            ChallengeService(client).own(883, "HTB{nope}")

        self.assertIn("Incorrect flag", str(ctx.exception))

    def test_rejected_flag_exits_non_zero_through_the_cli(self) -> None:
        with (
            mock.patch("htb_terminal.cli.load_config"),
            mock.patch("htb_terminal.handlers._challenge_service") as service,
            redirect_stderr(io.StringIO()) as errors,
        ):
            service.return_value.own.side_effect = RuntimeError("Challenge 883: Incorrect flag")
            code = cli.main(["challenge", "own", "883", "--flag", "HTB{nope}"])

        self.assertEqual(1, code)
        self.assertIn("Incorrect flag", errors.getvalue())


class ChallengeTableTests(TmpConfigMixin):
    def test_json_output_is_machine_readable(self) -> None:
        with (
            mock.patch("htb_terminal.cli.load_config"),
            mock.patch("htb_terminal.handlers._challenge_service") as service,
            redirect_stdout(io.StringIO()) as out,
        ):
            service.return_value.list.return_value = {
                "challenges": [challenge_row(chal(883))],
                "count": 1,
                "meta": {"pages_scanned": 1, "cached_pages": 0, "truncated": False},
            }
            code = cli.main(["challenge", "list", "--json"])

        payload = json.loads(out.getvalue())
        self.assertEqual(0, code)
        self.assertEqual(1, payload["count"])
        self.assertIn("owned", payload["challenges"][0])

    def test_handler_maps_filters_and_limit(self) -> None:
        args = Namespace(
            state="active",
            difficulty="easy",
            category=None,
            owned=True,
            search=None,
            limit=5,
            all=False,
            no_cache=False,
            json=False,
            color="never",
            wide=False,
        )
        with (
            mock.patch("htb_terminal.handlers._challenge_service") as service,
            redirect_stdout(io.StringIO()),
        ):
            service.return_value.list.return_value = {
                "challenges": [],
                "count": 0,
                "meta": {"truncated": False},
            }
            handlers.challenge_list(args, mock.Mock())

        call = service.return_value.list.call_args
        self.assertEqual(ChallengeFilters(state="active", difficulty="easy", owned=True), call.args[0])
        self.assertEqual(5, call.kwargs["limit"])
        self.assertTrue(call.kwargs["use_cache"])

    def test_truncation_note_goes_to_stderr(self) -> None:
        args = Namespace(
            state=None,
            difficulty=None,
            category=None,
            owned=None,
            search=None,
            limit=2,
            all=False,
            no_cache=False,
            json=False,
            color="never",
            wide=False,
        )
        with (
            mock.patch("htb_terminal.handlers._challenge_service") as service,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as errors,
        ):
            service.return_value.list.return_value = {
                "challenges": [challenge_row(chal(1))],
                "count": 1,
                "meta": {"truncated": True, "limit": 2, "pages_scanned": 1},
            }
            handlers.challenge_list(args, mock.Mock())

        self.assertIn("--all", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
