"""Local machine search.

HTB Labs v4 has no documented search endpoint, so ``search_machines`` scans the
list endpoints and ranks the results client-side. It takes loaders and a profile
resolver as callables, so it stays decoupled from ``MachineService`` and the HTTP
client.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from htb_terminal.services.payloads import (
    extract_items,
    has_next_page,
    machine_row,
    page_signature,
    text,
)

MachineLoader = Callable[[int], Any]
SearchSource = tuple[bool, MachineLoader]
ProfileResolver = Callable[[dict[str, Any]], dict[str, Any] | None]


def search_machines(
    sources: list[SearchSource],
    term: str,
    *,
    profile_resolver: ProfileResolver,
    include_profiles: bool,
    limit: int,
    max_pages: int,
) -> list[dict[str, Any]]:
    matches: list[tuple[int, dict[str, Any]]] = []
    seen: set[int] = set()
    for retired, loader in sources:
        page_signatures: set[tuple[Any, ...]] = set()
        for page in range(1, max_pages + 1):
            payload = loader(page)
            items = extract_items(payload)
            if not items:
                break
            signature = page_signature(items)
            if signature in page_signatures:
                break
            page_signatures.add(signature)
            for item in items:
                if not isinstance(item, dict):
                    continue
                source_item = item
                rank = machine_match_rank(source_item, term)
                if rank is None and include_profiles:
                    profile_item = profile_resolver(source_item)
                    if profile_item:
                        source_item = {**source_item, **profile_item}
                        rank = machine_match_rank(source_item, term)
                if rank is None:
                    continue
                row = machine_row(source_item)
                machine_id = row.get("id")
                if isinstance(machine_id, int):
                    if machine_id in seen:
                        continue
                    seen.add(machine_id)
                row["retired"] = retired
                matches.append((rank, row))
            if len(matches) >= limit or not has_next_page(payload, page):
                break
        if len(matches) >= limit:
            break

    matches.sort(key=lambda match: (match[0], str(match[1].get("name") or "").casefold()))
    return [row for _, row in matches[:limit]]


def machine_match_rank(item: dict[str, Any], query: str) -> int | None:
    term = query.casefold()
    name = text(item.get("name"))
    if name == term:
        return 0
    if name.startswith(term):
        return 1
    if term in name:
        return 2

    exact_fields = [
        item.get("id"),
        item.get("os"),
        item.get("difficultyText"),
        item.get("difficulty_text"),
        item.get("difficulty"),
    ]
    if any(text(value) == term for value in exact_fields):
        return 3

    return 4 if any(term in value for value in searchable_machine_values(item)) else None


def searchable_machine_values(item: dict[str, Any]) -> list[str]:
    values = [
        item.get("id"),
        item.get("name"),
        item.get("os"),
        item.get("difficultyText"),
        item.get("difficulty_text"),
        item.get("difficulty"),
        item.get("points"),
        item.get("static_points"),
        item.get("ip"),
        item.get("description"),
        item.get("short_description"),
        item.get("description_html"),
        item.get("overview"),
    ]

    for key in ("maker", "maker2"):
        maker = item.get(key)
        if isinstance(maker, dict):
            values.append(maker.get("name"))

    tags = item.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                values.extend(tag.values())
            else:
                values.append(tag)

    return [text(value) for value in values if value is not None]
