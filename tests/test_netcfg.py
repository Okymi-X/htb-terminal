from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from htb_terminal.netcfg import (
    ensure_openvpn_active,
    set_mtu,
    start_openvpn,
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
    def test_start_openvpn_writes_private_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "openvpn.log"
            log.write_bytes(b"old")
            log.chmod(0o644)

            with mock.patch("htb_terminal.netcfg.subprocess.Popen") as popen:
                start_openvpn(Path("lab.ovpn"), log_path=log)

            popen.assert_called_once()
            if os.name == "posix":
                self.assertEqual(0o600, stat.S_IMODE(log.stat().st_mode))

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW is unavailable")
    def test_start_openvpn_refuses_symlink_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.write_bytes(b"keep")
            log = Path(tmp) / "openvpn.log"
            log.symlink_to(target)

            with (
                mock.patch("htb_terminal.netcfg.subprocess.Popen") as popen,
                self.assertRaisesRegex(RuntimeError, "securely open"),
            ):
                start_openvpn(Path("lab.ovpn"), log_path=log)

            popen.assert_not_called()
            self.assertEqual(b"keep", target.read_bytes())

    @unittest.skipUnless(hasattr(os, "link"), "hard links are unavailable")
    def test_start_openvpn_refuses_hard_link_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.write_bytes(b"keep")
            log = Path(tmp) / "openvpn.log"
            os.link(target, log)

            with (
                mock.patch("htb_terminal.netcfg.subprocess.Popen") as popen,
                self.assertRaisesRegex(RuntimeError, "securely open"),
            ):
                start_openvpn(Path("lab.ovpn"), log_path=log)

            popen.assert_not_called()
            self.assertEqual(b"keep", target.read_bytes())

    def test_start_openvpn_wraps_missing_command(self) -> None:
        with (
            mock.patch(
                "htb_terminal.netcfg.subprocess.Popen",
                side_effect=FileNotFoundError("missing"),
            ),
            self.assertRaisesRegex(RuntimeError, "Could not start OpenVPN"),
        ):
            start_openvpn(Path("lab.ovpn"))

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


class SetMtuFailureTests(unittest.TestCase):
    def test_missing_ip_command_has_install_hint(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Install iproute2"):
            set_mtu(
                "tun0",
                1300,
                runner=mock.Mock(side_effect=FileNotFoundError("missing")),
            )

    def test_ip_command_failure_reports_exit_code(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "code 2"):
            set_mtu(
                "tun0",
                1300,
                runner=mock.Mock(
                    side_effect=subprocess.CalledProcessError(2, ["ip"])
                ),
            )


if __name__ == "__main__":
    unittest.main()
