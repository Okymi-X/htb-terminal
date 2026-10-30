from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

from htb_terminal import cli
from htb_terminal.http import ApiError
from htb_terminal.services.paging import PageCache
from htb_terminal.services.sherlocks import (
    SherlockFilters,
    SherlockService,
    sherlock_row,
    task_row,
)


def page(items: list[dict[str, Any]], *, page_no: int = 1, last_page: int = 1) -> dict[str, Any]:
    return {
        "data": items,
        "links": {"next": None if page_no >= last_page else f"...page={page_no + 1}"},
        "meta": {"current_page": page_no, "last_page": last_page},
    }


def sherlock(ident: int, **overrides: Any) -> dict[str, Any]:
    item = {
        "id": ident,
        "name": f"Sherlock {ident}",
        "difficulty": "Easy",
        "state": "active",
        "category_name": "DFIR",
        "solves": 100,
        "is_owned": False,
        "progress": 0,
    }
    item.update(overrides)
    return item


TASKS = {
    "data": [
        {
            "id": 2880,
            "title": "Task 1",
            "description": "What is the attacker IP?",
            "hint": "Look at auth.log",
            "masked_flag": "x.x.x.x",
            "completed": False,
            "prerequisite_id": None,
        },
        {
            "id": 2881,
            "title": "Task 2",
            "description": "Which account was compromised?",
            "hint": "Successful logins",
            "masked_flag": "text",
            "completed": False,
            "prerequisite_id": 2880,
        },
    ]
}


class StubClient:
    def __init__(self, *, pages: dict[int, Any] | None = None, tasks: Any = None, progress: Any = None):
        self.pages = pages or {}
        self.tasks_payload = TASKS if tasks is None else tasks
        self.progress_payload = progress or {
            "data": {
                "is_owned": False,
                "progress": 50,
                "total_tasks": 8,
                "tasks_answered": 4,
                "own_rank": None,
            }
        }
        self.page_queries: list[dict[str, Any]] = []
        self.posts: list[tuple[str, dict[str, Any] | None]] = []
        self.post_error: Exception | None = None
        self.post_response: Any = {"message": "Correct answer!"}

    def get(self, path: str, query: dict[str, Any] | None = None, *, version: str | None = None) -> Any:
        if path == "/sherlocks":
            page_no = int((query or {}).get("page", 1))
            self.page_queries.append(dict(query or {}))
            value = self.pages[page_no]
            if isinstance(value, Exception):
                raise value
            return value
        if path.endswith("/tasks"):
            return self.tasks_payload
        if path.endswith("/progress"):
            return self.progress_payload
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path: str, data: dict[str, Any] | None = None, *, version: str | None = None) -> Any:
        self.posts.append((path, data))
        if self.post_error is not None:
            raise self.post_error
        return self.post_response


class SherlockTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def service(self, client: StubClient) -> SherlockService:
        return SherlockService(
            client,
            cache=PageCache(self.root / "config" / "htb-terminal" / "cache" / "sherlocks.json"),
        )


class SherlockListTests(SherlockTestCase):
    def test_pages_and_filters_server_side(self) -> None:
        client = StubClient(
            pages={
                1: page([sherlock(1)], page_no=1, last_page=2),
                2: page([sherlock(2)], page_no=2, last_page=2),
            }
        )
        result = self.service(client).list(
            SherlockFilters(state="active", difficulty="easy"), limit=None
        )

        self.assertEqual([1, 2], [row["id"] for row in result["sherlocks"]])
        self.assertEqual("active", client.page_queries[0]["state"])
        self.assertEqual("easy", client.page_queries[0]["difficulty[]"])
        self.assertEqual(2, result["meta"]["pages_scanned"])

    def test_owned_filter_is_local(self) -> None:
        client = StubClient(pages={1: page([sherlock(1, is_owned=False), sherlock(2, is_owned=True)])})
        result = self.service(client).list(SherlockFilters(owned=True), limit=None, use_cache=False)

        self.assertEqual([2], [row["id"] for row in result["sherlocks"]])

    def test_very_easy_difficulty_matches_locally(self) -> None:
        client = StubClient(
            pages={1: page([sherlock(1, difficulty="Very Easy"), sherlock(2, difficulty="Easy")])}
        )
        result = self.service(client).list(
            SherlockFilters(difficulty="very-easy"), limit=None, use_cache=False
        )

        self.assertEqual([1], [row["id"] for row in result["sherlocks"]])

    def test_rate_limited_page_falls_back_to_cache(self) -> None:
        cache = PageCache(
            self.root / "config" / "htb-terminal" / "cache" / "sherlocks.json", ttl=-1
        )
        self.service(StubClient(pages={1: page([sherlock(4)])})).list(limit=None)

        flaky = StubClient(pages={1: ApiError(429, "HTTP 429: exhausted")})
        with redirect_stderr(io.StringIO()) as errors:
            result = SherlockService(flaky, cache=cache).list(limit=None)

        self.assertEqual([4], [row["id"] for row in result["sherlocks"]])
        self.assertIn("cached copy", errors.getvalue())


class SherlockTaskTests(SherlockTestCase):
    def test_tasks_come_from_the_tasks_endpoint(self) -> None:
        result = self.service(StubClient()).tasks(631)

        self.assertEqual(631, result["sherlock_id"])
        self.assertEqual([2880, 2881], [task["id"] for task in result["tasks"]])
        self.assertEqual("What is the attacker IP?", result["tasks"][0]["question"])
        self.assertEqual("x.x.x.x", result["tasks"][0]["answer_format"])
        self.assertEqual(2880, result["tasks"][1]["prerequisite_id"])
        self.assertNotIn("hint", result["tasks"][0])

    def test_hints_are_opt_in(self) -> None:
        result = self.service(StubClient()).tasks(631, include_hints=True)

        self.assertEqual("Look at auth.log", result["tasks"][0]["hint"])

    def test_empty_task_payload_is_reported_not_invented(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self.service(StubClient(tasks={"data": []})).tasks(999)

        self.assertIn("returned no tasks", str(ctx.exception))
        self.assertIn("do not carry tasks", str(ctx.exception))

    def test_task_row_keeps_the_completed_flag(self) -> None:
        row = task_row({"id": 5, "completed": True})

        self.assertTrue(row["completed"])
        self.assertIsNone(row["question"])


class SherlockAnswerTests(SherlockTestCase):
    def test_accepted_answer_posts_the_flag(self) -> None:
        client = StubClient()
        result = self.service(client).answer(631, 2880, "10.0.0.5")

        self.assertTrue(result["accepted"])
        self.assertEqual(
            [("/sherlocks/631/tasks/2880/flag", {"flag": "10.0.0.5"})],
            client.posts,
        )

    def test_wrong_answer_is_surfaced_as_wrong(self) -> None:
        client = StubClient()
        client.post_error = ApiError(400, "HTTP 400: Incorrect flag", {"message": "Incorrect flag"})

        with self.assertRaises(RuntimeError) as ctx:
            self.service(client).answer(631, 2880, "nope")

        self.assertIn("Wrong answer for task 2880", str(ctx.exception))
        self.assertIn("Incorrect flag", str(ctx.exception))

    def test_locked_task_is_surfaced_distinctly(self) -> None:
        client = StubClient()
        client.post_error = ApiError(403, "HTTP 403: forbidden", {"message": "Task locked"})

        with self.assertRaises(RuntimeError) as ctx:
            self.service(client).answer(631, 2881, "nope")

        message = str(ctx.exception)
        self.assertIn("locked or not available", message)
        self.assertIn("prerequisite", message)

    def test_unknown_task_points_at_the_tasks_command(self) -> None:
        client = StubClient()
        client.post_error = ApiError(404, "HTTP 404", {"message": "No results for this task"})

        with self.assertRaises(RuntimeError) as ctx:
            self.service(client).answer(631, 999999, "x")

        self.assertIn("htb sherlock tasks 631", str(ctx.exception))

    def test_accepted_message_in_body_marks_success(self) -> None:
        client = StubClient()
        client.post_response = {"message": "Correct! Task solved."}

        result = self.service(client).answer(631, 2880, "10.0.0.5")

        self.assertEqual("Correct! Task solved.", result["message"])

    def test_rejected_message_in_a_200_body_raises(self) -> None:
        client = StubClient()
        client.post_response = {"message": "Incorrect flag"}

        with self.assertRaises(RuntimeError):
            self.service(client).answer(631, 2880, "nope")


class SherlockProgressTests(SherlockTestCase):
    def test_progress_reports_answered_and_total(self) -> None:
        result = self.service(StubClient()).progress(631)

        self.assertEqual(
            {"id": 631, "answered": 4, "total": 8, "progress": 50, "owned": False, "own_rank": None},
            result["sherlock"],
        )


class SherlockCliTests(SherlockTestCase):
    def test_json_list_is_machine_readable(self) -> None:
        with (
            mock.patch("htb_terminal.cli.load_config"),
            mock.patch("htb_terminal.handlers._sherlock_service") as service,
            redirect_stdout(io.StringIO()) as out,
        ):
            service.return_value.list.return_value = {
                "sherlocks": [sherlock_row(sherlock(631))],
                "count": 1,
                "meta": {"pages_scanned": 1, "cached_pages": 0, "truncated": False},
            }
            code = cli.main(["sherlock", "list", "--active", "--json"])

        payload = json.loads(out.getvalue())
        self.assertEqual(0, code)
        self.assertEqual(631, payload["sherlocks"][0]["id"])

    def test_tasks_text_output_shows_questions(self) -> None:
        with (
            mock.patch("htb_terminal.cli.load_config"),
            mock.patch("htb_terminal.handlers._sherlock_service") as service,
            redirect_stdout(io.StringIO()) as out,
        ):
            service.return_value.tasks.return_value = {
                "sherlock_id": 631,
                "count": 1,
                "tasks": [task_row(TASKS["data"][0])],
            }
            code = cli.main(["sherlock", "tasks", "631", "--color", "never"])

        self.assertEqual(0, code)
        self.assertIn("2880", out.getvalue())
        self.assertIn("What is the attacker IP?", out.getvalue())
        self.assertIn("format: x.x.x.x", out.getvalue())


if __name__ == "__main__":
    unittest.main()
