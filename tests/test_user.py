from __future__ import annotations

import unittest
from typing import Any

from htb_terminal.services.user import UserService, user_summary, vip_tier


class FakeClient:
    def __init__(self, responses: dict[str, Any]):
        self.responses = responses
        self.calls: list[str] = []

    def get(self, path: str, query: dict[str, Any] | None = None) -> Any:
        self.calls.append(path)
        return self.responses[path]


class UserServiceTests(unittest.TestCase):
    def test_whoami_reads_info(self) -> None:
        client = FakeClient({"/user/info": {"info": {"id": 5, "name": "neo"}}})
        self.assertEqual({"id": 5, "name": "neo"}, UserService(client).whoami())

    def test_whoami_raises_on_unexpected_shape(self) -> None:
        client = FakeClient({"/user/info": {"info": None}})
        with self.assertRaises(RuntimeError):
            UserService(client).whoami()

    def test_profile_defaults_to_authenticated_user(self) -> None:
        client = FakeClient(
            {
                "/user/info": {"info": {"id": 5, "name": "neo"}},
                "/user/profile/basic/5": {"profile": {"id": 5, "name": "neo", "points": 120}},
            }
        )
        profile = UserService(client).profile()
        self.assertEqual(120, profile["points"])
        self.assertEqual(["/user/info", "/user/profile/basic/5"], client.calls)

    def test_profile_with_explicit_id_skips_whoami(self) -> None:
        client = FakeClient({"/user/profile/basic/9": {"profile": {"id": 9, "name": "trinity"}}})
        profile = UserService(client).profile(9)
        self.assertEqual("trinity", profile["name"])
        self.assertEqual(["/user/profile/basic/9"], client.calls)


class UserSummaryTests(unittest.TestCase):
    def test_extracts_team_name_and_core_fields(self) -> None:
        summary = user_summary(
            {
                "id": 5,
                "name": "neo",
                "rank": "Hacker",
                "points": 120,
                "user_owns": 30,
                "system_owns": 25,
                "country_name": "France",
                "team": {"name": "Zion"},
                "isVip": True,
            }
        )
        info = summary["info"]
        self.assertEqual("neo", info["name"])
        self.assertEqual("France", info["country"])
        self.assertEqual("Zion", info["team"])
        self.assertTrue(info["vip"])

    def test_team_can_be_plain_value(self) -> None:
        summary = user_summary({"id": 1, "name": "x", "team": None})
        self.assertIsNone(summary["info"]["team"])

    def test_vip_tier_reports_dedicated_vip_as_plus(self) -> None:
        # VIP+ accounts have isVip == False, so isDedicatedVip must win.
        self.assertEqual("VIP+", vip_tier({"isVip": False, "isDedicatedVip": True}))
        self.assertEqual("VIP", vip_tier({"isVip": True, "isDedicatedVip": False}))
        self.assertEqual("no", vip_tier({"isVip": False}))

    def test_summary_surfaces_vip_plus(self) -> None:
        summary = user_summary({"id": 5, "name": "neo", "isDedicatedVip": True})
        self.assertEqual("VIP+", summary["info"]["vip"])


if __name__ == "__main__":
    unittest.main()
