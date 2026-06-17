from __future__ import annotations

import argparse
import getpass
import json
import shlex
import sys
from pathlib import Path
from typing import Any

from htb_terminal import __version__
from htb_terminal.config import ConfigError, load_config, save_token
from htb_terminal.http import ApiError, HtbApiClient
from htb_terminal.output import print_json, print_pretty, print_table
from htb_terminal.services.machines import MachineService
from htb_terminal.services.payloads import machine_rows
from htb_terminal.services.vpn import VpnService, vpn_rows


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 2

    try:
        client = None
        if getattr(args, "needs_auth", True):
            config = load_config(token_file=args.token_file, base_url=args.base_url)
            client = HtbApiClient(config.base_url, config.token, timeout=args.timeout)
        result = args.handler(args, client)
        if result is not None:
            _print_result(result, args)
        return 0
    except (ApiError, ConfigError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="htb",
        description="Terminal client for selected Hack The Box Labs API workflows.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--token-file", type=Path, default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--json", action="store_true", help="Print raw JSON responses.")
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Colorize human output. Defaults to auto.",
    )
    parser.add_argument("--wide", action="store_true", help="Do not truncate table columns.")

    subparsers = parser.add_subparsers(dest="command")
    _add_init_command(subparsers)
    _add_machine_commands(subparsers)
    _add_vpn_commands(subparsers)
    _add_raw_command(subparsers)
    return parser


def _add_init_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    init = subparsers.add_parser(
        "init",
        help="Save your HTB App Token so future commands find it automatically.",
    )
    init.add_argument(
        "--token",
        default=None,
        help="Token value. If omitted, you are prompted (input hidden) or it is read from stdin.",
    )
    init.set_defaults(handler=_init, needs_auth=False)


def _add_machine_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    machine = subparsers.add_parser("machine", help="Manage machines.")
    machine_sub = machine.add_subparsers(dest="machine_command")

    profile = machine_sub.add_parser("profile", help="Show a machine profile by id or name.")
    profile.add_argument("target")
    profile.set_defaults(handler=_machine_profile)

    active = machine_sub.add_parser("active", help="Show the active machine.")
    active.add_argument("--details", action="store_true", help="Include synopsis and Academy module names.")
    active.set_defaults(handler=_machine_active)

    list_cmd = machine_sub.add_parser("list", help="List machines.")
    list_cmd.add_argument("--page", type=int, default=None)
    list_cmd.add_argument("--retired", action="store_true")
    list_cmd.add_argument("--todo", action="store_true")
    list_cmd.add_argument("--unreleased", action="store_true")
    list_cmd.add_argument("--sp-tier", type=int, choices=[1, 2, 3], default=None)
    list_cmd.set_defaults(handler=_machine_list)

    search = machine_sub.add_parser(
        "search",
        help="Search machines by id, name, OS, difficulty, tag, maker, or profile text.",
    )
    search.add_argument("query")
    search.add_argument("--retired", action="store_true", help="Search retired machines only.")
    search.add_argument("--all", action="store_true", help="Search playable and retired machines.")
    search.add_argument(
        "--profiles",
        action="store_true",
        help="Also fetch machine profiles and search description/profile-only fields.",
    )
    search.add_argument("--limit", type=int, default=20, help="Maximum matching rows to print.")
    search.add_argument("--max-pages", type=int, default=10, help="Maximum API pages to scan per list.")
    search.set_defaults(handler=_machine_search)

    start = machine_sub.add_parser("start", help="Start a machine by id or name.")
    start.add_argument("target")
    start.add_argument("--mode", choices=["auto", "play", "spawn"], default="auto")
    start.add_argument(
        "--wait",
        action="store_true",
        help="Retry while spawn capacity is full, then wait for the machine IP."
        " Useful at peak times such as seasonal releases (Saturdays 19:00 UTC).",
    )
    start.add_argument(
        "--retry-for",
        type=int,
        default=600,
        metavar="SECONDS",
        help="With --wait: keep retrying the spawn for up to this long. Default 600.",
    )
    start.add_argument(
        "--interval",
        type=int,
        default=15,
        metavar="SECONDS",
        help="With --wait: base delay between attempts (jittered). Default 15.",
    )
    start.set_defaults(handler=_machine_start)

    stop = machine_sub.add_parser("stop", help="Stop a machine. Defaults to active machine.")
    stop.add_argument("target", nargs="?")
    stop.set_defaults(handler=_machine_stop)

    reset = machine_sub.add_parser("reset", help="Reset a machine. Defaults to active machine.")
    reset.add_argument("target", nargs="?")
    reset.set_defaults(handler=_machine_reset)

    submit = machine_sub.add_parser("submit", help="Submit a user or root flag.")
    submit.add_argument("target")
    submit.add_argument("flag")
    submit.add_argument("--difficulty", type=int, required=True)
    submit.set_defaults(handler=_machine_submit)


def _add_vpn_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    vpn = subparsers.add_parser("vpn", help="Manage VPN server selection and OVPN files.")
    vpn_sub = vpn.add_subparsers(dest="vpn_command")

    servers = vpn_sub.add_parser("servers", help="Show known VPN server aliases.")
    servers.set_defaults(handler=_vpn_servers)

    switch = vpn_sub.add_parser("switch", help="Switch to a VPN server by id or alias.")
    switch.add_argument("server")
    switch.set_defaults(handler=_vpn_switch)

    download = vpn_sub.add_parser("download", help="Download an OVPN file.")
    download.add_argument("server")
    download.add_argument("-o", "--output", type=Path, default=Path("lab-vpn.ovpn"))
    download.add_argument("--variant", type=int, default=0)
    download.set_defaults(handler=_vpn_download)

    connect = vpn_sub.add_parser("connect", help="Switch, download, then run OpenVPN.")
    connect.add_argument("server")
    connect.add_argument("-o", "--output", type=Path, default=Path("lab-vpn.ovpn"))
    connect.add_argument("--variant", type=int, default=0)
    connect.add_argument(
        "--openvpn-command",
        default="sudo openvpn",
        help="Command used before '--config <file>'.",
    )
    connect.set_defaults(handler=_vpn_connect)


def _add_raw_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    raw = subparsers.add_parser("raw", help="Call an API endpoint directly.")
    raw.add_argument("method", choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    raw.add_argument("path", help="Path such as /machine/active.")
    raw.add_argument("--data", default=None, help="JSON body for write requests.")
    raw.add_argument("-o", "--output", type=Path, default=None)
    raw.set_defaults(handler=_raw)


def _init(args: argparse.Namespace, client: HtbApiClient | None) -> Any:
    token = args.token or _prompt_token()
    path = save_token(token, args.token_file)
    return {"saved": str(path)}


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


def _machine_service(client: HtbApiClient) -> MachineService:
    return MachineService(client)


def _vpn_service(client: HtbApiClient) -> VpnService:
    return VpnService(client)


def _machine_profile(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _machine_service(client).profile(args.target)


def _machine_active(args: argparse.Namespace, client: HtbApiClient) -> Any:
    service = _machine_service(client)
    if args.json:
        return service.active_with_profile()
    return service.active_summary(include_details=args.details)


def _machine_list(args: argparse.Namespace, client: HtbApiClient) -> Any:
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


def _machine_search(args: argparse.Namespace, client: HtbApiClient) -> Any:
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


def _machine_start(args: argparse.Namespace, client: HtbApiClient) -> Any:
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
    info = service.wait_for_active_ip(machine_id)
    return {
        "id": machine_id,
        "name": info.get("name"),
        "ip": info.get("ip"),
        "spawn": result,
    }


def _machine_stop(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _machine_service(client).stop(args.target)


def _machine_reset(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _machine_service(client).reset(args.target)


def _machine_submit(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _machine_service(client).submit_flag(args.target, args.flag, args.difficulty)


def _vpn_servers(args: argparse.Namespace, client: HtbApiClient) -> Any:
    rows = vpn_rows()
    if args.json:
        return rows
    print_table(rows, ["alias", "id", "name", "scope", "location"], color=args.color, wide=args.wide)
    return None


def _vpn_switch(args: argparse.Namespace, client: HtbApiClient) -> Any:
    return _vpn_service(client).switch(args.server)


def _vpn_download(args: argparse.Namespace, client: HtbApiClient) -> Any:
    path = _vpn_service(client).download_ovpn(args.server, args.variant, args.output)
    return {"output": str(path)}


def _vpn_connect(args: argparse.Namespace, client: HtbApiClient) -> Any:
    command = shlex.split(args.openvpn_command)
    code = _vpn_service(client).connect(args.server, args.variant, args.output, command)
    return {"exit_code": code}


def _raw(args: argparse.Namespace, client: HtbApiClient) -> Any:
    data = json.loads(args.data) if args.data else None
    response = client.request(args.method, args.path, data=data)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(response.body)
        return {"status": response.status, "output": str(args.output)}
    if response.content_type.startswith("application/json"):
        return response.json()
    return response.body.decode("utf-8", errors="replace")


def _print_result(value: Any, args: argparse.Namespace) -> None:
    if isinstance(value, (dict, list)):
        if args.json:
            print_json(value)
        else:
            print_pretty(value, color=args.color)
    else:
        print(value)


if __name__ == "__main__":
    raise SystemExit(main())
