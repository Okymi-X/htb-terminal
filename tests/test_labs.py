from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import Any
from unittest import mock

from htb_terminal import cli
from htb_terminal.http import ApiError
from htb_terminal.services.labs import LabService

LABS = {
    "status": True,
    "data": {
        "count": 2,
        "labs": [
            {
                "id": 22,
                "name": "Puppet",
                "pro_machines_count": 3,
                "pro_flags_count": 4,
                "pro_flags_owns_count": 4,
                "state": "free",
                "release_at": "2025-09-30T13:03:32.000000Z",
            },
            {"id": 4, "name": "Dante", "pro_machines_count": 15, "state": "paid"},
        ],
    },
}

FORTRESSES = {
    "status": True,
    "data": [
        {"id": 7, "name": "AWS", "number_of_flags": 10, "owned_flags": 0, "new": True},
        {"id": 6, "name": "Faraday", "number_of_flags": 7, "owned_flags": 4, "new": False},
    ],
}

FORTRESS = {
    "status": True,
    "data": {
        "id": 6,
        "name": "Faraday",
        "ip": "10.13.37.14",
        "points": 110,
        "progress_percent": 57.14,
        "players_completed": 1597,
        "company": {"id": 28, "name": "Faraday", "description": "<p>about</p>"},
        "flags": [
            {"id": 51, "title": "Warmup", "points": 5, "owned": True},
            {"id": 53, "title": "Time to play", "points": 25, "owned": False},
        ],
    },
}

LAB_MACHINES = {
    "status": True,
    "data": [
        {"id": 211, "name": "PUPPET-PM01", "os": "Linux"},
        {"id": 214, "name": "PUPPET-DC01", "os": "Windows"},
    ],
}


class StubClient:
    def __init__(self, payloads: dict[str, Any], error: Exception | None = None):
        self.payloads = payloads
        self.error = error
        self.paths: list[str] = []

    def get(self, path: str, query: dict[str, Any] | None = None, *, version: str | None = None) -> Any:
        self.paths.append(path)
        if self.error is not None:
            raise self.error
        return self.payloads[path]


class LabServiceTests(unittest.TestCase):
    def test_labs_map_the_documented_fields(self) -> None:
        rows = LabService(StubClient({"/prolabs": LABS})).labs()["labs"]

        self.assertEqual(2, len(rows))
        self.assertEqual("Puppet", rows[0]["name"])
        self.assertEqual(3, rows[0]["machines"])
        self.assertEqual(4, rows[0]["flags"])
        self.assertEqual(4, rows[0]["flags_owned"])
        self.assertEqual("free", rows[0]["state"])

    def test_lab_machines_use_the_prolab_route(self) -> None:
        client = StubClient({"/prolab/22/machines": LAB_MACHINES})
        result = LabService(client).lab_machines(22)

        self.assertEqual(["/prolab/22/machines"], client.paths)
        self.assertEqual(["PUPPET-PM01", "PUPPET-DC01"], [row["name"] for row in result["machines"]])

    def test_fortress_rows_carry_flag_counts_not_points(self) -> None:
        rows = LabService(StubClient({"/fortresses": FORTRESSES})).fortresses()["fortresses"]

        self.assertEqual("4/7", rows[1]["progress"])
        self.assertEqual(10, rows[0]["flags"])
        self.assertNotIn("points", rows[0])

    def test_fortress_detail_sums_owned_points(self) -> None:
        result = LabService(StubClient({"/fortress/6": FORTRESS})).fortress(6)

        self.assertEqual(1, result["flags_owned"])
        self.assertEqual(2, result["flags_total"])
        self.assertEqual(5, result["points_earned"])
        self.assertEqual(30, result["points_total"])
        self.assertEqual("Faraday", result["company"]["name"])

    def test_missing_fortress_payload_is_reported(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            LabService(StubClient({"/fortress/9": {"status": False}})).fortress(9)

        self.assertIn("/fortress/<id>", str(ctx.exception))


class LabCliTests(unittest.TestCase):
    def run_cli(self, argv: list[str], payloads: dict[str, Any]) -> str:
        out = io.StringIO()
        with mock.patch.object(cli, "build_client") if hasattr(cli, "build_client") else mock.patch(
            "htb_terminal.cli.HtbApiClient", lambda *a, **k: StubClient(payloads)
        ):
            with redirect_stdout(out):
                cli.main(argv)
        return out.getvalue()

    def test_prolab_list_prints_a_table(self) -> None:
        output = self.run_cli(["prolab", "list", "--color", "never"], {"/prolabs": LABS})

        self.assertIn("Puppet", output)
        self.assertIn("machines", output)

    def test_fortress_info_prints_flags_and_totals(self) -> None:
        output = self.run_cli(["fortress", "info", "6", "--color", "never"], {"/fortress/6": FORTRESS})

        self.assertIn("Faraday", output)
        self.assertIn("Warmup", output)
        self.assertIn("points: 5/30", output)

    def test_api_error_is_surfaced_not_swallowed(self) -> None:
        client = StubClient({}, error=ApiError(404, "HTTP 404: not found"))
        with mock.patch("htb_terminal.cli.HtbApiClient", lambda *a, **k: client):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                code = cli.main(["prolab", "list", "--color", "never"])

        self.assertEqual(1, code)
        self.assertIn("404", errors.getvalue())


LAB_INFO = {
    "status": True,
    "data": {"id": 22, "name": "Puppet", "version": "1.0", "pro_machines_count": 3, "pro_flags_count": 4},
}

LAB_FLAGS = {
    "status": True,
    "data": [
        {"id": 295, "title": "Sleep", "points": 30, "owned": True},
        {"id": 298, "title": "Nightmare", "points": 30, "owned": False},
    ],
}


class LabDetailTests(unittest.TestCase):
    def test_info_uses_the_prolab_info_route(self) -> None:
        client = StubClient({"/prolab/22/info": LAB_INFO})
        result = LabService(client).lab_info(22)

        self.assertEqual(["/prolab/22/info"], client.paths)
        self.assertEqual("Puppet", result["name"])
        self.assertEqual(3, result["machines"])

    def test_flags_totals_split_owned_and_all(self) -> None:
        result = LabService(StubClient({"/prolab/22/flags": LAB_FLAGS})).lab_flags(22)

        self.assertEqual(1, result["owned"])
        self.assertEqual(2, result["total"])
        self.assertEqual(30, result["points_earned"])
        self.assertEqual(60, result["points_total"])


class _PostClient:
    def __init__(self, response: Any = None, error: Exception | None = None):
        self.response = response if response is not None else {"message": "Correct flag!"}
        self.error = error
        self.posts: list[tuple[str, dict[str, Any] | None]] = []

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        self.posts.append((path, payload))
        if self.error is not None:
            raise self.error
        return self.response


class FlagSubmissionTests(unittest.TestCase):
    def test_fortress_flag_posts_to_the_fortress_route(self) -> None:
        client = _PostClient()
        result = LabService(client).own_fortress_flag(7, "HTB{test}")

        self.assertEqual("/fortress/7/flag", client.posts[0][0])
        self.assertEqual({"flag": "HTB{test}"}, client.posts[0][1])
        self.assertTrue(result["accepted"])

    def test_prolab_flag_posts_to_the_prolab_route(self) -> None:
        client = _PostClient({"message": "Correct flag"})
        result = LabService(client).own_lab_flag(22, "HTB{test}")

        self.assertEqual("/prolab/22/flag", client.posts[0][0])
        self.assertIn("Correct", result["message"])

    def test_a_rejected_flag_raises_with_the_server_message(self) -> None:
        client = _PostClient(error=ApiError(400, '{"status": false, "message": "Wrong flag"}'))

        with self.assertRaises(RuntimeError) as ctx:
            LabService(client).own_fortress_flag(7, "nope")

        self.assertIn("Wrong flag", str(ctx.exception))

    def test_empty_flag_is_refused_before_any_request(self) -> None:
        client = _PostClient()

        with self.assertRaises(ValueError):
            LabService(client).own_lab_flag(22, "   ")

        self.assertEqual([], client.posts)
