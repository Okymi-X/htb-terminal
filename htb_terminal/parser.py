"""Argument parser construction.

Builds the full ``htb`` argument parser and binds each subcommand to a handler
in :mod:`htb_terminal.handlers`. This module is declarative only; it contains no
request or rendering logic.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from htb_terminal import __version__, handlers
from htb_terminal.helpfmt import HtbHelpFormatter, banner
from htb_terminal.services.vpn import VPN_PRODUCTS

_SubParsers = argparse._SubParsersAction


def _add_global_arguments(parser: argparse.ArgumentParser, *, inherited: bool) -> None:
    """Add the flags accepted at every level.

    The root parser keeps real defaults so the attributes always exist. The
    inherited copy (mixed into every subcommand via ``parents=``) uses
    ``SUPPRESS`` for both default and help: ``SUPPRESS`` defaults mean a flag
    placed before the subcommand is not clobbered by the subparser, and
    ``SUPPRESS`` help keeps per-command ``--help`` output uncluttered.
    """
    sup = argparse.SUPPRESS

    def add(*flags: str, default: object, help: str, **kwargs: object) -> None:
        parser.add_argument(
            *flags,
            default=sup if inherited else default,
            help=sup if inherited else help,
            **kwargs,  # type: ignore[arg-type]
        )

    add("--token-file", type=Path, default=None, help="Read the API token from this file.")
    add("--base-url", default=None, help="Override the API base URL.")
    add("--timeout", type=int, default=30, help="Per-request timeout in seconds. Default 30.")
    add("--json", action="store_true", default=False, help="Print raw JSON responses.")
    add(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Colorize human output. Defaults to auto.",
    )
    add("--wide", action="store_true", default=False, help="Do not truncate table columns.")


def _leaf(
    subparsers: _SubParsers,
    name: str,
    common: argparse.ArgumentParser,
    **kwargs: Any,
) -> argparse.ArgumentParser:
    """Add a runnable subcommand that also accepts the global flags."""
    return subparsers.add_parser(name, parents=[common], **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="htb",
        formatter_class=HtbHelpFormatter,
        description=banner("Terminal client for selected Hack The Box Labs API workflows."),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_global_arguments(parser, inherited=False)

    # Mixed into every subcommand so global flags also work *after* the command,
    # e.g. both "htb --json machine list" and "htb machine list --json".
    common = argparse.ArgumentParser(add_help=False)
    _add_global_arguments(common, inherited=True)

    subparsers = parser.add_subparsers(dest="command")
    _add_init_command(subparsers, common)
    _add_machine_commands(subparsers, common)
    _add_vpn_commands(subparsers, common)
    _add_user_commands(subparsers, common)
    _add_speedrun_command(subparsers, common)
    _add_raw_command(subparsers, common)
    _add_completion_command(subparsers, common)
    return parser


def _add_init_command(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    init = _leaf(
        subparsers,
        "init",
        common,
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


def _add_machine_commands(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    machine = subparsers.add_parser("machine", help="Manage machines.")
    machine_sub = machine.add_subparsers(dest="machine_command")

    profile = _leaf(machine_sub, "profile", common, help="Show a machine profile by id or name.")
    profile.add_argument("target")
    profile.set_defaults(handler=handlers.machine_profile)

    info = _leaf(machine_sub, "info", common, help="Alias for 'machine profile'.")
    info.add_argument("target")
    info.set_defaults(handler=handlers.machine_profile)

    active = _leaf(machine_sub, "active", common, help="Show the active machine.")
    active.add_argument("--details", action="store_true", help="Include synopsis and Academy module names.")
    active.add_argument(
        "--oneline",
        action="store_true",
        help="Print a single compact status line instead of the full summary.",
    )
    active.set_defaults(handler=handlers.machine_active)

    list_cmd = _leaf(machine_sub, "list", common, help="List machines.")
    list_cmd.add_argument("--page", type=int, default=None)
    list_cmd.add_argument("--retired", action="store_true")
    list_cmd.add_argument("--todo", action="store_true")
    list_cmd.add_argument("--unreleased", action="store_true")
    list_cmd.add_argument("--sp-tier", type=int, choices=[1, 2, 3], default=None)
    list_cmd.set_defaults(handler=handlers.machine_list)

    search = _leaf(
        machine_sub,
        "search",
        common,
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

    start = _leaf(machine_sub, "start", common, help="Start a machine by id or name.")
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
        help="With --wait: budget (seconds) for the whole flow — retrying the"
        " spawn while capacity is full and then waiting for the machine IP."
        " Default 600.",
    )
    start.add_argument(
        "--interval",
        type=int,
        default=15,
        metavar="SECONDS",
        help="With --wait: base delay between spawn attempts (jittered) and between"
        " IP-availability polls. Default 15.",
    )
    start.set_defaults(handler=handlers.machine_start)

    stop = _leaf(machine_sub, "stop", common, help="Stop a machine. Defaults to active machine.")
    stop.add_argument("target", nargs="?")
    stop.set_defaults(handler=handlers.machine_stop)

    reset = _leaf(machine_sub, "reset", common, help="Reset a machine. Defaults to active machine.")
    reset.add_argument("target", nargs="?")
    reset.set_defaults(handler=handlers.machine_reset)

    extend = _leaf(
        machine_sub, "extend", common, help="Extend a machine's expiry. Defaults to active machine."
    )
    extend.add_argument("target", nargs="?")
    extend.set_defaults(handler=handlers.machine_extend)

    submit = _leaf(machine_sub, "submit", common, help="Submit a user or root flag.")
    submit.add_argument("target")
    submit.add_argument("flag")
    submit.add_argument("--difficulty", type=int, required=True)
    submit.set_defaults(handler=handlers.machine_submit)


def _add_vpn_commands(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    vpn = subparsers.add_parser("vpn", help="Manage VPN server selection and OVPN files.")
    vpn_sub = vpn.add_subparsers(dest="vpn_command")

    servers = _leaf(
        vpn_sub,
        "servers",
        common,
        help="List VPN servers your account can use (live), including VIP/VIP+.",
    )
    servers.add_argument(
        "product",
        nargs="?",
        default="labs",
        choices=list(VPN_PRODUCTS),
        help="Which server pool to list. Default labs (regular machines).",
    )
    servers.add_argument(
        "--static",
        action="store_true",
        help="Skip the API and show only the built-in offline aliases.",
    )
    servers.set_defaults(handler=handlers.vpn_servers)

    switch = _leaf(vpn_sub, "switch", common, help="Switch to a VPN server by id, alias, or name.")
    switch.add_argument("server")
    switch.set_defaults(handler=handlers.vpn_switch)

    download = _leaf(vpn_sub, "download", common, help="Download an OVPN file.")
    download.add_argument("server")
    download.add_argument("-o", "--output", type=Path, default=Path("lab-vpn.ovpn"))
    download.add_argument("--variant", type=int, default=0)
    download.set_defaults(handler=handlers.vpn_download)

    connect = _leaf(vpn_sub, "connect", common, help="Switch, download, then run OpenVPN.")
    connect.add_argument("server")
    connect.add_argument("-o", "--output", type=Path, default=Path("lab-vpn.ovpn"))
    connect.add_argument("--variant", type=int, default=0)
    connect.add_argument(
        "--openvpn-command",
        default="sudo openvpn",
        help="Command used before '--config <file>'.",
    )
    connect.set_defaults(handler=handlers.vpn_connect)


def _add_user_commands(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    user = subparsers.add_parser("user", help="Show your HTB user profile.")
    user_sub = user.add_subparsers(dest="user_command")

    info = _leaf(user_sub, "info", common, help="Show your profile: rank, points, and owns.")
    info.set_defaults(handler=handlers.user_info)


def _add_speedrun_command(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    speedrun = _leaf(
        subparsers,
        "speedrun",
        common,
        help="Connect the VPN, set the MTU, and spawn a machine in one shot (needs sudo).",
        description="One-shot season-release flow: switch + connect the VPN, lower the tunnel"
        " MTU, then spawn the machine with capacity retries and wait for its IP. The VPN"
        " stays in the foreground; press Ctrl-C to disconnect.",
    )
    speedrun.add_argument("target", help="Machine id or name.")
    speedrun.add_argument("server", help="VPN server id, alias, or name (see 'htb vpn servers').")
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


def _add_completion_command(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    completion = _leaf(
        subparsers,
        "completion",
        common,
        help="Print a shell completion script. Eval or source the output.",
    )
    completion.add_argument("shell", choices=["bash", "zsh"])
    completion.set_defaults(handler=handlers.completion, needs_auth=False)


def _add_raw_command(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    raw = _leaf(subparsers, "raw", common, help="Call an API endpoint directly.")
    raw.add_argument("method", choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    raw.add_argument("path", help="Path such as /machine/active.")
    raw.add_argument("--data", default=None, help="JSON body for write requests.")
    raw.add_argument("-o", "--output", type=Path, default=None)
    raw.set_defaults(handler=handlers.raw)
