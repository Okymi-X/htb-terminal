"""Challenge API operations: listing, info, files, containers, and flags.

``ChallengeService`` is the single entry point for challenge workflows. Payload
reshaping lives in module-level helpers so the service stays about API calls and
state, and the container bookkeeping lives in :mod:`htb_terminal.containers`.
"""

from __future__ import annotations

import html
import sys
import time
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from htb_terminal.containers import ContainerEntry, ContainerStore
from htb_terminal.http import ApiError, HtbApiClient
from htb_terminal.services.paging import PageCache, cache_key, default_cache_path, paginate_rows
from htb_terminal.services.payloads import difficulty_slug, to_int
from htb_terminal.timefmt import relative_expiry

PER_PAGE = 100
STATES = ("active", "retired", "retired_free")
DIFFICULTIES = ("very-easy", "easy", "medium", "hard", "insane")
DEFAULT_ARCHIVE_PASSWORD = "hackthebox"
MAX_PAGES = 50


def challenge_cache_path() -> Path:
    return default_cache_path("challenges")


@dataclass(frozen=True)
class ChallengeFilters:
    """Filters for ``challenge list``.

    ``state`` and ``difficulty`` are applied by the API; the rest are applied
    locally because the endpoint has no parameter for them. Local filtering is
    also the safety net when the API rejects a server-side filter.
    """

    state: str | None = None
    difficulty: str | None = None
    category: str | None = None
    owned: bool | None = None
    search: str | None = None

    def server_query(self) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if self.state:
            query["state"] = self.state
        if self.difficulty:
            # The endpoint only accepts the bracketed array form.
            query["difficulty[]"] = self.difficulty
        return query

    def matches(self, row: dict[str, Any]) -> bool:
        if self.state and str(row.get("state") or "") != self.state:
            return False
        if self.difficulty and difficulty_slug(str(row.get("difficulty") or "")) != self.difficulty:
            return False
        if self.category and str(row.get("category") or "").casefold() != self.category.casefold():
            return False
        if self.owned is not None and bool(row.get("owned")) != self.owned:
            return False
        if self.search:
            term = self.search.casefold()
            name = str(row.get("name") or "").casefold()
            if term not in name and term != str(row.get("id") or ""):
                return False
        return True


def challenge_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": to_int(item.get("id")),
        "name": item.get("name"),
        "category": item.get("category_name") or item.get("category"),
        "difficulty": item.get("difficulty"),
        "state": item.get("state"),
        "solves": item.get("solves"),
        "owned": item.get("is_owned"),
        "rating": item.get("rating"),
    }


def challenge_summary(challenge: dict[str, Any]) -> dict[str, Any]:
    """Reshape ``/challenge/info`` into what a human wants to read."""
    play_info = challenge.get("play_info") if isinstance(challenge.get("play_info"), dict) else {}
    expires_at = play_info.get("expires_at") or challenge.get("expires_at")
    ports = play_info.get("ports") or challenge.get("docker_ports") or []
    status = play_info.get("status") or challenge.get("docker_status")
    ip = play_info.get("ip") or challenge.get("docker_ip")
    file_name = challenge.get("file_name")
    file_block = None
    if file_name:
        size = to_int(challenge.get("file_size"))
        file_block = {
            "name": file_name,
            "size": human_size(size),
            "bytes": size,
        }
        if challenge.get("file_password"):
            file_block["password"] = challenge["file_password"]

    info_block = None
    if any(play_info.get(key) for key in ("status", "ip", "ports", "expires_at")) or challenge.get(
        "docker_status"
    ):
        info_block = {
            "status": status,
            "ip": ip,
            "ports": list(ports),
            "expires_at": expires_at,
            "expires_in": relative_expiry(expires_at),
        }
    elif "container" in (challenge.get("play_methods") or []):
        # A container challenge with nothing assigned: say so instead of
        # silently dropping the block the user asked about.
        info_block = {"status": "not running"}

    return {
        "challenge": {
            "id": challenge.get("id"),
            "name": challenge.get("name"),
            "category": challenge.get("category_name"),
            "difficulty": challenge.get("difficulty"),
            "state": challenge.get("state"),
            "points": _int_or_raw(challenge.get("points")),
            "solves": challenge.get("solves"),
            "owned": challenge.get("authUserSolve"),
            "play_methods": challenge.get("play_methods"),
            "file": file_block,
            "play_info": info_block,
            "description": _plain_text(challenge.get("description")),
        }
    }


def human_size(value: int | None) -> str | None:
    if value is None:
        return None
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return None


class ChallengeService:
    def __init__(self, client: HtbApiClient, cache: PageCache | None = None):
        self.client = client
        self.cache = cache if cache is not None else PageCache(challenge_cache_path())

    def list(
        self,
        filters: ChallengeFilters | None = None,
        *,
        limit: int | None = 20,
        per_page: int = PER_PAGE,
        max_pages: int = MAX_PAGES,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        selected = filters or ChallengeFilters()
        server_query = selected.server_query()
        fell_back = False

        def fetch_page(page: int) -> tuple[Any, bool]:
            nonlocal server_query, fell_back
            while True:
                try:
                    return self._page(page, per_page, server_query, use_cache=use_cache)
                except ApiError as exc:
                    # A rejected server-side filter must not break the command:
                    # drop the server filters and filter everything locally.
                    if exc.status in {400, 422} and server_query and not fell_back:
                        print(
                            "warning: the API rejected the server-side list filters;"
                            " filtering locally instead.",
                            file=sys.stderr,
                        )
                        server_query = {}
                        fell_back = True
                        continue
                    raise

        rows, meta = paginate_rows(
            fetch_page,
            to_row=challenge_row,
            predicate=selected.matches,
            limit=limit,
            max_pages=max_pages,
        )
        return {"challenges": rows, "count": len(rows), "meta": meta}

    def _page(
        self, page: int, per_page: int, server_query: dict[str, Any], *, use_cache: bool
    ) -> tuple[Any, bool]:
        key = cache_key(page, per_page, server_query)
        if use_cache:
            cached = self.cache.page(key)
            if cached is not None:
                return cached, True
        query = {"page": page, "per_page": per_page, **server_query}
        try:
            payload = self.client.get("/challenges", query=query)
        except ApiError as exc:
            if exc.status != 429:
                raise
            stale = self.cache.page(key, allow_stale=True)
            if stale is None:
                raise ApiError(
                    exc.status,
                    f"{exc} (rate limited and no cached copy of page {page}; try again in a minute)",
                    exc.body,
                ) from exc
            print(
                f"warning: rate limited (HTTP 429); using the cached copy of page {page}.",
                file=sys.stderr,
            )
            return stale, True
        self.cache.store(key, payload)
        return payload, False

    def info_raw(self, challenge_id: int | str) -> dict[str, Any]:
        payload = self.client.get(f"/challenge/info/{int(challenge_id)}")
        challenge = payload.get("challenge") if isinstance(payload, dict) else None
        if not isinstance(challenge, dict):
            raise RuntimeError(f"Could not read challenge {challenge_id} from /challenge/info.")
        return payload

    def info(self, challenge_id: int | str) -> dict[str, Any]:
        return challenge_summary(self.info_raw(challenge_id)["challenge"])

    def download(
        self,
        challenge_id: int | str,
        *,
        out: Path | None = None,
        extract: bool = False,
        password: str = DEFAULT_ARCHIVE_PASSWORD,
    ) -> dict[str, Any]:
        cid = int(challenge_id)
        destination = download_target(cid, out)
        location = self.client.presigned_location(f"/challenge/download/{cid}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        size = self.client.fetch_to_file(location, destination)
        if not zipfile.is_zipfile(destination):
            raise RuntimeError(
                f"{destination} is not a zip archive. HTB served something unexpected"
                " (a container-only challenge has no file); delete it and check"
                f" 'htb challenge info {cid}'."
            )
        result: dict[str, Any] = {
            "challenge_id": cid,
            "output": str(destination),
            "size": size,
            "size_human": human_size(size),
        }
        if extract:
            result.update(extract_archive(destination, password))
        return result

    def start(
        self,
        challenge_id: int | str,
        *,
        force: bool = False,
        wait: int = 180,
        interval: int = 5,
    ) -> dict[str, Any]:
        """Start one container, enforcing the single running instance rule."""
        cid = int(challenge_id)
        store = ContainerStore()
        tracked = store.running(exclude=cid)
        if tracked:
            if not force:
                ids = ", ".join(str(entry.challenge_id) for entry in tracked)
                raise RuntimeError(
                    f"challenge {ids} is already running (tracked locally). HTB allows one"
                    " challenge container at a time and silently kills the previous one"
                    " when you start another, so this start is refused. Stop it first with"
                    " 'htb challenge stop', or re-run with --force to stop it and take the"
                    " slot."
                )
            for entry in tracked:
                print(
                    f"stopping challenge {entry.challenge_id} to free the single container slot (--force)",
                    file=sys.stderr,
                )
                self._stop_one(entry.challenge_id, store)

        response = self.client.post("/container/start", {"challenge_id": cid})
        # Track the slot before waiting: if the poll fails or is interrupted, the
        # container is still running and must block the next start, or HTB would
        # silently kill it.
        entry = ContainerEntry(
            challenge_id=cid,
            status="starting",
            started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        store.track(entry)
        play_info = self._wait_ready(cid, wait=wait, interval=interval)
        entry = replace(
            entry,
            status=str(play_info.get("status") or "ready"),
            ip=play_info.get("ip"),
            ports=tuple(to_int(port) for port in play_info.get("ports") or [] if to_int(port) is not None),
            expires_at=play_info.get("expires_at"),
        )
        store.track(entry)
        return {
            "challenge_id": cid,
            "status": entry.status,
            "ip": entry.ip,
            "ports": list(entry.ports),
            "expires_at": entry.expires_at,
            "expires_in": relative_expiry(entry.expires_at),
            "message": _message(response),
        }

    def _wait_ready(self, challenge_id: int, *, wait: int, interval: int) -> dict[str, Any]:
        """Poll ``challenge/info`` until ``play_info.status`` is ready.

        The field is null for the first 30-90 seconds after a start, so this is
        a poll, not a one-shot read.
        """
        deadline = time.monotonic() + wait
        while True:
            challenge = self.info_raw(challenge_id)["challenge"]
            play_info = challenge.get("play_info") if isinstance(challenge.get("play_info"), dict) else {}
            status = play_info.get("status")
            ip = play_info.get("ip") or challenge.get("docker_ip")
            if status == "ready" and ip:
                return {
                    "status": status,
                    "ip": ip,
                    "ports": play_info.get("ports") or challenge.get("docker_ports") or [],
                    "expires_at": play_info.get("expires_at"),
                }
            if time.monotonic() + interval > deadline:
                raise RuntimeError(
                    f"Container for challenge {challenge_id} did not become ready within"
                    f" {wait}s (last status: {status or 'pending'}). Check"
                    f" 'htb challenge status {challenge_id}' in a moment, or start it again."
                )
            print(f"waiting for container to become ready ({status or 'pending'})...", file=sys.stderr)
            time.sleep(interval)

    def stop(self, challenge_id: int | str | None = None) -> dict[str, Any]:
        store = ContainerStore()
        if challenge_id is None:
            targets = [entry.challenge_id for entry in store.running()]
            if not targets:
                raise RuntimeError(
                    "No tracked challenge container. Pass an id: 'htb challenge stop <id>'."
                )
        else:
            targets = [int(challenge_id)]
        stopped = [self._stop_one(cid, store) for cid in targets]
        return stopped[0] if len(stopped) == 1 else {"stopped": stopped}

    def _stop_one(self, challenge_id: int, store: ContainerStore) -> dict[str, Any]:
        response = self.client.post("/container/stop", {"challenge_id": int(challenge_id)})
        store.remove(int(challenge_id))
        return {"challenge_id": int(challenge_id), "message": _message(response)}

    def status(self, challenge_id: int | str | None = None) -> dict[str, Any]:
        store = ContainerStore()
        entries = [
            entry
            for entry in store.load()
            if challenge_id is None or entry.challenge_id == int(challenge_id)
        ]
        wanted = int(challenge_id) if challenge_id is not None else None
        if not entries and wanted is None:
            raise RuntimeError(
                "No tracked challenge containers. Start one with 'htb challenge start <id>'."
            )
        rows = [self._status_row(entry) for entry in entries]
        if not rows and wanted is not None:
            # Untracked id (started elsewhere): still report the live view when
            # the API has one, but do not invent an empty row.
            row = self._status_row(None, wanted)
            if not row.get("status"):
                raise RuntimeError(
                    f"No tracked container for challenge {wanted}, and /challenge/info"
                    " reported no play state for it."
                )
            rows.append(row)
        return {"containers": rows}

    def _status_row(self, entry: ContainerEntry | None, challenge_id: int | None = None) -> dict[str, Any]:
        cid = entry.challenge_id if entry is not None else challenge_id
        row: dict[str, Any] = {
            "id": cid,
            "name": entry.name if entry is not None else None,
            "status": entry.status if entry is not None else None,
            "ip": entry.ip if entry is not None else None,
            "ports": list(entry.ports) if entry is not None else [],
            "expires_at": entry.expires_at if entry is not None else None,
            "tracked": entry is not None,
        }
        try:
            challenge = self.info_raw(cid)["challenge"]
        except (ApiError, RuntimeError, TypeError):
            row["expires"] = relative_expiry(row.get("expires_at"))
            row["ports_text"] = _ports_text(row.get("ports"))
            return row
        play_info = challenge.get("play_info") if isinstance(challenge.get("play_info"), dict) else {}
        row["name"] = challenge.get("name") or row["name"]
        row["status"] = play_info.get("status") or row["status"]
        row["ip"] = play_info.get("ip") or row["ip"]
        row["ports"] = list(play_info.get("ports") or row["ports"] or [])
        row["expires_at"] = play_info.get("expires_at") or row["expires_at"]
        row["expires"] = relative_expiry(row.get("expires_at"))
        row["ports_text"] = _ports_text(row.get("ports"))
        return row

    def own(self, challenge_id: int | str, flag: str) -> dict[str, Any]:
        cid = int(challenge_id)
        submitted = flag.strip()
        if not submitted:
            raise ValueError("The flag must not be empty.")
        response = self.client.post("/challenge/own", {"challenge_id": cid, "flag": submitted})
        message = _message(response) or "Flag accepted."
        if _looks_rejected(message):
            raise RuntimeError(f"Challenge {cid}: {message}")
        return {"challenge_id": cid, "accepted": True, "message": message}


def download_target(challenge_id: int, out: Path | None) -> Path:
    """Where a challenge archive is saved: ``challenges/ch<id>/ch<id>.zip``.

    ``out`` is treated as a directory when it already is one or carries no
    suffix, so ``-o downloads`` and ``-o downloads/ch.zip`` both behave the way
    they read.
    """
    if out is None:
        return Path("challenges") / f"ch{challenge_id}" / f"ch{challenge_id}.zip"
    path = Path(out)
    if path.is_dir() or not path.suffix:
        return path / f"ch{challenge_id}.zip"
    return path


def extract_archive(archive_path: Path, password: str) -> dict[str, Any]:
    destination = archive_path.parent / archive_path.stem
    try:
        with zipfile.ZipFile(archive_path) as archive:
            _guard_member_paths(archive, destination)
            archive.extractall(destination, pwd=password.encode("utf-8"))
            members = [name for name in archive.namelist() if not name.endswith("/")]
    except RuntimeError as exc:
        # zipfile signals a wrong password with a bare RuntimeError.
        raise RuntimeError(
            f"Could not extract {archive_path}: {exc}. The archive password is not"
            f" {password!r}; retry with --password."
        ) from exc
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"{archive_path} is not a readable zip archive: {exc}") from exc
    return {"extracted_to": str(destination), "files": len(members)}


def _guard_member_paths(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        resolved = (root / member.filename).resolve()
        if resolved != root and root not in resolved.parents:
            raise RuntimeError(f"archive member escapes the destination directory: {member.filename}")


def _ports_text(ports: Any) -> str:
    if not isinstance(ports, list) or not ports:
        return ""
    return ",".join(str(port) for port in ports)


def _int_or_raw(value: Any) -> Any:
    parsed = to_int(value)
    return parsed if parsed is not None else value


def _plain_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return html.unescape(value)


def _message(response: Any) -> str | None:
    if isinstance(response, dict):
        message = response.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return None


def _looks_rejected(message: str) -> bool:
    lowered = message.casefold()
    return any(word in lowered for word in ("incorrect", "wrong", "invalid", "not correct"))
