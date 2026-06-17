"""Argument parser construction.

Builds the full ``htb`` argument parser and binds each subcommand to a handler
in :mod:`htb_terminal.handlers`. This module is declarative only; it contains no
request or rendering logic.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from htb_terminal import __version__, handlers

_SubParsers = argparse._SubParsersAction


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
    _add_user_commands(subparsers)
    _add_speedrun_command(subparsers)
    _add_raw_command(subparsers)
    _add_completion_command(subparsers)
    return parser


def _add_init_command(subparsers: _SubParsers) -> None:
    init = subparsers.add_parser(
        "init",
        help="Save your HTB App Token so future commands find it automatically.",
    )
    init.add_argument(
        "--token",
        default=None,
        help="Token value. If omitted, you are prompted (input hidden) or it is read from stdin.",
    )
    init.add_argument(
        "--check",
        action="store_true",
        help="After saving, verify the token against the API and print who you are.",
    )
    init.set_defaults(handler=handlers.init, needs_auth=False)


def _add_machine_commands(subparsers: _SubParsers) -> None:
    machine = subparsers.add_parser("machine", help="Manage machines.")
    machine_sub = machine.add_subparsers(dest="machine_command")

    profile = machine_sub.add_parser("profile", help="Show a machine profile by id or name.")
    profile.add_argument("target")
    profile.set_defaults(handler=handlers.machine_profile)

    info = machine_sub.add_parser("info", help="Alias for 'machine profile'.")
    info.add_argument("target")
    info.set_defaults(handler=handlers.machine_profile)

    active = machine_sub.add_parser("active", help="Show the active machine.")
    active.add_argument("--details", action="store_true", help="Include synopsis and Academy module names.")
    active.add_argument(
        "--oneline",
        action="store_true",
        help="Print a single compact status line instead of the full summary.",
    )
    active.set_defaults(handler=handlers.machine_active)

    list_cmd = machine_sub.add_parser("list", help="List machines.")
    list_cmd.add_argument("--page", type=int, default=None)
    list_cmd.add_argument("--retired", action="store_true")
    list_cmd.add_argument("--todo", action="store_true")
    list_cmd.add_argument("--unreleased", action="store_true")
    list_cmd.add_argument("--sp-tier", type=int, choices=[1, 2, 3], default=None)
    list_cmd.set_defaults(handler=handlers.machine_list)

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
    search.set_defaults(handler=handlers.machine_search)

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
    start.set_defaults(handler=handlers.machine_start)

    stop = machine_sub.add_parser("stop", help="Stop a machine. Defaults to active machine.")
    stop.add_argument("target", nargs="?")
    stop.set_defaults(handler=handlers.machine_stop)

    reset = machine_sub.add_parser("reset", help="Reset a machine. Defaults to active machine.")
    reset.add_argument("target", nargs="?")
    reset.set_defaults(handler=handlers.machine_reset)

    extend = machine_sub.add_parser("extend", help="Extend a machine's expiry. Defaults to active machine.")
    extend.add_argument("target", nargs="?")
    extend.set_defaults(handler=handlers.machine_extend)

    submit = machine_sub.add_parser("submit", help="Submit a user or root flag.")
    submit.add_argument("target")
    submit.add_argument("flag")
    submit.add_argument("--difficulty", type=int, required=True)
    submit.set_defaults(handler=handlers.machine_submit)


def _add_vpn_commands(subparsers: _SubParsers) -> None:
    vpn = subparsers.add_parser("vpn", help="Manage VPN server selection and OVPN files.")
    vpn_sub = vpn.add_subparsers(dest="vpn_command")

    servers = vpn_sub.add_parser("servers", help="Show known VPN server aliases.")
    servers.set_defaults(handler=handlers.vpn_servers)

    switch = vpn_sub.add_parser("switch", help="Switch to a VPN server by id or alias.")
    switch.add_argument("server")
    switch.set_defaults(handler=handlers.vpn_switch)

    download = vpn_sub.add_parser("download", help="Download an OVPN file.")
    download.add_argument("server")
    download.add_argument("-o", "--output", type=Path, default=Path("lab-vpn.ovpn"))
    download.add_argument("--variant", type=int, default=0)
    download.set_defaults(handler=handlers.vpn_download)

    connect = vpn_sub.add_parser("connect", help="Switch, download, then run OpenVPN.")
    connect.add_argument("server")
    connect.add_argument("-o", "--output", type=Path, default=Path("lab-vpn.ovpn"))
    connect.add_argument("--variant", type=int, default=0)
    connect.add_argument(
        "--openvpn-command",
        default="sudo openvpn",
        help="Command used before '--config <file>'.",
    )
    connect.set_defaults(handler=handlers.vpn_connect)


def _add_user_commands(subparsers: _SubParsers) -> None:
    user = subparsers.add_parser("user", help="Show your HTB user profile.")
    user_sub = user.add_subparsers(dest="user_command")

    info = user_sub.add_parser("info", help="Show your profile: rank, points, and owns.")
    info.set_defaults(handler=handlers.user_info)


def _add_speedrun_command(subparsers: _SubParsers) -> None:
    speedrun = subparsers.add_parser(
        "speedrun",
        help="Connect the VPN, set the MTU, and spawn a machine in one shot (needs sudo).",
        description="One-shot season-release flow: switch + connect the VPN, lower the tunnel"
        " MTU, then spawn the machine with capacity retries and wait for its IP. The VPN"
        " stays in the foreground; press Ctrl-C to disconnect.",
    )
    speedrun.add_argument("target", help="Machine id or name.")
    speedrun.add_argument("server", help="VPN server id or alias (see 'htb vpn servers').")
    speedrun.add_argument("-o", "--output", type=Path, default=Path("lab-vpn.ovpn"))
    speedrun.add_argument("--variant", type=int, default=0)
    speedrun.add_argument("--interface", default="tun0", help="Tunnel interface to tune. Default tun0.")
    speedrun.add_argument("--mtu", type=int, default=1300, help="MTU to set on the interface. Default 1300.")
    speedrun.add_argument("--mode", choices=["auto", "play", "spawn"], default="auto")
    speedrun.add_argument(
        "--retry-for",
        type=int,
        default=900,
        metavar="SECONDS",
        help="Keep retrying the spawn for up to this long. Default 900.",
    )
    speedrun.add_argument(
        "--interval",
        type=int,
        default=15,
        metavar="SECONDS",
        help="Base delay between spawn attempts (jittered). Default 15.",
    )
    speedrun.add_argument(
        "--openvpn-command",
        default="openvpn",
        help="OpenVPN command; '--config <file>' is appended. Default 'openvpn' (already root).",
    )
    speedrun.set_defaults(handler=handlers.speedrun)


def _add_completion_command(subparsers: _SubParsers) -> None:
    completion = subparsers.add_parser(
        "completion",
        help="Print a shell completion script. Eval or source the output.",
    )
    completion.add_argument("shell", choices=["bash", "zsh"])
    completion.set_defaults(handler=handlers.completion, needs_auth=False)


def _add_raw_command(subparsers: _SubParsers) -> None:
    raw = subparsers.add_parser("raw", help="Call an API endpoint directly.")
    raw.add_argument("method", choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    raw.add_argument("path", help="Path such as /machine/active.")
    raw.add_argument("--data", default=None, help="JSON body for write requests.")
    raw.add_argument("-o", "--output", type=Path, default=None)
    raw.set_defaults(handler=handlers.raw)
