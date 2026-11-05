from __future__ import annotations

import unittest
from typing import Any

from htb_terminal.services.progress import ProgressService

PROGRESS = {
    "machines": {
        "profile": {
            "machine_owns": {"solved": 3, "total": 558},
            "total_bloods": 0,
        }
    },
    "challenges": {
        "profile": {
            "challenge_owns": {"solved": 104, "total": 860},
            "total_bloods": 0,
        }
    },
    "fortress": {
        "profile": {
            "fortresses": [
                {
                    "id": 6,
                    "name": "Faraday",
                    "owned_flags": 4,
                    "total_flags": 7,
                    "completion_percentage": 57,
                }
            ]
        }
    },
    "prolab": {
        "profile": {
            "prolabs": [
                {
                    "id": 22,
                    "name": "Puppet",
                    "owned_flags": 4,
                    "total_flags": 4,
                    "total_machines": 3,
                    "completion_percentage": 100,
                }
            ]
        }
    },
}


class StubClient:
    def __init__(self, payloads: dict[str, Any]):
        self.payloads = payloads
        self.paths: list[str] = []

    def get(self, path: str, query: dict[str, Any] | None = None, *, version: str | None = None) -> Any:
        self.paths.append(path)
        if path not in self.payloads:
            raise AssertionError(f"unexpected path {path}")
        return self.payloads[path]


def client() -> StubClient:
    payloads = {f"/profile/progress/{kind}/346510": body for kind, body in PROGRESS.items()}
    payloads["/user/info"] = {"info": {"id": 346510, "name": "tester"}}
    payloads["/user/submissions/machines"] = {"submission_machines": [(1, 2, 3)]}
    payloads["/user/submissions/challenges"] = {"submission_challenges": []}
    payloads["/user/connection/status"] = {"status": False, "connection": "not connected"}
    return StubClient(payloads)


class ProgressTests(unittest.TestCase):
    def test_user_id_comes_from_user_info(self) -> None:
        self.assertEqual(346510, ProgressService(client()).user_id())

    def test_machine_and_challenge_counts(self) -> None:
        service = ProgressService(client())
        self.assertEqual(3, service.kind("machines")["solved"])
        self.assertEqual(860, service.kind("challenges")["total"])

    def test_fortress_uses_owned_over_total_flags(self) -> None:
        rows = ProgressService(client()).kind("fortress")["fortresses"]

        self.assertEqual(4, rows[0]["flags"])
        self.assertEqual(7, rows[0]["total"])
        self.assertEqual(57, rows[0]["percent"])

    def test_prolab_keeps_the_machine_count(self) -> None:
        rows = ProgressService(client()).kind("prolab")["prolabs"]

        self.assertEqual(3, rows[0]["machines"])
        self.assertEqual(100, rows[0]["percent"])

    def test_summary_covers_every_category_with_one_user_lookup(self) -> None:
        stub = client()
        summary = ProgressService(stub).summary()

        self.assertEqual(346510, summary["user_id"])
        self.assertEqual({"solved": 3, "total": 558}, summary["machines"])
        self.assertEqual(1, stub.paths.count("/user/info"))

    def test_unknown_kind_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ProgressService(client()).kind("endgame")

    def test_connection_status_is_normalised(self) -> None:
        result = ProgressService(client()).connection()

        self.assertFalse(result["connected"])
        self.assertEqual("not connected", result["state"])


if __name__ == "__main__":
    unittest.main()


class MachineFilterTests(unittest.TestCase):
    ROWS = [
        {"id": 1, "name": "A", "os": "Linux", "difficulty": "Easy"},
        {"id": 2, "name": "B", "os": "Windows", "difficulty": "Insane"},
        {"id": 3, "name": "C", "os": "Linux", "difficulty": "Easy"},
    ]

    def test_difficulty_filter_is_case_insensitive(self) -> None:
        from htb_terminal.handlers import _filter_machine_rows

        self.assertEqual([1, 3], [row["id"] for row in _filter_machine_rows(self.ROWS, difficulty="easy")])

    def test_os_filter(self) -> None:
        from htb_terminal.handlers import _filter_machine_rows

        self.assertEqual([2], [row["id"] for row in _filter_machine_rows(self.ROWS, os_name="Windows")])

    def test_no_filter_returns_everything(self) -> None:
        from htb_terminal.handlers import _filter_machine_rows

        self.assertEqual(3, len(_filter_machine_rows(self.ROWS)))
