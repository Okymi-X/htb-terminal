"""Current-user profile operations.

``UserService`` is the single entry point for the authenticated user's data.
``whoami`` (``GET /user/info``) is also the lightweight call used to verify a
token, since any authenticated request validates the bearer token.
"""

from __future__ import annotations

from typing import Any

from htb_terminal.http import HtbApiClient


class UserService:
    def __init__(self, client: HtbApiClient):
        self.client = client

    def whoami(self) -> dict[str, Any]:
        """Return the authenticated user's basic identity (id, name)."""
        data = self.client.get("/user/info")
        info = data.get("info") if isinstance(data, dict) else None
        if not isinstance(info, dict) or "id" not in info:
            raise RuntimeError("Could not read the current user from /user/info.")
        return info

    def profile(self, user_id: int | None = None) -> dict[str, Any]:
        """Return a full basic profile. Defaults to the authenticated user."""
        if user_id is None:
            user_id = int(self.whoami()["id"])
        data = self.client.get(f"/user/profile/basic/{user_id}")
        profile = data.get("profile") if isinstance(data, dict) else None
        if not isinstance(profile, dict):
            raise RuntimeError(f"Could not read the profile for user {user_id}.")
        return profile

    def summary(self) -> dict[str, Any]:
        return user_summary(self.profile())


def user_summary(profile: dict[str, Any]) -> dict[str, Any]:
    team = profile.get("team")
    team_name = team.get("name") if isinstance(team, dict) else team
    return {
        "info": {
            "id": profile.get("id"),
            "name": profile.get("name"),
            "rank": profile.get("rank"),
            "points": profile.get("points"),
            "ranking": profile.get("ranking"),
            "user_owns": profile.get("user_owns"),
            "system_owns": profile.get("system_owns"),
            "respects": profile.get("respects"),
            "country": profile.get("country_name"),
            "team": team_name,
            "vip": vip_tier(profile),
        }
    }


def vip_tier(profile: dict[str, Any]) -> str:
    """HTB's tiers: VIP+ (dedicated) outranks VIP; otherwise no subscription.

    ``isVip`` is false for VIP+ accounts, so dedicated VIP must be checked
    separately or the tool reports a paying user as having none.
    """
    if profile.get("isDedicatedVip"):
        return "VIP+"
    if profile.get("isVip"):
        return "VIP"
    return "no"
