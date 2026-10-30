"""Shared page walking and page caching for paginated list endpoints.

HTB list routes are Laravel paginators: ``{"data": [...], "links": {...},
"meta": {...}}``. :func:`paginate_rows` walks them until the last page, a
repeated page (an endpoint ignoring ``page``), the row limit, or a page cap, so
a caller never has to know how many pages a filter needs.

:class:`PageCache` is a small JSON-on-disk cache of already fetched pages. It
exists for one reason: the challenge and Sherlock list endpoints are rate
limited (HTTP 429), and a listing that only needs a handful of pages should not
fall over when the limit is hit — the client still backs off and retries, and
this cache answers with the last good payload if the retries run out.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from htb_terminal.config import user_config_dir
from htb_terminal.services.payloads import extract_items, has_next_page, page_signature

PAGE_CACHE_TTL_SECONDS = 300.0


def default_cache_path(name: str) -> Path:
    """Cache file for one endpoint family, under the user config directory."""
    return user_config_dir() / "cache" / f"{name}.json"


class PageCache:
    """Best-effort cache of list pages, keyed by page and server-side filters."""

    def __init__(self, path: Path | None = None, ttl: float = PAGE_CACHE_TTL_SECONDS):
        self.path = path or default_cache_path("pages")
        self.ttl = ttl

    def page(self, key: str, *, allow_stale: bool = False) -> Any | None:
        entry = self._read().get(key)
        if not isinstance(entry, dict):
            return None
        payload = entry.get("payload")
        if payload is None:
            return None
        if allow_stale:
            return payload
        stored_at = entry.get("stored_at")
        if not isinstance(stored_at, (int, float)):
            return None
        if time.time() - stored_at > self.ttl:
            return None
        return payload

    def store(self, key: str, payload: Any) -> None:
        data = self._read()
        data[key] = {"stored_at": time.time(), "payload": payload}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            # The cache is an optimization; a read-only config dir must not
            # turn a working listing into a failure.
            pass

    def _read(self) -> dict[str, Any]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}


def cache_key(page: int, per_page: int, query: dict[str, Any]) -> str:
    return json.dumps([page, per_page, sorted(query.items())])


def paginate_rows(
    fetch_page: Callable[[int], tuple[Any, bool]],
    *,
    to_row: Callable[[dict[str, Any]], dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool] | None = None,
    limit: int | None = None,
    max_pages: int = 50,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collect rows across pages.

    ``fetch_page`` returns ``(payload, from_cache)`` for a 1-based page number
    and may raise; that is where a service applies its cache and 429 fallback.
    ``predicate`` filters rows locally, after the API-side filters, so a
    filter the API does not support still works.
    """
    rows: list[dict[str, Any]] = []
    pages_scanned = 0
    cached_pages = 0
    truncated = False
    page_cap_reached = False
    previous: tuple[Any, ...] | None = None
    seen: set[Any] = set()
    page = 1

    while page <= max_pages:
        payload, from_cache = fetch_page(page)
        pages_scanned += 1
        cached_pages += int(from_cache)
        items = [item for item in extract_items(payload) if isinstance(item, dict)]

        hit_limit = False
        for index, item in enumerate(items):
            row = to_row(item)
            if predicate is not None and not predicate(row):
                continue
            identifier = row.get("id")
            if identifier is not None:
                if identifier in seen:
                    continue
                seen.add(identifier)
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                # Only claim truncation when something was actually left out.
                truncated = index + 1 < len(items) or has_next_page(payload, page)
                hit_limit = True
                break
        if hit_limit:
            break

        signature = page_signature(items)
        if not items or signature == previous or not has_next_page(payload, page):
            break
        previous = signature
        page += 1
    else:
        page_cap_reached = pages_scanned >= max_pages

    meta = {
        "pages_scanned": pages_scanned,
        "cached_pages": cached_pages,
        "truncated": truncated,
        "page_cap_reached": page_cap_reached,
        "limit": limit,
    }
    return rows, meta
