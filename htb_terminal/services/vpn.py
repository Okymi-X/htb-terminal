from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from htb_terminal.http import HtbApiClient


@dataclass(frozen=True)
class VpnServer:
    id: int
    name: str
    scope: str
    location: str


KNOWN_VPN_SERVERS = {
    "eu-sp-1": VpnServer(412, "EU Starting Point 1", "starting-point", "EU"),
    "us-sp-1": VpnServer(414, "US Starting Point 1", "starting-point", "US"),
    "eu-free-1": VpnServer(1, "EU Free 1", "machines", "EU"),
    "eu-free-2": VpnServer(201, "EU Free 2", "machines", "EU"),
    "eu-free-3": VpnServer(253, "EU Free 3", "machines", "EU"),
    "us-free-1": VpnServer(113, "US Free 1", "machines", "US"),
    "us-free-2": VpnServer(202, "US Free 2", "machines", "US"),
    "us-free-3": VpnServer(254, "US Free 3", "machines", "US"),
    "au-free-1": VpnServer(177, "AU Free 1", "machines", "AU"),
    "sg-free-1": VpnServer(251, "SG Free 1", "machines", "SG"),
}


class VpnService:
    def __init__(self, client: HtbApiClient):
        self.client = client

    def switch(self, server: str) -> Any:
        server_id = resolve_server_id(server)
        return self.client.post(f"/connections/servers/switch/{server_id}")

    def download_ovpn(self, server: str, variant: int, output: Path) -> Path:
        server_id = resolve_server_id(server)
        content = self.client.download(f"/access/ovpnfile/{server_id}/{variant}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        return output

    def connect(
        self,
        server: str,
        variant: int,
        output: Path,
        openvpn_command: list[str],
    ) -> int:
        ensure_openvpn_privileges(openvpn_command)
        self.switch(server)
        ovpn_path = self.download_ovpn(server, variant, output)
        command = [*openvpn_command, "--config", str(ovpn_path)]
        return subprocess.call(command)


def ensure_openvpn_privileges(command: list[str]) -> None:
    if not command:
        raise RuntimeError("Empty OpenVPN command.")
    if not hasattr(os, "geteuid") or os.geteuid() == 0:
        return
    if Path(command[0]).name in {"sudo", "doas", "pkexec"}:
        return
    raise RuntimeError(
        "OpenVPN needs root privileges to create the tun interface. "
        "Re-run as root, or keep the default --openvpn-command \"sudo openvpn\" "
        "so the OpenVPN process is elevated."
    )


def resolve_server_id(value: str) -> int:
    normalized = value.strip().lower()
    if normalized.isdigit():
        return int(normalized)
    if normalized in KNOWN_VPN_SERVERS:
        return KNOWN_VPN_SERVERS[normalized].id
    known = ", ".join(sorted(KNOWN_VPN_SERVERS))
    raise RuntimeError(f"Unknown VPN server {value!r}. Known aliases: {known}")


def vpn_rows() -> list[dict[str, Any]]:
    return [
        {
            "alias": alias,
            "id": server.id,
            "name": server.name,
            "scope": server.scope,
            "location": server.location,
        }
        for alias, server in KNOWN_VPN_SERVERS.items()
    ]

