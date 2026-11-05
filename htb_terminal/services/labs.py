"""Pro Lab and Fortress API operations.

Both are separate multiplayer products from machines and challenges:

* ``/prolabs`` lists labs; a lab's machines come from ``/prolab/<id>/machines``.
  There is no ``/prolab/<id>`` detail route (it answers 404), so the list payload
  is the only source of lab metadata.
* ``/fortresses`` lists fortresses and ``/fortress/<id>`` (singular) returns the
  detail, including the flag targets with their points and owned state.

Neither product is spawnable through this client: they are reached over their own
VPN profiles, which is what ``htb vpn`` manages.
"""

from __future__ import annotations

from typing import Any

from htb_terminal.http import ApiError, HtbApiClient
from htb_terminal.services.payloads import extract_items, to_int


def lab_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": to_int(item.get("id")),
        "name": item.get("name"),
        "machines": item.get("pro_machines_count"),
        "flags": item.get("pro_flags_count"),
        "flags_owned": item.get("pro_flags_owns_count"),
        "state": item.get("state"),
        "level": item.get("level") or item.get("skill_level"),
        "release_at": item.get("release_at"),
    }


def fortress_row(item: dict[str, Any]) -> dict[str, Any]:
    """The list payload is thin: id, name, flag counts. Detail adds points/ip."""
    total = item.get("number_of_flags")
    owned = item.get("owned_flags")
    return {
        "id": to_int(item.get("id")),
        "name": item.get("name"),
        "flags": total,
        "owned": owned,
        "progress": f"{owned}/{total}" if total is not None and owned is not None else None,
        "new": item.get("new"),
    }


def flag_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": to_int(item.get("id")),
        "title": item.get("title"),
        "points": item.get("points"),
        "owned": item.get("owned"),
    }


class LabService:
    def __init__(self, client: HtbApiClient):
        self.client = client

    # ------------------------------------------------------------- pro labs
    def labs(self) -> dict[str, Any]:
        payload = self.client.get("/prolabs")
        data = payload.get("data") if isinstance(payload, dict) else None
        items = data.get("labs") if isinstance(data, dict) else None
        if not isinstance(items, list):
            items = extract_items(payload)
        rows = [lab_row(item) for item in items if isinstance(item, dict)]
        return {"labs": rows, "count": len(rows)}

    def lab_info(self, lab_id: int | str) -> dict[str, Any]:
        """``/prolab/<id>/info`` -- the detail route the bare /prolab/<id> lacks."""
        lid = int(lab_id)
        payload = self.client.get(f"/prolab/{lid}/info")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError(f"Could not read lab {lid} from /prolab/<id>/info.")
        return {
            "lab_id": lid,
            "name": data.get("name"),
            "version": data.get("version"),
            "entry_points": data.get("entry_points"),
            "machines": data.get("pro_machines_count") or data.get("machines_count"),
            "flags": data.get("pro_flags_count") or data.get("flags_count"),
            "state": data.get("state"),
        }

    def lab_flags(self, lab_id: int | str) -> dict[str, Any]:
        lid = int(lab_id)
        payload = self.client.get(f"/prolab/{lid}/flags")
        rows = [flag_row(item) for item in extract_items(payload) if isinstance(item, dict)]
        return {
            "lab_id": lid,
            "flags": rows,
            "owned": sum(1 for row in rows if row.get("owned")),
            "total": len(rows),
            "points_earned": sum(row.get("points") or 0 for row in rows if row.get("owned")),
            "points_total": sum(row.get("points") or 0 for row in rows),
        }

    def lab_machines(self, lab_id: int | str) -> dict[str, Any]:
        lid = int(lab_id)
        payload = self.client.get(f"/prolab/{lid}/machines")
        items = extract_items(payload)
        rows = [
            {
                "id": to_int(item.get("id")),
                "name": item.get("name"),
                "os": item.get("os"),
            }
            for item in items
            if isinstance(item, dict)
        ]
        return {"lab_id": lid, "machines": rows, "count": len(rows)}

    # ------------------------------------------------------------- fortresses
    def fortresses(self) -> dict[str, Any]:
        payload = self.client.get("/fortresses")
        items = extract_items(payload)
        rows = [fortress_row(item) for item in items if isinstance(item, dict)]
        return {"fortresses": rows, "count": len(rows)}

    def own_fortress_flag(self, fortress_id: int | str, flag: str) -> dict[str, Any]:
        """``POST /fortress/<id>/flag`` -- fortress flags are per-flag, not user/root.

        The server answers ``400 {"status": false, "message": "Wrong flag"}`` for a
        bad value, so a 2xx here means the flag counted.
        """
        fid = int(fortress_id)
        submitted = flag.strip()
        if not submitted:
            raise ValueError("The flag must not be empty.")
        try:
            payload = self.client.post(f"/fortress/{fid}/flag", {"flag": submitted})
        except ApiError as exc:
            raise RuntimeError(f"Fortress {fid} rejected the flag: {exc}") from exc
        message = payload.get("message") if isinstance(payload, dict) else None
        return {
            "fortress_id": fid,
            "accepted": True,
            "message": message or "Flag accepted.",
        }

    def own_lab_flag(self, lab_id: int | str, flag: str) -> dict[str, Any]:
        """``POST /prolab/<id>/flag`` -- same shape, different message."""
        lid = int(lab_id)
        submitted = flag.strip()
        if not submitted:
            raise ValueError("The flag must not be empty.")
        try:
            payload = self.client.post(f"/prolab/{lid}/flag", {"flag": submitted})
        except ApiError as exc:
            raise RuntimeError(f"Pro Lab {lid} rejected the flag: {exc}") from exc
        message = payload.get("message") if isinstance(payload, dict) else None
        return {
            "lab_id": lid,
            "accepted": True,
            "message": message or "Flag accepted.",
        }

    def fortress(self, fortress_id: int | str) -> dict[str, Any]:
        fid = int(fortress_id)
        payload = self.client.get(f"/fortress/{fid}")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError(f"Could not read fortress {fid} from /fortress/<id>.")
        flags = [flag_row(item) for item in data.get("flags") or [] if isinstance(item, dict)]
        return {
            "fortress_id": fid,
            "name": data.get("name"),
            "company": data.get("company"),
            "ip": data.get("ip"),
            "points": data.get("points"),
            "progress": data.get("progress_percent"),
            "players": data.get("players_completed"),
            "description": data.get("description"),
            "flags": flags,
            "flags_owned": sum(1 for flag in flags if flag.get("owned")),
            "flags_total": len(flags),
            "points_earned": sum(flag.get("points") or 0 for flag in flags if flag.get("owned")),
            "points_total": sum(flag.get("points") or 0 for flag in flags),
        }
