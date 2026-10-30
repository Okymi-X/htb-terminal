"""Single-slot bookkeeping for challenge containers.

HTB runs one challenge instance per account: starting a second container
silently terminates the first one instead of returning an error. That makes
"which instance did I start" state the CLI has to remember, because the API
offers no way to list running containers.

The store is a small JSON file under the user config directory. It is advisory
only: it never talks to the API, and a corrupt file degrades to "nothing
tracked" rather than breaking a command.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from htb_terminal.config import user_config_dir
from htb_terminal.files import write_private_file
from htb_terminal.services.payloads import to_int
from htb_terminal.timefmt import relative_expiry

_RUNNING_STATUSES = ("ready", "starting", "pending")


def containers_path() -> Path:
    """Where tracked containers live, next to the token and the page cache."""
    return user_config_dir() / "containers.json"


@dataclass(frozen=True)
class ContainerEntry:
    """One challenge instance we started, as far as the CLI knows."""

    challenge_id: int
    status: str = "ready"
    ip: str | None = None
    ports: tuple[int, ...] = field(default_factory=tuple)
    expires_at: str | None = None
    started_at: str | None = None
    name: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "status": self.status,
            "ip": self.ip,
            "ports": list(self.ports),
            "expires_at": self.expires_at,
            "started_at": self.started_at,
            "name": self.name,
        }

    @classmethod
    def from_json(cls, data: Any) -> ContainerEntry | None:
        if not isinstance(data, dict):
            return None
        challenge_id = to_int(data.get("challenge_id"))
        if challenge_id is None:
            return None
        ports: list[int] = []
        raw_ports = data.get("ports")
        if isinstance(raw_ports, list):
            for value in raw_ports:
                port = to_int(value)
                if port is not None:
                    ports.append(port)
        port_text = data.get("ports")
        if isinstance(port_text, str):
            for chunk in port_text.replace(",", " ").split():
                port = to_int(chunk)
                if port is not None:
                    ports.append(port)
        return cls(
            challenge_id=challenge_id,
            status=str(data.get("status") or "ready"),
            ip=data.get("ip") if isinstance(data.get("ip"), str) else None,
            ports=tuple(ports),
            expires_at=data.get("expires_at") if isinstance(data.get("expires_at"), str) else None,
            started_at=data.get("started_at") if isinstance(data.get("started_at"), str) else None,
            name=data.get("name") if isinstance(data.get("name"), str) else None,
        )

    def is_running(self) -> bool:
        """Tracked as live: a running status that has not expired yet."""
        if self.status not in _RUNNING_STATUSES:
            return False
        if not self.expires_at:
            return True
        return relative_expiry(self.expires_at) != "expired"


class ContainerStore:
    """Read and write the tracked-container file."""

    def __init__(self, path: Path | None = None):
        self.path = path or containers_path()

    def load(self) -> list[ContainerEntry]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print(
                f"warning: ignoring unreadable container state file {self.path};"
                " 'htb challenge status' will not show earlier instances.",
                file=sys.stderr,
            )
            return []
        raw_entries = data.get("containers") if isinstance(data, dict) else None
        if not isinstance(raw_entries, list):
            return []
        entries = [ContainerEntry.from_json(item) for item in raw_entries]
        return [entry for entry in entries if entry is not None]

    def save(self, entries: list[ContainerEntry]) -> None:
        payload = {"containers": [entry.to_json() for entry in entries]}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_private_file(self.path, (json.dumps(payload, indent=2) + "\n").encode("utf-8"))
        except (OSError, RuntimeError) as exc:
            # Tracking is bookkeeping, not the operation itself: warn and go on
            # so a read-only HOME does not block a start that already happened.
            print(f"warning: could not save container state: {exc}", file=sys.stderr)

    def track(self, entry: ContainerEntry) -> None:
        entries = [item for item in self.load() if item.challenge_id != entry.challenge_id]
        entries.append(entry)
        self.save(entries)

    def remove(self, challenge_id: int) -> None:
        entries = [item for item in self.load() if item.challenge_id != int(challenge_id)]
        self.save(entries)

    def running(self, *, exclude: int | None = None) -> list[ContainerEntry]:
        return [
            entry
            for entry in self.load()
            if entry.is_running() and (exclude is None or entry.challenge_id != int(exclude))
        ]
