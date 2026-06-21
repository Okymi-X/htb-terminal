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
import shlex
import subprocess
import sys
from typing import Any

from htb_terminal import box
from htb_terminal.completion import completion_script
from htb_terminal.config import load_config, save_token
from htb_terminal.http import ApiError, HtbApiClient
from htb_terminal.output import (
    color_enabled,
    print_json,
    print_pretty,
    print_status_line,
    print_table,
)
from htb_terminal.services.machines import MachineService
from htb_terminal.services.payloads import machine_rows
from htb_terminal.services.speedrun import SpeedrunService
from htb_terminal.services.user import UserService
from htb_terminal.services.vpn import VpnService, server_rows, vpn_rows
from htb_terminal.ui import StepRunner


def _machine_service(client: HtbApiClient) -> MachineService:
    return MachineService(client)


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

    if args.json:
        return payload
    print_table(
        machine_rows(payload),
        ["id", "name", "os", "difficulty", "points", "active", "spawned", "free"],
        color=args.color,
        wide=args.wide,
    )
    return None


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
        machine_id, timeout=args.retry_for, interval=args.interval
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
        if rows:
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
        result.process.wait()
    except KeyboardInterrupt:
        ui.note("disconnecting VPN...")
        result.process.terminate()
        try:
            result.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            result.process.kill()
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
