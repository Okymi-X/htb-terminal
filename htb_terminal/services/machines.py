from __future__ import annotations

from typing import Any

from htb_terminal.http import ApiError, HtbApiClient


class MachineService:
    def __init__(self, client: HtbApiClient):
        self.client = client

    def profile(self, target: str) -> Any:
        return self.client.get(f"/machine/profile/{target}")

    def active(self) -> Any:
        return self.client.get("/machine/active")

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

    def start(self, target: str, mode: str) -> Any:
        machine_id = self.resolve_id(target)
        if mode == "auto":
            return self._start_auto(machine_id)
        if mode == "play":
            return self.play(machine_id)
        if mode == "spawn":
            return self.spawn(machine_id)
        raise ValueError(f"Unsupported start mode: {mode}")

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


def machine_rows(payload: Any) -> list[dict[str, Any]]:
    items = _extract_items(payload)
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "os": item.get("os"),
                "difficulty": item.get("difficulty"),
                "points": item.get("points") or item.get("static_points"),
                "active": item.get("isActive"),
                "spawned": item.get("isSpawned"),
                "free": item.get("free"),
            }
        )
    return rows


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
