from __future__ import annotations

import unittest
from unittest import mock

from htb_terminal.services.vpn import (
    ensure_openvpn_privileges,
    resolve_server_id,
    server_rows,
)


class OpenvpnPrivilegeTests(unittest.TestCase):
    def test_allows_any_command_when_root(self):
        with mock.patch("htb_terminal.services.vpn.os.geteuid", return_value=0):
            ensure_openvpn_privileges(["openvpn"])

    def test_allows_sudo_wrapper_when_not_root(self):
        with mock.patch("htb_terminal.services.vpn.os.geteuid", return_value=1000):
            ensure_openvpn_privileges(["sudo", "openvpn"])
            ensure_openvpn_privileges(["/usr/bin/doas", "openvpn"])

    def test_rejects_plain_openvpn_when_not_root(self):
        with mock.patch("htb_terminal.services.vpn.os.geteuid", return_value=1000):
            with self.assertRaises(RuntimeError) as ctx:
                ensure_openvpn_privileges(["openvpn"])
        self.assertIn("root", str(ctx.exception))
        self.assertIn("sudo openvpn", str(ctx.exception))


class ResolveServerIdTests(unittest.TestCase):
    def test_resolves_alias_and_numeric_id(self):
        self.assertEqual(113, resolve_server_id("us-free-1"))
        self.assertEqual(42, resolve_server_id("42"))

    def test_unknown_alias_lists_known_ones(self):
        with self.assertRaises(RuntimeError) as ctx:
            resolve_server_id("mars-free-1")
        self.assertIn("eu-free-1", str(ctx.exception))


class ServerRowsTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "data": {
                "assigned": {
                    "id": 288,
                    "friendly_name": "EU Dedicated VIP",
                    "location": "EU",
                    "current_clients": 3,
                    "full": False,
                },
                "options": {
                    "VIP": {
                        "EU": {
                            "name": "EU - VIP",
                            "location": "EU",
                            "servers": {
                                "265": {
                                    "id": 265,
                                    "friendly_name": "EU VIP 1",
                                    "location": "EU",
                                    "current_clients": 40,
                                    "full": False,
                                },
                                "288": {
                                    "id": 288,
                                    "friendly_name": "EU Dedicated VIP",
                                    "location": "EU",
                                    "current_clients": 3,
                                    "full": False,
                                },
                            },
                        },
                    },
                    "VIP+": {
                        "EU": {
                            "name": "EU - VIP+",
                            "location": "EU",
                            "servers": {
                                "300": {
                                    "id": 300,
                                    "friendly_name": "EU VIP+ 1",
                                    "location": "EU",
                                    "current_clients": 5,
                                    "full": True,
                                },
                            },
                        },
                    },
                },
            },
        }

    def test_flattens_vip_pools_and_marks_assigned_first(self):
        rows = server_rows(self._payload())
        ids = [r["id"] for r in rows]

        self.assertEqual([288, 265, 300], ids)
        self.assertEqual("EU - VIP", rows[0]["group"])
        self.assertTrue(rows[0]["assigned"])
        self.assertFalse(any(r["assigned"] for r in rows[1:]))
        self.assertEqual(300, rows[2]["id"])
        self.assertTrue(rows[2]["full"])

    def test_dedupes_assigned_server_listed_in_options(self):
        rows = server_rows(self._payload())
        self.assertEqual(1, sum(1 for r in rows if r["id"] == 288))

    def test_empty_or_malformed_payload_yields_no_rows(self):
        self.assertEqual([], server_rows({}))
        self.assertEqual([], server_rows({"data": {"options": None}}))
        self.assertEqual([], server_rows("nope"))

class ResolveServerTests(unittest.TestCase):
    """Test VpnService.resolve_server() — the three-tier resolver."""

    def _service(self, live_payload=None):
        from htb_terminal.services.vpn import VpnService

        client = mock.Mock()
        if live_payload is not None:
            client.get.return_value = live_payload
        service = VpnService(client)
        return service, client

    def test_numeric_id_skips_api(self):
        service, client = self._service()
        self.assertEqual(289, service.resolve_server("289"))
        client.get.assert_not_called()

    def test_static_alias_skips_api(self):
        service, client = self._service()
        self.assertEqual(113, service.resolve_server("us-free-1"))
        client.get.assert_not_called()

    def test_resolves_friendly_name_via_live_api(self):
        payload = {
            "data": {
                "assigned": None,
                "options": {
                    "VIP+": {
                        "US": {
                            "name": "US - Machines VIP+",
                            "servers": {
                                "289": {
                                    "id": 289,
                                    "friendly_name": "US Machines VIP+ 1",
                                    "location": "US",
                                    "current_clients": 52,
                                    "full": False,
                                },
                            },
                        },
                    },
                },
            },
        }
        service, _ = self._service(live_payload=payload)
        self.assertEqual(289, service.resolve_server("US Machines VIP+ 1"))

    def test_friendly_name_is_case_insensitive(self):
        payload = {
            "data": {
                "assigned": None,
                "options": {
                    "Pool": {
                        "EU": {
                            "name": "EU - Pool",
                            "servers": {
                                "10": {
                                    "id": 10,
                                    "friendly_name": "EU Pool 1",
                                    "location": "EU",
                                    "current_clients": 5,
                                    "full": False,
                                },
                            },
                        },
                    },
                },
            },
        }
        service, _ = self._service(live_payload=payload)
        self.assertEqual(10, service.resolve_server("eu pool 1"))

    def test_unknown_name_raises_with_helpful_message(self):
        payload = {"data": {"assigned": None, "options": {}}}
        service, _ = self._service(live_payload=payload)
        with self.assertRaises(RuntimeError) as ctx:
            service.resolve_server("Mars VPN 1")
        self.assertIn("Mars VPN 1", str(ctx.exception))
        self.assertIn("htb vpn servers", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
