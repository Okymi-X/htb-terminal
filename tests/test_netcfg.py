from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from htb_terminal.netcfg import (
    ensure_openvpn_active,
    set_mtu,
    stop_openvpn,
    wait_for_interface,
)


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


class OpenvpnLifecycleTests(unittest.TestCase):
    def test_active_requires_running_process_and_interface(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None

        ensure_openvpn_active(process, "tun0", exists=lambda _name: True)

    def test_active_reports_openvpn_exit_and_log(self) -> None:
        process = mock.Mock()
        process.poll.return_value = 1

        with self.assertRaises(RuntimeError) as ctx:
            ensure_openvpn_active(
                process,
                "tun0",
                exists=lambda _name: True,
                log_path=Path("lab-vpn.log"),
            )

        self.assertIn("code 1", str(ctx.exception))
        self.assertIn("lab-vpn.log", str(ctx.exception))

    def test_active_reports_missing_interface(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None

        with self.assertRaises(RuntimeError) as ctx:
            ensure_openvpn_active(process, "tun0", exists=lambda _name: False)

        self.assertIn("tun0 is no longer active", str(ctx.exception))

    def test_stop_terminates_and_reaps_openvpn(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None

        stop_openvpn(process, timeout=3)

        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=3)
        process.kill.assert_not_called()

    def test_stop_kills_openvpn_after_timeout(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = [
            subprocess.TimeoutExpired("openvpn", 3),
            0,
        ]

        stop_openvpn(process, timeout=3)

        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual([mock.call(timeout=3), mock.call()], process.wait.call_args_list)

    def test_stop_is_noop_after_openvpn_exits(self) -> None:
        process = mock.Mock()
        process.poll.return_value = 0

        stop_openvpn(process)

        process.terminate.assert_not_called()
        process.wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
