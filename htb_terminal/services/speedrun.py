"""Speedrun orchestration.

``SpeedrunService`` composes the VPN, machine, host-network, and UI pieces into
the season-release flow: connect the VPN, raise/lower the tunnel MTU, then spawn
the machine with capacity retries and wait for its IP. It owns sequencing only;
each underlying step lives in its own module.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from htb_terminal.netcfg import ensure_root, set_mtu, start_openvpn, wait_for_interface
from htb_terminal.services.machines import MachineService
from htb_terminal.services.vpn import VpnService
from htb_terminal.ui import StepRunner


@dataclass
class SpeedrunResult:
    process: subprocess.Popen
    interface: str
    mtu: int
    machine: dict[str, Any]


class SpeedrunService:
    def __init__(self, vpn: VpnService, machine: MachineService, ui: StepRunner):
        self.vpn = vpn
        self.machine = machine
        self.ui = ui

    def launch(
        self,
        target: str,
        server: str,
        *,
        output: Path,
        variant: int = 0,
        interface: str = "tun0",
        mtu: int = 1300,
        mode: str = "auto",
        retry_for: int = 900,
        interval: int = 15,
        openvpn_command: list[str] | None = None,
        log_path: Path | None = None,
    ) -> SpeedrunResult:
        ensure_root()
        command = tuple(openvpn_command or ("openvpn",))

        with self.ui.step(f"resolve machine {target!r}"):
            machine_id = self.machine.resolve_id(target)
        with self.ui.step(f"switch vpn server {server}"):
            self.vpn.switch(server)
        with self.ui.step("download ovpn config"):
            ovpn = self.vpn.download_ovpn(server, variant, output)
        with self.ui.step("start openvpn"):
            process = start_openvpn(ovpn, command=command, log_path=log_path)
        with self.ui.step(f"wait for {interface}"):
            wait_for_interface(interface, is_alive=lambda: process.poll() is None)
        with self.ui.step(f"set {interface} mtu {mtu}"):
            set_mtu(interface, mtu)
        with self.ui.step("spawn machine"):
            self.machine.start_with_retry(str(machine_id), mode, retry_for=retry_for, interval=interval)
        with self.ui.step("wait for machine ip"):
            info = self.machine.wait_for_active_ip(machine_id)

        return SpeedrunResult(process=process, interface=interface, mtu=mtu, machine=info)
