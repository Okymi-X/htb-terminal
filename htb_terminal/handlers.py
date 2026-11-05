"""Command handlers: the controller layer between parsed args and services.

Each handler takes ``(args, client)`` and returns a value to render (dict/list
printed as JSON or pretty text), or ``None`` when it prints its own output.
Parser definitions live in :mod:`htb_terminal.parser`; rendering in
:mod:`htb_terminal.output`.
"""

from __future__ import annotations

import argparse
import getpass
import json
import math
import shlex
import sys
import time
from typing import Any

from htb_terminal import box
from htb_terminal.completion import completion_script
from htb_terminal.config import load_config, save_token
from htb_terminal.http import ApiError, HtbApiClient
from htb_terminal.netcfg import stop_openvpn
from htb_terminal.output import (
    color_enabled,
    print_json,
    print_pretty,
    print_status_line,
    print_table,
)
from htb_terminal.services.challenges import (
    ChallengeFilters,
    ChallengeService,
    challenge_summary,
)
from htb_terminal.services.labs import LabService
from htb_terminal.services.machines import MachineService
from htb_terminal.services.payloads import machine_rows
from htb_terminal.services.progress import ProgressService
from htb_terminal.services.sherlocks import SherlockFilters, SherlockService
from htb_terminal.services.speedrun import SpeedrunService
from htb_terminal.services.user import UserService
from htb_terminal.services.vpn import VpnService, server_rows, vpn_rows
from htb_terminal.ui import StepRunner


def _machine_service(client: HtbApiClient) -> MachineService:
    return MachineService(client)


def _challenge_service(client: HtbApiClient) -> ChallengeService:
    return ChallengeService(client)


def _lab_service(client: HtbApiClient) -> LabService:
    return LabService(client)


def _progress_service(client: HtbApiClient) -> ProgressService:
    return ProgressService(client)


def _sherlock_service(client: HtbApiClient) -> SherlockService:
    return SherlockService(client)


def _vpn_service(client: HtbApiClient) -> VpnService:
    return VpnService(client)


def _prompt_token() -> str:
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if piped:
            return piped
        raise ValueError("No token provided on stdin.")
    try:
        entered = getpass.getpass("Paste your HTB App Token (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        raise ValueError("Token entry cancelled.") from None
    if not entered:
        raise ValueError("No token entered.")
    return entered


def init(args: argparse.Namespace, client: HtbApiClient | None) -> Any:
    token = args.token or _prompt_token()
    path = save_token(token, args.token_file)
    result: dict[str, Any] = {"saved": str(path)}
    if args.check:
        config = load_config(token_file=path, base_url=args.base_url)
        verify_client = HtbApiClient(config.base_url, config.token, timeout=args.timeout)
        result["verified_as"] = UserService(verify_client).whoami().get("name")
    return result


def machine_profile(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _machine_service(client).profile(args.target)


def machine_active(args: argparse.Namespace, client: HtbApiClient) -> Any:
    service = _machine_service(client)
    if args.json:
        return service.active_with_profile()
    summary = service.active_summary(include_details=args.details)
    if args.oneline:
        info = summary.get("info") if isinstance(summary, dict) else None
        print_status_line(info if isinstance(info, dict) else {}, color=args.color)
        return None
    return summary


def machine_list(args: argparse.Namespace, client: HtbApiClient) -> Any:
    service = _machine_service(client)
    selected = sum(bool(value) for value in [args.retired, args.todo, args.unreleased, args.sp_tier])
    if selected > 1:
        raise ValueError("Choose only one list filter.")
    if args.retired:
        payload = service.list_retired(args.page)
    elif args.todo:
        payload = service.list_todo()
    elif args.unreleased:
        payload = service.list_unreleased()
    elif args.sp_tier:
        payload = service.list_starting_point(args.sp_tier)
    else:
        payload = service.list_playable(args.page)

    rows = machine_rows(payload)
    rows = _filter_machine_rows(rows, difficulty=args.difficulty, os_name=args.os_name)
    if args.json:
        return rows
    print_table(
        rows,
        ["id", "name", "os", "difficulty", "points", "active", "spawned", "free"],
        color=args.color,
        wide=args.wide,
    )
    return None


def _filter_machine_rows(
    rows: list[dict[str, Any]],
    *,
    difficulty: str | None = None,
    os_name: str | None = None,
) -> list[dict[str, Any]]:
    """Local filters for ``machine list``.

    The list endpoints take no difficulty/os query parameters (unlike
    ``challenge list``, which filters server-side), so these have to be applied to
    the page after it arrives.
    """
    filtered = rows
    if difficulty:
        wanted = difficulty.strip().casefold()
        filtered = [row for row in filtered if str(row.get("difficulty") or "").casefold() == wanted]
    if os_name:
        wanted = os_name.strip().casefold()
        filtered = [row for row in filtered if str(row.get("os") or "").casefold() == wanted]
    return filtered


def machine_search(args: argparse.Namespace, client: HtbApiClient) -> Any:
    if args.retired and args.all:
        raise ValueError("Choose either --retired or --all, not both.")

    rows = _machine_service(client).search(
        args.query,
        retired_only=args.retired,
        include_retired=args.all,
        include_profiles=args.profiles,
        limit=args.limit,
        max_pages=args.max_pages,
    )
    if args.json:
        return rows
    print_table(
        rows,
        ["id", "name", "os", "difficulty", "points", "retired", "active", "spawned", "free"],
        color=args.color,
        wide=args.wide,
    )
    return None


def machine_start(args: argparse.Namespace, client: HtbApiClient) -> Any:
    service = _machine_service(client)
    if not args.wait:
        return service.start(args.target, args.mode)

    machine_id = service.resolve_id(args.target)
    deadline = time.monotonic() + args.retry_for
    result = service.start_with_retry(
        str(machine_id),
        args.mode,
        retry_for=args.retry_for,
        interval=args.interval,
    )
    # Honor --interval (cadence) and --retry-for (budget) for the IP poll too,
    # so the whole --wait flow respects the limits the user asked for instead of
    # a hidden 300s cap.
    info = service.wait_for_active_ip(
        machine_id,
        timeout=max(0, math.ceil(deadline - time.monotonic())),
        interval=args.interval,
    )
    return {
        "id": machine_id,
        "name": info.get("name"),
        "ip": info.get("ip"),
        "spawn": result,
    }


def machine_stop(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _machine_service(client).stop(args.target)


def machine_reset(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _machine_service(client).reset(args.target)


def machine_extend(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _machine_service(client).extend(args.target)


def machine_submit(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _machine_service(client).submit_flag(args.target, args.flag, args.difficulty)


def challenge_list(args: argparse.Namespace, client: HtbApiClient) -> Any:
    filters = ChallengeFilters(
        state=args.state,
        difficulty=args.difficulty,
        category=args.category,
        owned=args.owned,
        search=args.search,
    )
    result = _challenge_service(client).list(
        filters,
        limit=None if args.all else args.limit,
        use_cache=not args.no_cache,
    )
    if args.json:
        return result

    print_table(
        result["challenges"],
        ["id", "name", "category", "difficulty", "state", "solves", "owned"],
        color=args.color,
        wide=args.wide,
    )
    _report_list_meta("challenges", result)
    return None


def challenge_info(args: argparse.Namespace, client: HtbApiClient) -> Any:
    # One request either way: --json returns the raw payload, the table view is
    # the same payload reshaped.
    payload = _challenge_service(client).info_raw(args.id)
    if args.json:
        return payload
    return challenge_summary(payload["challenge"])


def challenge_download(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _challenge_service(client).download(
        args.id,
        out=args.out,
        extract=args.extract,
        password=args.password,
    )


def challenge_start(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _challenge_service(client).start(
        args.id,
        force=args.force,
        wait=args.wait,
        interval=args.interval,
        probe=getattr(args, "probe", 0),
    )


def challenge_restart(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _challenge_service(client).restart(
        args.id,
        wait=args.wait,
        interval=args.interval,
        probe=getattr(args, "probe", 0),
    )


def challenge_stop(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _challenge_service(client).stop(args.id)


def challenge_status(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _challenge_service(client).status(args.id)
    if args.json:
        return result
    print_table(
        result["containers"],
        ["id", "name", "status", "ip", "ports_text", "expires"],
        color=args.color,
        wide=args.wide,
    )
    return None


def challenge_own(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _challenge_service(client).own(args.id, args.flag)


def sherlock_list(args: argparse.Namespace, client: HtbApiClient) -> Any:
    filters = SherlockFilters(
        state="active" if args.active else None,
        difficulty=args.difficulty,
        owned=args.owned,
        search=args.search,
    )
    result = _sherlock_service(client).list(
        filters,
        limit=None if args.all else args.limit,
        use_cache=not args.no_cache,
    )
    if args.json:
        return result

    print_table(
        result["sherlocks"],
        ["id", "name", "difficulty", "state", "solves", "owned", "progress"],
        color=args.color,
        wide=args.wide,
    )
    _report_list_meta("sherlocks", result)
    return None


def sherlock_tasks(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _sherlock_service(client).tasks(args.id, include_hints=args.hints)
    if args.json:
        return result
    for task in result["tasks"]:
        print(f"{task['id']}  {task.get('title') or ''}".rstrip())
        if task.get("question"):
            print(f"    {task['question']}")
        details = []
        if task.get("answer_format"):
            details.append(f"format: {task['answer_format']}")
        if task.get("completed"):
            details.append("solved")
        if task.get("prerequisite_id"):
            details.append(f"needs task {task['prerequisite_id']} first")
        if task.get("hint"):
            details.append(f"hint: {task['hint']}")
        if details:
            print(f"    {' | '.join(details)}")
    return None


def sherlock_answer(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _sherlock_service(client).answer(args.id, args.task_id, args.answer)


def sherlock_info(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _sherlock_service(client).info(args.id)


def sherlock_download(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _sherlock_service(client).download(
        args.id,
        out=args.out,
        extract=args.extract,
        password=args.password,
    )


def sherlock_progress(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _sherlock_service(client).progress(args.id)


def _report_list_meta(label: str, result: dict[str, Any]) -> None:
    """Explain shortened listings on stderr so stdout stays table-only."""
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    count = result.get("count")
    if meta.get("truncated"):
        print(
            f"note: showing {count} {label} (--limit {meta.get('limit')});"
            " raise --limit or pass --all for every match.",
            file=sys.stderr,
        )
    if meta.get("page_cap_reached"):
        print(
            f"warning: stopped after {meta.get('pages_scanned')} pages;"
            " results may be incomplete. Narrow the filters.",
            file=sys.stderr,
        )
    cached = meta.get("cached_pages") or 0
    if cached and cached == meta.get("pages_scanned"):
        print(
            "note: served from the page cache (5 minute TTL); pass --no-cache to refetch.",
            file=sys.stderr,
        )


def vpn_servers(args: argparse.Namespace, client: HtbApiClient) -> Any:
    if not args.static:
        try:
            payload = _vpn_service(client).list_servers(args.product)
            rows = server_rows(payload)
        except ApiError as exc:
            print(
                f"warning: could not fetch live servers ({exc});"
                " showing built-in aliases. Use --static to silence this.",
                file=sys.stderr,
            )
            rows = []
        else:
            if args.json:
                return payload
            print_table(
                rows,
                ["id", "name", "group", "location", "clients", "full", "assigned"],
                color=args.color,
                wide=args.wide,
            )
            return None

    rows = vpn_rows()
    if args.json:
        return rows
    print_table(rows, ["alias", "id", "name", "scope", "location"], color=args.color, wide=args.wide)
    return None


def vpn_switch(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _vpn_service(client).switch(args.server)


def vpn_download(args: argparse.Namespace, client: HtbApiClient) -> Any:
    path = _vpn_service(client).download_ovpn(args.server, args.variant, args.output)
    return {"output": str(path)}


def vpn_connect(args: argparse.Namespace, client: HtbApiClient) -> Any:
    command = shlex.split(args.openvpn_command)
    code = _vpn_service(client).connect(args.server, args.variant, args.output, command)
    if code != 0:
        raise RuntimeError(f"OpenVPN exited with code {code}.")
    return {"exit_code": code}


def user_info(args: argparse.Namespace, client: HtbApiClient) -> Any:
    service = UserService(client)
    if args.json:
        return service.profile()
    return service.summary()


def completion(args: argparse.Namespace, client: HtbApiClient | None) -> Any:
    print(completion_script(args.shell))
    return None


def speedrun(args: argparse.Namespace, client: HtbApiClient) -> Any:
    ui = StepRunner(color=args.color)
    ui.header(f"speedrun: {args.target} via {args.server}")
    service = SpeedrunService(VpnService(client), MachineService(client), ui)
    result = service.launch(
        args.target,
        args.server,
        output=args.output,
        variant=args.variant,
        interface=args.interface,
        mtu=args.mtu,
        mode=args.mode,
        retry_for=args.retry_for,
        interval=args.interval,
        openvpn_command=shlex.split(args.openvpn_command),
        log_path=args.output.with_suffix(".log"),
    )

    info = result.machine
    name = info.get("name") or args.target
    ip = info.get("ip")
    enabled = color_enabled(args.color)
    lines = box.panel(
        [
            f"machine   {name}",
            f"ip        {ip}",
            f"tunnel    {result.interface} (mtu {result.mtu})",
        ],
        title="ready",
        enabled=enabled,
    )
    for line in lines:
        print(line)
    ui.note("VPN is foreground; press Ctrl-C to disconnect.")

    try:
        code = result.process.wait()
        if code != 0:
            raise RuntimeError(f"OpenVPN exited with code {code}. Check {args.output.with_suffix('.log')}.")
    except KeyboardInterrupt:
        ui.note("disconnecting VPN...")
        raise
    finally:
        stop_openvpn(result.process)
    return None


def raw(args: argparse.Namespace, client: HtbApiClient) -> Any:
    data = json.loads(args.data) if args.data else None
    response = client.request(args.method, args.path, data=data)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(response.body)
        return {"status": response.status, "output": str(args.output)}
    if response.content_type.startswith("application/json"):
        return response.json()
    return response.body.decode("utf-8", errors="replace")


def print_result(value: Any, args: argparse.Namespace) -> None:
    if isinstance(value, (dict, list)):
        if args.json:
            print_json(value)
        else:
            print_pretty(value, color=args.color)
    else:
        print(value)


def prolab_list(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _lab_service(client).labs()
    if args.json:
        return result
    print_table(
        result["labs"],
        ["id", "name", "machines", "flags", "flags_owned", "state", "release_at"],
        color=args.color,
        wide=args.wide,
    )
    return None


def prolab_machines(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _lab_service(client).lab_machines(args.id)
    if args.json:
        return result
    print_table(
        result["machines"],
        ["id", "name", "os"],
        color=args.color,
        wide=args.wide,
    )
    return None


def fortress_list(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _lab_service(client).fortresses()
    if args.json:
        return result
    print_table(
        result["fortresses"],
        ["id", "name", "flags", "owned", "progress", "new"],
        color=args.color,
        wide=args.wide,
    )
    return None


def fortress_info(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _lab_service(client).fortress(args.id)
    if args.json:
        return result
    summary = {
        key: value
        for key, value in result.items()
        if key not in {"flags", "description", "company"}
    }
    company = result.get("company")
    if isinstance(company, dict):
        summary["company"] = company.get("name")
    print_pretty(summary, color=args.color)
    print()
    print_table(
        result["flags"],
        ["id", "title", "points", "owned"],
        color=args.color,
        wide=args.wide,
    )
    print(
        f"\npoints: {result['points_earned']}/{result['points_total']}"
        f"  flags: {result['flags_owned']}/{result['flags_total']}"
    )
    return None


def prolab_info(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _lab_service(client).lab_info(args.id)
    if args.json:
        return result
    print_pretty(result, color=args.color)
    return None


def prolab_flags(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _lab_service(client).lab_flags(args.id)
    if args.json:
        return result
    print_table(
        result["flags"],
        ["id", "title", "points", "owned"],
        color=args.color,
        wide=args.wide,
    )
    print(
        f"\npoints: {result['points_earned']}/{result['points_total']}"
        f"  flags: {result['owned']}/{result['total']}"
    )
    return None


def progress_show(args: argparse.Namespace, client: HtbApiClient) -> Any:
    service = _progress_service(client)
    kind = args.kind
    if kind is None:
        result = service.summary()
        if args.json:
            return result
        machines = result["machines"]
        challenges = result["challenges"]
        print(f"user {result['user_id']}")
        print(f"  machines    {machines['solved']}/{machines['total']}")
        print(f"  challenges  {challenges['solved']}/{challenges['total']}")
        if result["fortresses"]:
            print("  fortresses")
            print_table(
                result["fortresses"],
                ["id", "name", "flags", "total", "percent"],
                color=args.color,
                wide=args.wide,
            )
        if result["prolabs"]:
            print("  pro labs")
            print_table(
                result["prolabs"],
                ["id", "name", "flags", "total", "machines", "percent"],
                color=args.color,
                wide=args.wide,
            )
        return None
    result = service.kind(kind)
    if args.json:
        return result
    if kind in ("machines", "challenges"):
        print(
            f"{kind}: {result['solved']}/{result['total']}  bloods: {result.get('bloods')}"
        )
        return None
    rows = result.get("fortresses") or result.get("prolabs") or []
    columns = ["id", "name", "flags", "total", "percent"]
    if kind == "prolab":
        columns.insert(4, "machines")
    print_table(rows, columns, color=args.color, wide=args.wide)
    return None


def progress_submissions(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _progress_service(client).submissions(args.kind)
    if args.json:
        return result
    print_table(result["submissions"], ["id", "name", "type"], color=args.color, wide=args.wide)
    return None


def progress_connection(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _progress_service(client).connection()
    if args.json:
        return result
    print(f"connected: {'yes' if result['connected'] else 'no'}  ({result.get('state')})")
    return None


def fortress_own(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _lab_service(client).own_fortress_flag(args.id, args.flag)


def prolab_own(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _lab_service(client).own_lab_flag(args.id, args.flag)


def machine_activity(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _machine_service(client).activity(args.target)
    if args.json:
        return result
    rows = result
    print_table(
        rows,
        ["date", "user", "type", "blood"],
        color=args.color,
        wide=args.wide,
    )
    return None


def machine_walkthroughs(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _machine_service(client).walkthroughs(args.target)
    if args.json:
        return result
    print_table(result, ["id", "title", "language", "url"], color=args.color, wide=args.wide)
    return None


def challenge_activity(args: argparse.Namespace, client: HtbApiClient) -> Any:
    result = _challenge_service(client).activity(args.id)
    if args.json:
        return result
    print_table(
        result,
        ["date", "user", "type", "blood"],
        color=args.color,
        wide=args.wide,
    )
    return None
