from __future__ import annotations

import errno
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from htb_terminal.http import ApiError, HtbApiClient
from htb_terminal.services.payloads import to_int

# Server pools exposed by GET /connections/servers. "labs" covers regular
# machines including the VIP / VIP+ / dedicated pools a paid account unlocks.
VPN_PRODUCTS = ("labs", "starting_point", "competitive", "fortresses", "release_arena")


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
        server_id = self.resolve_server(server)
        return self.client.post(f"/connections/servers/switch/{server_id}")

    def list_servers(self, product: str = "labs") -> Any:
        """Fetch the VPN servers the account can actually use for ``product``.

        Unlike the static :data:`KNOWN_VPN_SERVERS` table this reflects the
        live entitlement, so VIP / VIP+ / dedicated lab servers show up for
        paid accounts (retired machines only deploy on those).
        """
        return self.client.get("/connections/servers", query={"product": product})

    def download_ovpn(self, server: str, variant: int, output: Path) -> Path:
        server_id = self.resolve_server(server)
        content = self.client.download(f"/access/ovpnfile/{server_id}/{variant}")
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_private_file(output, content)
        return output

    def resolve_server(self, value: str) -> int:
        """Resolve a server value to its numeric ID.

        Accepts, in priority order:
        1. A numeric ID ("289")
        2. A static alias ("us-free-1")
        3. A live friendly name from ``/connections/servers`` ("US Machines VIP+ 1")

        The live lookup is only attempted when the first two fail, so it adds no
        API call for the common numeric-ID and alias paths.
        """
        try:
            return resolve_server_id(value)
        except RuntimeError:
            pass
        return self._resolve_server_by_name(value)

    def _resolve_server_by_name(self, name: str) -> int:
        """Search the live server listing across all products for *name*."""
        needle = name.strip().lower()
        lookup_errors: list[ApiError] = []
        successful_lookup = False
        for product in VPN_PRODUCTS:
            try:
                rows = server_rows(self.list_servers(product))
            except ApiError as exc:
                lookup_errors.append(exc)
                continue
            successful_lookup = True
            for row in rows:
                friendly = (row.get("name") or "").lower()
                if friendly == needle:
                    return row["id"]
        if not successful_lookup and lookup_errors:
            last_error = lookup_errors[-1]
            raise RuntimeError(
                f"Could not query HTB VPN servers while resolving {name!r}: {last_error}"
            ) from last_error
        known = ", ".join(sorted(KNOWN_VPN_SERVERS))
        raise RuntimeError(
            f"Unknown VPN server {name!r}. Not a numeric ID, known alias, or "
            f"live server name. Known aliases: {known}. "
            "Use 'htb vpn servers' to see live server names and IDs."
        )

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
        try:
            return subprocess.call(command)
        except OSError as exc:
            raise RuntimeError(
                f"Could not start OpenVPN command {openvpn_command[0]!r}: {exc}"
            ) from exc


def _write_private_file(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise OSError(errno.EINVAL, "output must be a single-link regular file")
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        os.ftruncate(descriptor, 0)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(content)
    except OSError as exc:
        raise RuntimeError(f"Could not securely write VPN config {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


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


def server_rows(payload: Any) -> list[dict[str, Any]]:
    """Flatten ``/connections/servers`` into table rows.

    The API nests servers as ``data.options[product][location].servers[id]``
    and marks the current pick under ``data.assigned``. We walk it defensively
    — any group object carrying a ``servers`` map is expanded — so VIP, VIP+,
    and dedicated pools all surface regardless of their grouping labels. The
    assigned server sorts first.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    assigned = data.get("assigned") if isinstance(data.get("assigned"), dict) else None
    assigned_id = to_int(assigned.get("id")) if assigned else None

    rows: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(server: dict[str, Any], group: str) -> None:
        sid = to_int(server.get("id"))
        if sid is None or sid in seen:
            return
        seen.add(sid)
        rows.append(
            {
                "id": sid,
                "name": server.get("friendly_name"),
                "group": group,
                "location": server.get("location"),
                "clients": server.get("current_clients"),
                "full": bool(server.get("full")),
                "assigned": sid == assigned_id,
            }
        )

    def walk(node: Any, group: str) -> None:
        if not isinstance(node, dict):
            return
        servers = node.get("servers")
        if isinstance(servers, dict):
            label = str(node.get("name") or group)
            for server in servers.values():
                if isinstance(server, dict):
                    add(server, label)
            return
        for key, value in node.items():
            child_group = str(value.get("name") or key) if isinstance(value, dict) else group
            walk(value, child_group)

    walk(data.get("options"), "")
    if assigned is not None:
        # Make sure the active server shows even if it is absent from options.
        add(assigned, str(assigned.get("location_type_friendly") or "assigned"))

    rows.sort(key=lambda r: (not r["assigned"], r["group"] or "", r["id"]))
    return rows
