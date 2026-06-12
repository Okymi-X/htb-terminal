from __future__ import annotations

import random
import sys
import time
from typing import Any

from htb_terminal.http import ApiError, HtbApiClient

TRANSIENT_SPAWN_STATUSES = {429, 500, 502, 503, 504}
TRANSIENT_SPAWN_KEYWORDS = (
    "full",
    "busy",
    "capacity",
    "high load",
    "too many",
    "try again",
    "later",
    "wait",
)


class MachineService:
    def __init__(self, client: HtbApiClient):
        self.client = client

    def profile(self, target: str) -> Any:
        return self.client.get(f"/machine/profile/{target}")

    def active(self) -> Any:
        return self.client.get("/machine/active")

    def active_with_profile(self) -> Any:
        data = self.active()
        info = data.get("info") if isinstance(data, dict) else None
        if not isinstance(info, dict) or "id" not in info:
            return data

        try:
            profile_info = self._profile_item(info)
        except ApiError:
            return data
        if not profile_info:
            return data

        enriched = dict(data)
        enriched["info"] = {**profile_info, **info}
        return enriched

    def active_summary(self, *, include_details: bool = False) -> Any:
        data = self.active_with_profile()
        info = data.get("info") if isinstance(data, dict) else None
        if not isinstance(info, dict):
            return data

        play_info = info.get("playInfo")
        if not isinstance(play_info, dict):
            play_info = {}

        summary = {
            "info": {
                "id": info.get("id"),
                "name": info.get("name"),
                "ip": info.get("ip"),
                "os": info.get("os"),
                "difficulty": info.get("difficultyText")
                or info.get("difficulty_text")
                or info.get("difficulty"),
                "type": info.get("type"),
                "retired": info.get("retired"),
                "active": play_info.get("isActive", info.get("active")),
                "spawned": play_info.get("isSpawned"),
                "expires_at": info.get("expires_at") or play_info.get("expires_at"),
                "vpn_server_id": info.get("vpn_server_id"),
                "lab_server": info.get("lab_server"),
                "info_status": info.get("info_status"),
                "description": info.get("description")
                or info.get("short_description")
                or info.get("overview"),
            }
        }
        if include_details:
            summary["info"]["synopsis"] = info.get("synopsis")
            summary["info"]["academy_modules"] = _academy_module_names(info.get("academy_modules"))
        return summary

    def list_playable(self, page: int | None = None) -> Any:
        return self.client.get("/machine/paginated", query={"page": page})

    def list_retired(self, page: int | None = None) -> Any:
        return self.client.get("/machine/list/retired/paginated", query={"page": page})

    def list_todo(self) -> Any:
        return self.client.get("/machine/todo")

    def list_unreleased(self) -> Any:
        return self.client.get("/machine/unreleased")

    def list_starting_point(self, tier: int) -> Any:
        return self.client.get(f"/sp/tier/{tier}")

    def search(
        self,
        query: str,
        *,
        retired_only: bool = False,
        include_retired: bool = False,
        include_profiles: bool = False,
        limit: int = 20,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        term = query.strip()
        if not term:
            raise ValueError("Search query is required.")
        if limit < 1:
            raise ValueError("Search limit must be at least 1.")
        if max_pages < 1:
            raise ValueError("Search max pages must be at least 1.")

        matches: list[tuple[int, dict[str, Any]]] = []
        seen: set[int] = set()
        for retired, loader in self._search_sources(retired_only, include_retired):
            page_signatures: set[tuple[Any, ...]] = set()
            for page in range(1, max_pages + 1):
                payload = loader(page)
                items = _extract_items(payload)
                if not items:
                    break
                signature = _page_signature(items)
                if signature in page_signatures:
                    break
                page_signatures.add(signature)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    source_item = item
                    rank = _machine_match_rank(source_item, term)
                    if rank is None and include_profiles:
                        profile_item = self._profile_item(source_item)
                        if profile_item:
                            source_item = {**source_item, **profile_item}
                            rank = _machine_match_rank(source_item, term)
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
                if len(matches) >= limit or not _has_next_page(payload, page):
                    break
            if len(matches) >= limit:
                break

        matches.sort(key=lambda match: (match[0], str(match[1].get("name") or "").casefold()))
        return [row for _, row in matches[:limit]]

    def start(self, target: str, mode: str) -> Any:
        machine_id = self.resolve_id(target)
        if mode == "auto":
            return self._start_auto(machine_id)
        if mode == "play":
            return self.play(machine_id)
        if mode == "spawn":
            return self.spawn(machine_id)
        raise ValueError(f"Unsupported start mode: {mode}")

    def start_with_retry(
        self,
        target: str,
        mode: str,
        *,
        retry_for: int = 600,
        interval: int = 15,
    ) -> Any:
        """Start a machine, retrying while spawn capacity is exhausted.

        Meant for peak moments such as seasonal releases (Saturdays 19:00
        UTC), when /vm/spawn rejects requests until a slot frees up.
        """
        machine_id = self.resolve_id(target)
        deadline = time.monotonic() + retry_for
        attempt = 0
        while True:
            attempt += 1
            try:
                return self.start(str(machine_id), mode)
            except ApiError as exc:
                if not _is_transient_spawn_error(exc):
                    raise
                # Jitter spreads retries out so simultaneous clients do not
                # hammer the API in lockstep at the release moment.
                wait = interval * random.uniform(0.8, 1.2)
                if time.monotonic() + wait > deadline:
                    raise ApiError(
                        exc.status,
                        f"Gave up after {attempt} attempts over {retry_for}s: {exc}",
                        exc.body,
                    ) from exc
                print(
                    f"warning: spawn rejected (attempt {attempt}): {exc};"
                    f" retrying in {wait:.0f}s",
                    file=sys.stderr,
                )
                time.sleep(wait)

    def wait_for_active_ip(
        self,
        machine_id: int,
        *,
        timeout: int = 300,
        interval: int = 10,
    ) -> dict[str, Any]:
        """Poll the active machine until it reports an IP address."""
        deadline = time.monotonic() + timeout
        while True:
            data = self.active()
            info = data.get("info") if isinstance(data, dict) else None
            if info and _to_int(info.get("id")) == machine_id and info.get("ip"):
                return info
            if time.monotonic() + interval > deadline:
                raise RuntimeError(
                    f"Machine {machine_id} spawned but got no IP within {timeout}s."
                    " Check 'htb machine active' in a moment."
                )
            print("waiting for machine IP...", file=sys.stderr)
            time.sleep(interval)

    def play(self, machine_id: int) -> Any:
        return self.client.post(f"/machine/play/{machine_id}")

    def spawn(self, machine_id: int) -> Any:
        return self.client.post("/vm/spawn", data={"machine_id": machine_id})

    def stop(self, target: str | None = None) -> Any:
        machine_id = self.resolve_id(target) if target else self.active_id()
        return self.client.post("/vm/terminate", data={"machine_id": machine_id})

    def reset(self, target: str | None = None) -> Any:
        machine_id = self.resolve_id(target) if target else self.active_id()
        return self.client.post("/vm/reset", data={"machine_id": machine_id})

    def submit_flag(self, target: str, flag: str, difficulty: int) -> Any:
        return self.client.post(
            "/machine/own",
            data={"id": self.resolve_id(target), "flag": flag, "difficulty": difficulty},
        )

    def active_id(self) -> int:
        data = self.active()
        info = data.get("info") if isinstance(data, dict) else None
        if not info or "id" not in info:
            raise RuntimeError("No active machine found.")
        return int(info["id"])

    def resolve_id(self, target: str | None) -> int:
        if not target:
            raise RuntimeError("Machine target is required.")
        if target.isdigit():
            return int(target)

        data = self.profile(target)
        info = data.get("info") if isinstance(data, dict) else None
        if not info or "id" not in info:
            raise RuntimeError(f"Unable to resolve machine id for {target!r}.")
        return int(info["id"])

    def _start_auto(self, machine_id: int) -> Any:
        try:
            return self.play(machine_id)
        except ApiError as exc:
            if exc.status in {400, 404, 409, 422}:
                return self.spawn(machine_id)
            raise

    def _search_sources(self, retired_only: bool, include_retired: bool) -> list[tuple[bool, Any]]:
        if retired_only:
            return [(True, self.list_retired)]
        if include_retired:
            return [(False, self.list_playable), (True, self.list_retired)]
        return [(False, self.list_playable)]

    def _profile_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        target = item.get("id") or item.get("name")
        if target is None:
            return None
        data = self.profile(str(target))
        info = data.get("info") if isinstance(data, dict) else None
        return info if isinstance(info, dict) else None


def _is_transient_spawn_error(exc: ApiError) -> bool:
    if exc.status in TRANSIENT_SPAWN_STATUSES:
        return True
    message = str(exc).lower()
    return any(keyword in message for keyword in TRANSIENT_SPAWN_KEYWORDS)


def machine_rows(payload: Any) -> list[dict[str, Any]]:
    items = _extract_items(payload)
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(machine_row(item))
    return rows


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


def _extract_items(payload: Any) -> list[Any]:
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


def _has_next_page(payload: Any, current_page: int) -> bool:
    if not isinstance(payload, dict):
        return False

    links = payload.get("links")
    if isinstance(links, dict) and "next" in links:
        return bool(links.get("next"))

    meta = payload.get("meta")
    if isinstance(meta, dict):
        last_page = _to_int(meta.get("last_page"))
        page = _to_int(meta.get("current_page")) or current_page
        if last_page is not None:
            return page < last_page

    return bool(_extract_items(payload))


def _page_signature(items: list[Any]) -> tuple[Any, ...]:
    signature: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            signature.append(item.get("id", item.get("name")))
        else:
            signature.append(repr(item))
    return tuple(signature)


def _machine_match_rank(item: dict[str, Any], query: str) -> int | None:
    term = query.casefold()
    name = _text(item.get("name"))
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
    if any(_text(value) == term for value in exact_fields):
        return 3

    return 4 if any(term in value for value in _searchable_machine_values(item)) else None


def _searchable_machine_values(item: dict[str, Any]) -> list[str]:
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

    return [_text(value) for value in values if value is not None]


def _academy_module_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def _text(value: Any) -> str:
    return str(value).casefold()


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
