"""Account progress and submission views.

The documented ``/profile/progress/machines/os/<id>`` route is gone (it answers
404), but the aggregate routes still work and carry the same numbers:
``/profile/progress/machines/<id>``, ``/challenges/<id>``, ``/fortress/<id>`` and
``/prolab/<id>``. Everything here is read-only and keyed by the authenticated
user id, so ``htb progress`` needs no arguments.
"""

from __future__ import annotations

from typing import Any

from htb_terminal.http import HtbApiClient
from htb_terminal.services.payloads import extract_items, to_int

PROGRESS_KINDS = ("machines", "challenges", "fortress", "prolab")


def _profile(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        profile = payload.get("profile")
        if isinstance(profile, dict):
            return profile
    return {}


class ProgressService:
    def __init__(self, client: HtbApiClient):
        self.client = client

    def user_id(self) -> int:
        payload = self.client.get("/user/info")
        info = payload.get("info") if isinstance(payload, dict) else None
        uid = to_int((info or {}).get("id"))
        if uid is None:
            raise RuntimeError("Could not read the authenticated user id from /user/info.")
        return uid

    def kind(self, kind: str, user_id: int | None = None) -> dict[str, Any]:
        if kind not in PROGRESS_KINDS:
            raise ValueError(f"Unknown progress kind {kind!r}; choose from {PROGRESS_KINDS}.")
        uid = user_id if user_id is not None else self.user_id()
        profile = _profile(self.client.get(f"/profile/progress/{kind}/{uid}"))
        if kind == "machines":
            owns = profile.get("machine_owns") or {}
            return {
                "kind": kind,
                "user_id": uid,
                "solved": owns.get("solved"),
                "total": owns.get("total"),
                "bloods": profile.get("total_bloods"),
                "raw": profile,
            }
        if kind == "challenges":
            owns = profile.get("challenge_owns") or {}
            return {
                "kind": kind,
                "user_id": uid,
                "solved": owns.get("solved"),
                "total": owns.get("total"),
                "bloods": profile.get("total_bloods"),
                "raw": profile,
            }
        if kind == "fortress":
            rows = [
                {
                    "id": to_int(item.get("id")),
                    "name": item.get("name"),
                    "flags": item.get("owned_flags"),
                    "total": item.get("total_flags"),
                    "percent": item.get("completion_percentage"),
                }
                for item in profile.get("fortresses") or []
                if isinstance(item, dict)
            ]
            return {"kind": kind, "user_id": uid, "fortresses": rows, "count": len(rows)}
        rows = [
            {
                "id": to_int(item.get("id")),
                "name": item.get("name"),
                "flags": item.get("owned_flags"),
                "total": item.get("total_flags"),
                "machines": item.get("total_machines"),
                "percent": item.get("completion_percentage"),
            }
            for item in profile.get("prolabs") or []
            if isinstance(item, dict)
        ]
        return {"kind": kind, "user_id": uid, "prolabs": rows, "count": len(rows)}

    def summary(self) -> dict[str, Any]:
        uid = self.user_id()
        machines = self.kind("machines", uid)
        challenges = self.kind("challenges", uid)
        fortress = self.kind("fortress", uid)
        prolab = self.kind("prolab", uid)
        return {
            "user_id": uid,
            "machines": {"solved": machines["solved"], "total": machines["total"]},
            "challenges": {"solved": challenges["solved"], "total": challenges["total"]},
            "bloods": challenges.get("bloods"),
            "fortresses": fortress["fortresses"],
            "prolabs": prolab["prolabs"],
        }

    def submissions(self, kind: str = "machines") -> dict[str, Any]:
        if kind not in ("machines", "challenges"):
            raise ValueError("Submissions kind must be 'machines' or 'challenges'.")
        payload = self.client.get(f"/user/submissions/{kind}")
        rows = [
            {"id": to_int(item.get("id")), "name": item.get("name"), "type": item.get("type")}
            for item in extract_items(payload)
            if isinstance(item, dict)
        ]
        return {"kind": kind, "submissions": rows, "count": len(rows)}

    def connection(self) -> dict[str, Any]:
        payload = self.client.get("/user/connection/status")
        if not isinstance(payload, dict):
            return {"connected": False}
        return {
            "connected": bool(payload.get("status")),
            "state": payload.get("connection"),
        }
