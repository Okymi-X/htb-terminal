"""Pure helpers for interpreting HTB Labs machine-list payloads.

These functions have no I/O and no state; they only reshape the JSON the API
returns. Keeping them here lets ``MachineService`` stay focused on API calls.
"""

from __future__ import annotations

from typing import Any


def machine_rows(payload: Any) -> list[dict[str, Any]]:
    return [machine_row(item) for item in extract_items(payload) if isinstance(item, dict)]


def machine_row(item: dict[str, Any]) -> dict[str, Any]:
    play_info = item.get("playInfo")
    if not isinstance(play_info, dict):
        play_info = {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "os": item.get("os"),
        "difficulty": item.get("difficultyText") or item.get("difficulty_text") or item.get("difficulty"),
        "points": item.get("points") or item.get("static_points"),
        "active": item.get("isActive") if item.get("isActive") is not None else play_info.get("isActive"),
        "spawned": item.get("isSpawned") if item.get("isSpawned") is not None else play_info.get("isSpawned"),
        "free": item.get("free"),
    }


def extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("data", "message", "machines", "info"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = value.get("data")
            if isinstance(nested, list):
                return nested
    return []


def has_next_page(payload: Any, current_page: int) -> bool:
    if not isinstance(payload, dict):
        return False

    links = payload.get("links")
    if isinstance(links, dict) and "next" in links:
        return bool(links.get("next"))

    meta = payload.get("meta")
    if isinstance(meta, dict):
        last_page = to_int(meta.get("last_page"))
        page = to_int(meta.get("current_page")) or current_page
        if last_page is not None:
            return page < last_page

    return bool(extract_items(payload))


def page_signature(items: list[Any]) -> tuple[Any, ...]:
    signature: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            signature.append(item.get("id", item.get("name")))
        else:
            signature.append(repr(item))
    return tuple(signature)


def academy_module_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def text(value: Any) -> str:
    return str(value).casefold()


def to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
