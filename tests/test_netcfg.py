from __future__ import annotations

import unittest

from htb_terminal.netcfg import set_mtu, wait_for_interface


class SetMtuTests(unittest.TestCase):
    def test_runs_ip_link_with_check(self) -> None:
        calls = []

        def runner(args, check=False):
            calls.append((args, check))

        set_mtu("tun0", 1300, runner=runner)
        self.assertEqual([(["ip", "link", "set", "tun0", "mtu", "1300"], True)], calls)


class WaitForInterfaceTests(unittest.TestCase):
    def test_returns_once_interface_appears(self) -> None:
        seen = {"calls": 0}

        def exists(_name: str) -> bool:
            seen["calls"] += 1
            return seen["calls"] >= 3  # appears on the third probe

        slept: list[float] = []
        wait_for_interface(
            "tun0",
            exists=exists,
            sleep=slept.append,
            monotonic=lambda: 0.0,
            timeout=10,
            interval=0.5,
        )
        self.assertEqual(2, len(slept))

    def test_raises_when_openvpn_dies(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            wait_for_interface(
                "tun0",
                exists=lambda _n: False,
                is_alive=lambda: False,
                sleep=lambda _s: None,
                monotonic=lambda: 0.0,
            )
        self.assertIn("OpenVPN exited", str(ctx.exception))

    def test_times_out(self) -> None:
        clock = iter([0.0, 0.0, 5.0, 31.0])
        with self.assertRaises(RuntimeError) as ctx:
            wait_for_interface(
                "tun0",
                exists=lambda _n: False,
                sleep=lambda _s: None,
                monotonic=lambda: next(clock),
                timeout=30,
            )
        self.assertIn("did not come up", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
