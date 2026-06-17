from __future__ import annotations

import unittest
from typing import Any

from htb_terminal.http import ApiError
from htb_terminal.services.machines import MachineService
from htb_terminal.services.payloads import machine_rows


class FakeClient:
    def __init__(self, pages: dict[str, dict[int | None, Any]]):
        self.pages = pages
        self.calls: list[tuple[str, int | None]] = []

    def get(self, path: str, query: dict[str, Any] | None = None) -> Any:
        page = query.get("page") if query else None
        self.calls.append((path, page))
        value = self.pages[path][page]
        if isinstance(value, Exception):
            raise value
        return value


class MachineSearchTests(unittest.TestCase):
    def test_active_with_profile_adds_description_and_keeps_session_ip(self) -> None:
        client = FakeClient(
            {
                "/machine/active": {
                    None: {
                        "info": {
                            "id": 669,
                            "ip": "10.129.232.127",
                            "name": "RustyKey",
                            "type": "Retired",
                        },
                    },
                },
                "/machine/profile/669": {
                    None: {
                        "info": {
                            "id": 669,
                            "ip": "10.10.11.1",
                            "name": "RustyKey",
                            "description": "Includes intelligence gathering and SMB share discovery.",
                            "os": "Linux",
                        },
                    },
                },
            }
        )

        payload = MachineService(client).active_with_profile()

        self.assertEqual("10.129.232.127", payload["info"]["ip"])
        self.assertEqual("Includes intelligence gathering and SMB share discovery.", payload["info"]["description"])
        self.assertEqual("Linux", payload["info"]["os"])

    def test_active_with_profile_returns_empty_active_without_profile_call(self) -> None:
        client = FakeClient({"/machine/active": {None: {"info": None}}})

        payload = MachineService(client).active_with_profile()

        self.assertEqual({"info": None}, payload)
        self.assertEqual([("/machine/active", None)], client.calls)

    def test_active_with_profile_falls_back_when_profile_fails(self) -> None:
        active_payload = {"info": {"id": 669, "ip": "10.129.232.127", "name": "RustyKey"}}
        client = FakeClient(
            {
                "/machine/active": {None: active_payload},
                "/machine/profile/669": {None: ApiError(404, "HTTP 404")},
            }
        )

        payload = MachineService(client).active_with_profile()

        self.assertEqual(active_payload, payload)

    def test_active_summary_keeps_useful_text_without_details(self) -> None:
        client = FakeClient(
            {
                "/machine/active": {
                    None: {
                        "info": {
                            "id": 669,
                            "ip": "10.129.232.127",
                            "name": "RustyKey",
                            "type": "Retired",
                        },
                    },
                },
                "/machine/profile/669": {
                    None: {
                        "info": {
                            "id": 669,
                            "name": "RustyKey",
                            "os": "Windows",
                            "difficultyText": "Hard",
                            "info_status": "Credentials: rr.parker / 8#t5HE8L!W3A",
                            "synopsis": "Active Directory and SMB share enumeration.",
                            "academy_modules": [
                                {
                                    "id": 116,
                                    "name": "Attacking Common Services",
                                    "avatar": "https://example.test/avatar.png",
                                }
                            ],
                            "playInfo": {"isActive": True, "isSpawned": True},
                        },
                    },
                },
            }
        )

        payload = MachineService(client).active_summary()

        self.assertEqual("Credentials: rr.parker / 8#t5HE8L!W3A", payload["info"]["info_status"])
        self.assertNotIn("academy_modules", payload["info"])
        self.assertNotIn("synopsis", payload["info"])
        self.assertNotIn("playInfo", payload["info"])

    def test_active_summary_can_include_details(self) -> None:
        client = FakeClient(
            {
                "/machine/active": {
                    None: {
                        "info": {
                            "id": 669,
                            "ip": "10.129.232.127",
                            "name": "RustyKey",
                        },
                    },
                },
                "/machine/profile/669": {
                    None: {
                        "info": {
                            "id": 669,
                            "name": "RustyKey",
                            "synopsis": "Active Directory and SMB share enumeration.",
                            "academy_modules": [
                                {
                                    "id": 116,
                                    "name": "Attacking Common Services",
                                    "avatar": "https://example.test/avatar.png",
                                }
                            ],
                        },
                    },
                },
            }
        )

        payload = MachineService(client).active_summary(include_details=True)

        self.assertEqual("Active Directory and SMB share enumeration.", payload["info"]["synopsis"])
        self.assertEqual(["Attacking Common Services"], payload["info"]["academy_modules"])

    def test_search_matches_and_sorts_by_relevance(self) -> None:
        client = FakeClient(
            {
                "/machine/paginated": {
                    1: {
                        "message": [
                            {"id": 1, "name": "BlueBoard", "os": "Linux", "difficultyText": "Easy"},
                            {"id": 2, "name": "BoardLight", "os": "Windows", "difficultyText": "Easy"},
                        ],
                        "links": {"next": None},
                    },
                },
            }
        )

        rows = MachineService(client).search("board")

        self.assertEqual(["BoardLight", "BlueBoard"], [row["name"] for row in rows])
        self.assertEqual([False, False], [row["retired"] for row in rows])

    def test_search_can_include_retired_pages(self) -> None:
        client = FakeClient(
            {
                "/machine/paginated": {
                    1: {"message": [], "links": {"next": None}},
                },
                "/machine/list/retired/paginated": {
                    1: {
                        "message": [
                            {
                                "id": 3,
                                "name": "Legacy",
                                "os": "Linux",
                                "difficultyText": "Medium",
                                "tags": [{"name": "Kerberos"}],
                            },
                        ],
                        "links": {"next": None},
                    },
                },
            }
        )

        rows = MachineService(client).search("kerberos", include_retired=True)

        self.assertEqual(1, len(rows))
        self.assertEqual("Legacy", rows[0]["name"])
        self.assertTrue(rows[0]["retired"])

    def test_search_stops_when_endpoint_repeats_page(self) -> None:
        repeated_payload = {
            "message": [{"id": 5, "name": "Repeat", "os": "Linux"}],
        }
        client = FakeClient(
            {
                "/machine/paginated": {
                    1: repeated_payload,
                    2: repeated_payload,
                },
            }
        )

        rows = MachineService(client).search("missing", max_pages=10)

        self.assertEqual([], rows)
        self.assertEqual([("/machine/paginated", 1), ("/machine/paginated", 2)], client.calls)

    def test_search_can_match_profile_description(self) -> None:
        client = FakeClient(
            {
                "/machine/paginated": {
                    1: {
                        "message": [{"id": 6, "name": "Incident", "os": "Linux"}],
                        "links": {"next": None},
                    },
                },
                "/machine/profile/6": {
                    None: {
                        "info": {
                            "id": 6,
                            "name": "Incident",
                            "os": "Linux",
                            "description": "Scenario starts with breached credentials.",
                        },
                    },
                },
            }
        )

        rows = MachineService(client).search("breached credentials", include_profiles=True)

        self.assertEqual(1, len(rows))
        self.assertEqual("Incident", rows[0]["name"])

    def test_search_skips_profile_calls_when_profile_search_is_disabled(self) -> None:
        client = FakeClient(
            {
                "/machine/paginated": {
                    1: {
                        "message": [{"id": 7, "name": "NoProfileFetch", "os": "Linux"}],
                        "links": {"next": None},
                    },
                },
            }
        )

        rows = MachineService(client).search("breached credentials")

        self.assertEqual([], rows)
        self.assertEqual([("/machine/paginated", 1)], client.calls)

    def test_machine_rows_reads_play_info_state(self) -> None:
        rows = machine_rows(
            {
                "message": [
                    {
                        "id": 4,
                        "name": "Nested",
                        "playInfo": {"isActive": True, "isSpawned": False},
                    },
                ],
            }
        )

        self.assertEqual(True, rows[0]["active"])
        self.assertEqual(False, rows[0]["spawned"])


if __name__ == "__main__":
    unittest.main()
