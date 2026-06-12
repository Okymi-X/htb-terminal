from __future__ import annotations

import unittest
from unittest import mock

from htb_terminal.services.vpn import ensure_openvpn_privileges, resolve_server_id


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


if __name__ == "__main__":
    unittest.main()
