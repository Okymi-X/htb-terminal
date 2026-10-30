"""Sherlock (DFIR challenge) API operations.

Sherlocks are task-based: a Sherlock has a fixed set of numbered tasks, each
answered with a graded string. The ``/sherlocks`` list and ``/sherlocks/<id>``
info payloads do **not** carry the tasks — they come from
``/sherlocks/<id>/tasks`` — and progress is a separate call.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from htb_terminal.http import ApiError, HtbApiClient
from htb_terminal.services.paging import PageCache, cache_key, default_cache_path, paginate_rows
from htb_terminal.services.payloads import difficulty_slug, extract_items, to_int

PER_PAGE = 100
MAX_PAGES = 50


def sherlock_cache_path() -> Path:
    return default_cache_path("sherlocks")


@dataclass(frozen=True)
class SherlockFilters:
    """Filters for ``sherlock list``.

    ``state`` and ``difficulty`` are applied by the API; ownership and the text
    search are applied locally, matching ``challenge list``.
    """

    state: str | None = None
    difficulty: str | None = None
    owned: bool | None = None
    search: str | None = None

    def server_query(self) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if self.state:
            query["state"] = self.state
        if self.difficulty:
            query["difficulty[]"] = self.difficulty
        return query

    def matches(self, row: dict[str, Any]) -> bool:
        if self.state and str(row.get("state") or "") != self.state:
            return False
        if self.difficulty and difficulty_slug(row.get("difficulty")) != self.difficulty:
            return False
        if self.owned is not None and bool(row.get("owned")) != self.owned:
            return False
        if self.search:
            term = self.search.casefold()
            name = str(row.get("name") or "").casefold()
            if term not in name and term != str(row.get("id") or ""):
                return False
        return True


def sherlock_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": to_int(item.get("id")),
        "name": item.get("name"),
        "category": item.get("category_name"),
        "difficulty": item.get("difficulty"),
        "state": item.get("state"),
        "solves": item.get("solves"),
        "owned": item.get("is_owned"),
        "progress": item.get("progress"),
    }


def task_row(item: dict[str, Any], *, include_hint: bool = False) -> dict[str, Any]:
    row = {
        "id": to_int(item.get("id")),
        "title": item.get("title"),
        "question": item.get("description"),
        "answer_format": item.get("masked_flag"),
        "completed": item.get("completed"),
        "prerequisite_id": item.get("prerequisite_id"),
    }
    if include_hint:
        row["hint"] = item.get("hint")
    return row


class SherlockService:
    def __init__(self, client: HtbApiClient, cache: PageCache | None = None):
        self.client = client
        self.cache = cache if cache is not None else PageCache(sherlock_cache_path())

    def list(
        self,
        filters: SherlockFilters | None = None,
        *,
        limit: int | None = 20,
        per_page: int = PER_PAGE,
        max_pages: int = MAX_PAGES,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        selected = filters or SherlockFilters()
        server_query = selected.server_query()
        fell_back = False

        def fetch_page(page: int) -> tuple[Any, bool]:
            nonlocal server_query, fell_back
            while True:
                try:
                    return self._page(page, per_page, server_query, use_cache=use_cache)
                except ApiError as exc:
                    if exc.status in {400, 422} and server_query and not fell_back:
                        print(
                            "warning: the API rejected the server-side list filters;"
                            " filtering locally instead.",
                            file=sys.stderr,
                        )
                        server_query = {}
                        fell_back = True
                        continue
                    raise

        rows, meta = paginate_rows(
            fetch_page,
            to_row=sherlock_row,
            predicate=selected.matches,
            limit=limit,
            max_pages=max_pages,
        )
        return {"sherlocks": rows, "count": len(rows), "meta": meta}

    def _page(
        self, page: int, per_page: int, server_query: dict[str, Any], *, use_cache: bool
    ) -> tuple[Any, bool]:
        key = cache_key(page, per_page, server_query)
        if use_cache:
            cached = self.cache.page(key)
            if cached is not None:
                return cached, True
        query = {"page": page, "per_page": per_page, **server_query}
        try:
            payload = self.client.get("/sherlocks", query=query)
        except ApiError as exc:
            if exc.status != 429:
                raise
            stale = self.cache.page(key, allow_stale=True)
            if stale is None:
                raise ApiError(
                    exc.status,
                    f"{exc} (rate limited and no cached copy of page {page}; try again in a minute)",
                    exc.body,
                ) from exc
            print(
                f"warning: rate limited (HTTP 429); using the cached copy of page {page}.",
                file=sys.stderr,
            )
            return stale, True
        self.cache.store(key, payload)
        return payload, False

    def info_raw(self, sherlock_id: int | str) -> dict[str, Any]:
        payload = self.client.get(f"/sherlocks/{int(sherlock_id)}")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError(f"Could not read sherlock {sherlock_id} from /sherlocks/<id>.")
        return payload

    def tasks(self, sherlock_id: int | str, *, include_hints: bool = False) -> dict[str, Any]:
        """List a Sherlock's tasks (ids, questions, answer format)."""
        sid = int(sherlock_id)
        payload = self.client.get(f"/sherlocks/{sid}/tasks")
        items = [item for item in extract_items(payload) if isinstance(item, dict)]
        if not items:
            raise RuntimeError(
                f"Sherlock {sid} returned no tasks from /sherlocks/{sid}/tasks."
                " The list and info payloads do not carry tasks, so this is the only"
                " source; check that the id is correct with 'htb sherlock list'."
            )
        rows = [task_row(item, include_hint=include_hints) for item in items]
        return {"sherlock_id": sid, "tasks": rows, "count": len(rows)}

    def answer(self, sherlock_id: int | str, task_id: int | str, answer: str) -> dict[str, Any]:
        sid = int(sherlock_id)
        tid = int(task_id)
        submitted = answer.strip()
        if not submitted:
            raise ValueError("The answer must not be empty.")
        try:
            payload = self.client.post(
                f"/sherlocks/{sid}/tasks/{tid}/flag",
                {"flag": submitted},
            )
        except ApiError as exc:
            raise _answer_error(exc, sid, tid) from exc
        message = _message(payload) or "Answer accepted."
        if any(word in message.casefold() for word in ("incorrect", "wrong", "invalid")):
            raise RuntimeError(f"Task {tid}: {message}")
        return {
            "sherlock_id": sid,
            "task_id": tid,
            "accepted": True,
            "message": message,
        }

    def progress(self, sherlock_id: int | str) -> dict[str, Any]:
        sid = int(sherlock_id)
        payload = self.client.get(f"/sherlocks/{sid}/progress")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError(f"Could not read progress for sherlock {sid}.")
        return {
            "sherlock": {
                "id": sid,
                "answered": data.get("tasks_answered"),
                "total": data.get("total_tasks"),
                "progress": data.get("progress"),
                "owned": data.get("is_owned"),
                "own_rank": data.get("own_rank"),
            }
        }


def _answer_error(exc: ApiError, sherlock_id: int, task_id: int) -> RuntimeError:
    detail = _body_message(exc) or str(exc)
    if exc.status == 400:
        return RuntimeError(f"Wrong answer for task {task_id}: {detail}")
    if exc.status == 403:
        return RuntimeError(
            f"Task {task_id} is locked or not available to this account (HTTP 403): {detail}."
            " Answer the prerequisite task first, then retry."
        )
    if exc.status == 404:
        return RuntimeError(
            f"Sherlock {sherlock_id} has no task {task_id} (HTTP 404)."
            f" Run 'htb sherlock tasks {sherlock_id}' to list the valid ids."
        )
    return RuntimeError(f"Could not submit the answer for task {task_id}: {detail}")


def _body_message(exc: ApiError) -> str | None:
    body = exc.body
    if isinstance(body, dict):
        message = body.get("message") or body.get("error")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return None


def _message(payload: Any) -> str | None:
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return None
