"""Machine API operations.

``MachineService`` is the single entry point for machine workflows. Payload
reshaping lives in :mod:`htb_terminal.services.payloads`, search ranking in
:mod:`htb_terminal.services.search`, and spawn-error detection in
:mod:`htb_terminal.services.spawn`.
"""

from __future__ import annotations

import random
import sys
import time
from typing import Any

from htb_terminal.http import ApiError, HtbApiClient
from htb_terminal.services.payloads import academy_module_names, to_int
from htb_terminal.services.search import SearchSource, search_machines
from htb_terminal.services.spawn import (
    is_active_instance_conflict,
    is_transient_spawn_error,
)
from htb_terminal.timefmt import relative_expiry


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
                "expires_in": relative_expiry(info.get("expires_at") or play_info.get("expires_at")),
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
            summary["info"]["academy_modules"] = academy_module_names(info.get("academy_modules"))
        return summary

    def list_playable(self, page: int | None = None) -> Any:
        return self.client.get("/machine/paginated", query={"page": page})

    def list_retired(self, page: int | None = None) -> Any:
        return self.client.get("/machine/list/retired/paginated", query={"page": page})

    def list_todo(self) -> Any:
        # The v4 /machine/todo, /machine/unreleased and /sp/tier/{tier} routes
        # were removed; their filters now live on the unified v5 /machines.
        return self.client.get("/machines", query={"todo": 1}, version="v5")

    def list_unreleased(self) -> Any:
        return self.client.get("/machines", query={"state": "unreleased"}, version="v5")

    def list_starting_point(self, tier: int) -> Any:
        return self.client.get("/machines", query={"spTier": tier}, version="v5")

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

        return search_machines(
            self._search_sources(retired_only, include_retired),
            term,
            profile_resolver=self._profile_item,
            include_profiles=include_profiles,
            limit=limit,
            max_pages=max_pages,
        )

    def start(self, target: str, mode: str) -> Any:
        machine_id = self.resolve_id(target)
        dispatch = self._start_dispatch(mode)
        try:
            return dispatch(machine_id)
        except ApiError as exc:
            if not is_active_instance_conflict(exc):
                raise
            return self._recover_active_conflict(machine_id, dispatch, exc)

    def _start_dispatch(self, mode: str):
        """Return the callable that performs ``start`` for ``mode``."""
        if mode == "auto":
            return self._start_auto
        if mode == "play":
            return self.play
        if mode == "spawn":
            return self.spawn
        raise ValueError(f"Unsupported start mode: {mode}")

    def _recover_active_conflict(self, machine_id: int, dispatch, exc: ApiError) -> Any:
        """Resolve a "you already have an active instance" rejection.

        HTB blocks a start whenever any instance is assigned to the account.
        We inspect what is actually active and react idempotently:

        * Same machine, already has an IP -> it is up; report it, do not churn it.
        * Same machine, no IP yet (assigned but ``spawned: no``) -> the slot is
          stuck, so reclaim it (terminate + restart) — exactly the manual
          ``stop`` then ``start`` recovery, but automatic.
        * A *different* machine is active -> never touch it; raise a clear,
          actionable error naming it.
        """
        info = self._active_info()
        active_id = to_int(info.get("id")) if info else None
        if active_id is None:
            # Conflict reported but nothing visibly active; nothing safe to do.
            raise exc
        if active_id != machine_id:
            name = info.get("name") or "another machine"
            raise ApiError(
                exc.status,
                f"You already have an active instance: {name} (id {active_id}). "
                "Stop it first with 'htb machine stop' before starting this one.",
                exc.body,
            ) from exc
        if info.get("ip"):
            return {"message": "Machine already active.", "info": info}
        # Assigned to us but not running: free the stuck slot and try again.
        print(
            f"reclaiming stuck instance for machine {machine_id} "
            "(active but not spawned); terminating and restarting...",
            file=sys.stderr,
        )
        self.stop(str(machine_id))
        return dispatch(machine_id)

    def _active_info(self) -> dict[str, Any] | None:
        data = self.active()
        info = data.get("info") if isinstance(data, dict) else None
        return info if isinstance(info, dict) else None

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
                if not is_transient_spawn_error(exc):
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
                # Expected at peak/seasonal times, so this is progress, not a
                # warning: the spawn server is full and we keep trying.
                print(
                    f"spawn server busy (attempt {attempt}): {exc};"
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
        """Poll the active machine until it reports an IP address.

        Two failure shapes are handled distinctly from a normal "still booting"
        poll: if the machine drops out of ``/machine/active`` (or is replaced by
        a different one) after we have already seen it active, the spawn has
        collapsed on HTB's side and waiting out the full ``timeout`` is
        pointless — fail fast with that diagnosis instead.
        """
        deadline = time.monotonic() + timeout
        seen_active = False
        while True:
            info = self._active_info()
            current_id = to_int(info.get("id")) if info else None
            if current_id == machine_id:
                seen_active = True
                if info.get("ip"):
                    return info
            elif seen_active:
                where = (
                    f"machine {current_id} is now active instead"
                    if current_id is not None
                    else "no machine is active anymore"
                )
                raise RuntimeError(
                    f"Machine {machine_id} dropped out before reporting an IP"
                    f" ({where}); the spawn collapsed on HTB's side."
                    " Re-run 'htb machine start', and confirm you are connected"
                    " to the matching VPN lab server."
                )
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

    def extend(self, target: str | None = None) -> Any:
        machine_id = self.resolve_id(target) if target else self.active_id()
        return self.client.post("/vm/extend", data={"machine_id": machine_id})

    def submit_flag(self, target: str, flag: str, difficulty: int) -> Any:
        # v4 /machine/own was removed; flag submission now lives on v5.
        return self.client.post(
            "/machine/own",
            data={"id": self.resolve_id(target), "flag": flag, "difficulty": difficulty},
            version="v5",
        )

    def active_id(self) -> int:
        info = self._active_info()
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

    def _search_sources(self, retired_only: bool, include_retired: bool) -> list[SearchSource]:
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
