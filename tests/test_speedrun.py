from __future__ import annotations

import io
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from htb_terminal.services.speedrun import SpeedrunService
from htb_terminal.ui import StepRunner


class FakeVpn:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def switch(self, server: str) -> Any:
        self.calls.append(("switch", server))

    def download_ovpn(self, server: str, variant: int, output: Path) -> Path:
        self.calls.append(("download", server, variant, output))
        return output


class FakeMachine:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def resolve_id(self, target: str) -> int:
        self.calls.append(("resolve", target))
        return 478

    def start_with_retry(self, target: str, mode: str, *, retry_for: int, interval: int) -> Any:
        self.calls.append(("spawn", target, mode, retry_for, interval))
        return {"message": "deployed"}

    def wait_for_active_ip(self, machine_id: int) -> dict[str, Any]:
        self.calls.append(("wait_ip", machine_id))
        return {"id": machine_id, "name": "Seasonal", "ip": "10.10.11.50"}


class FakeProcess:
    def poll(self) -> None:
        return None


class SpeedrunLaunchTests(unittest.TestCase):
    def _run(self) -> tuple[FakeVpn, FakeMachine, list[Any], Any]:
        vpn, machine = FakeVpn(), FakeMachine()
        mtu_calls: list[Any] = []
        stream = io.StringIO()
        ui = StepRunner(color="never", stream=stream)
        service = SpeedrunService(vpn, machine, ui)

        with (
            mock.patch("htb_terminal.services.speedrun.ensure_root"),
            mock.patch("htb_terminal.services.speedrun.start_openvpn", return_value=FakeProcess()),
            mock.patch("htb_terminal.services.speedrun.wait_for_interface"),
            mock.patch(
                "htb_terminal.services.speedrun.set_mtu",
                side_effect=lambda name, mtu: mtu_calls.append((name, mtu)),
            ),
        ):
            result = service.launch(
                "Seasonal",
                "us-free-1",
                output=Path("lab-vpn.ovpn"),
                interface="tun0",
                mtu=1300,
            )
        return vpn, machine, mtu_calls, result

    def test_orders_steps_and_returns_machine_info(self) -> None:
        vpn, machine, mtu_calls, result = self._run()

        self.assertEqual("10.10.11.50", result.machine["ip"])
        self.assertEqual("tun0", result.interface)
        self.assertEqual(1300, result.mtu)
        self.assertEqual([("tun0", 1300)], mtu_calls)
        # VPN switched + downloaded, machine resolved + spawned + polled.
        self.assertEqual(("switch", "us-free-1"), vpn.calls[0])
        self.assertEqual(("resolve", "Seasonal"), machine.calls[0])
        self.assertIn(("spawn", "478", "auto", 900, 15), machine.calls)
        self.assertIn(("wait_ip", 478), machine.calls)

    def test_launch_runs_without_error(self) -> None:
        _vpn, _machine, _mtu, result = self._run()
        self.assertEqual("Seasonal", result.machine["name"])


if __name__ == "__main__":
    unittest.main()
