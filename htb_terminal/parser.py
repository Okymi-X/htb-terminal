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
from htb_terminal.services.challenges import (
    ARCHIVE_WORD,
    DIFFICULTIES,
    STATES,
)
from htb_terminal.services.payloads import difficulty_slug
from htb_terminal.services.vpn import VPN_PRODUCTS

_SubParsers = argparse._SubParsersAction


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be at least 0")
    return parsed


def _vpn_servers_needs_auth(args: argparse.Namespace) -> bool:
    return not args.static


def _difficulty(value: str) -> str:
    slug = difficulty_slug(value)
    if slug not in DIFFICULTIES:
        raise argparse.ArgumentTypeError(
            f"unknown difficulty {value!r}; choose one of {', '.join(DIFFICULTIES)}"
        )
    return slug


def _add_owned_filters(parser: argparse.ArgumentParser) -> None:
    """``--owned`` / ``--unowned`` as one tri-state option (None = both)."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--owned",
        dest="owned",
        action="store_const",
        const=True,
        help="Only entries you already own.",
    )
    group.add_argument(
        "--unowned",
        dest="owned",
        action="store_const",
        const=False,
        help="Only entries you have not solved yet.",
    )
    parser.set_defaults(owned=None)


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
    add(
        "--timeout",
        type=_positive_int,
        default=30,
        help="Per-request timeout in seconds. Default 30.",
    )
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
    _add_challenge_commands(subparsers, common)
    _add_sherlock_commands(subparsers, common)
    _add_lab_commands(subparsers, common)
    _add_progress_commands(subparsers, common)
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

    activity = _leaf(
        machine_sub, "activity", common, help="Recent owns and bloods for one machine."
    )
    activity.add_argument("target")
    activity.set_defaults(handler=handlers.machine_activity)

    walkthroughs = _leaf(
        machine_sub, "walkthroughs", common, help="Official walkthroughs (retired boxes only)."
    )
    walkthroughs.add_argument("target")
    walkthroughs.set_defaults(handler=handlers.machine_walkthroughs)

    active = _leaf(machine_sub, "active", common, help="Show the active machine.")
    active.add_argument("--details", action="store_true", help="Include synopsis and Academy module names.")
    active.add_argument(
        "--oneline",
        action="store_true",
        help="Print a single compact status line instead of the full summary.",
    )
    active.set_defaults(handler=handlers.machine_active)

    list_cmd = _leaf(machine_sub, "list", common, help="List machines.")
    list_cmd.add_argument("--page", type=_positive_int, default=None)
    list_cmd.add_argument("--retired", action="store_true")
    list_cmd.add_argument("--todo", action="store_true")
    list_cmd.add_argument("--unreleased", action="store_true")
    list_cmd.add_argument("--sp-tier", type=int, choices=[1, 2, 3], default=None)
    list_cmd.add_argument(
        "--difficulty",
        default=None,
        help="Only rows with this difficulty (local filter: the endpoint has no such param).",
    )
    list_cmd.add_argument(
        "--os",
        dest="os_name",
        default=None,
        help="Only rows with this OS (local filter).",
    )
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
    search.add_argument(
        "--limit",
        type=_positive_int,
        default=20,
        help="Maximum matching rows to print.",
    )
    search.add_argument(
        "--max-pages",
        type=_positive_int,
        default=10,
        help="Maximum API pages to scan per list.",
    )
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
        type=_positive_int,
        default=600,
        metavar="SECONDS",
        help="With --wait: budget (seconds) for the whole flow — retrying the"
        " spawn while capacity is full and then waiting for the machine IP."
        " Default 600.",
    )
    start.add_argument(
        "--interval",
        type=_positive_int,
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
    submit.add_argument(
        "--difficulty",
        type=int,
        choices=range(10, 101, 10),
        required=True,
    )
    submit.set_defaults(handler=handlers.machine_submit)


def _add_challenge_commands(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    challenge = subparsers.add_parser(
        "challenge",
        help="List, inspect, download, run, and flag challenges.",
        description="Challenges are separate from machines: they are listed and"
        " paginated here, their files come as a zip, and a container challenge needs"
        " a started instance before its ports answer.",
    )
    challenge_sub = challenge.add_subparsers(dest="challenge_command")

    list_cmd = _leaf(
        challenge_sub,
        "list",
        common,
        help="List challenges with paging, filters, and a cached fallback.",
    )
    list_cmd.add_argument("--state", choices=list(STATES), default=None)
    list_cmd.add_argument(
        "--difficulty",
        type=_difficulty,
        default=None,
        metavar="{very-easy,easy,medium,hard,insane}",
        help="Filter by difficulty. 'very easy' and 'very_easy' are accepted too.",
    )
    list_cmd.add_argument(
        "--category",
        default=None,
        help="Category name, such as Web, Reversing, Crypto, or Forensics.",
    )
    _add_owned_filters(list_cmd)
    list_cmd.add_argument(
        "--search",
        default=None,
        help="Case-insensitive substring match on the name, or an exact id.",
    )
    list_cmd.add_argument(
        "--limit",
        type=_positive_int,
        default=20,
        help="Maximum rows to print. Default 20.",
    )
    list_cmd.add_argument(
        "--all",
        action="store_true",
        help="Print every match, ignoring --limit.",
    )
    list_cmd.add_argument(
        "--no-cache",
        action="store_true",
        help="Refetch pages instead of serving them from the 5 minute page cache.",
    )
    list_cmd.set_defaults(handler=handlers.challenge_list)

    activity = _leaf(
        challenge_sub, "activity", common, help="Recent owns and bloods for one challenge."
    )
    activity.add_argument("id", type=_positive_int)
    activity.set_defaults(handler=handlers.challenge_activity)

    info = _leaf(challenge_sub, "info", common, help="Show one challenge and its play state.")
    info.add_argument("id", type=_positive_int)
    info.set_defaults(handler=handlers.challenge_info)

    download = _leaf(
        challenge_sub,
        "download",
        common,
        help="Download a challenge file (default challenges/ch<id>/ch<id>.zip).",
    )
    download.add_argument("id", type=_positive_int)
    download.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="Archive path, or a directory to drop ch<id>.zip into."
        " Default challenges/ch<id>/ch<id>.zip.",
    )
    download.add_argument(
        "--extract",
        action="store_true",
        help="Extract the archive after verifying it is a zip (needs the password).",
    )
    download.add_argument(
        "--password",
        default=ARCHIVE_WORD,
        help=f"Archive password for --extract. Default {ARCHIVE_WORD} (HTB publishes it).",
    )
    download.set_defaults(handler=handlers.challenge_download)

    start = _leaf(
        challenge_sub,
        "start",
        common,
        help="Start a container challenge and wait for its ip:port.",
    )
    start.add_argument("id", type=_positive_int)
    start.add_argument(
        "--force",
        action="store_true",
        help="Stop the tracked running container first. HTB silently kills it anyway.",
    )
    start.add_argument(
        "--wait",
        type=_positive_int,
        default=180,
        metavar="SECONDS",
        help="How long to poll for play_info.status == ready. Default 180.",
    )
    start.add_argument(
        "--interval",
        type=_positive_int,
        default=5,
        metavar="SECONDS",
        help="Poll interval while the container boots. Default 5.",
    )
    start.add_argument(
        "--probe",
        type=_positive_int,
        default=0,
        metavar="SECONDS",
        help="After ready, wait until a port really accepts TCP (0 = skip)."
        " play_info says ready before the service is listening.",
    )
    start.set_defaults(handler=handlers.challenge_start)

    restart = _leaf(
        challenge_sub,
        "restart",
        common,
        help="Stop then start a container, giving a fresh ip:port.",
    )
    restart.add_argument("id", type=_positive_int)
    restart.add_argument("--wait", type=_positive_int, default=180, metavar="SECONDS")
    restart.add_argument("--interval", type=_positive_int, default=5, metavar="SECONDS")
    restart.add_argument("--probe", type=_positive_int, default=0, metavar="SECONDS")
    restart.set_defaults(handler=handlers.challenge_restart)

    stop = _leaf(
        challenge_sub,
        "stop",
        common,
        help="Stop a container challenge. Defaults to the tracked running one.",
    )
    stop.add_argument("id", type=_positive_int, nargs="?")
    stop.set_defaults(handler=handlers.challenge_stop)

    status = _leaf(
        challenge_sub,
        "status",
        common,
        help="Show tracked challenge containers and their time to expiry.",
    )
    status.add_argument("id", type=_positive_int, nargs="?")
    status.set_defaults(handler=handlers.challenge_status)

    own = _leaf(challenge_sub, "own", common, help="Submit a challenge flag.")
    own.add_argument("id", type=_positive_int)
    own.add_argument("--flag", required=True, help="The flag value, for example HTB{...}.")
    own.set_defaults(handler=handlers.challenge_own)


def _add_sherlock_commands(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    sherlock = subparsers.add_parser(
        "sherlock",
        help="List Sherlock DFIR challenges and answer their tasks.",
        description="Sherlocks are task-based DFIR challenges. Tasks live on"
        " /sherlocks/<id>/tasks, not in the list or info payload.",
    )
    sherlock_sub = sherlock.add_subparsers(dest="sherlock_command")

    list_cmd = _leaf(sherlock_sub, "list", common, help="List Sherlocks with paging and filters.")
    list_cmd.add_argument("--active", action="store_true", help="Only the active Sherlocks.")
    list_cmd.add_argument(
        "--difficulty",
        type=_difficulty,
        default=None,
        metavar="{very-easy,easy,medium,hard,insane}",
    )
    _add_owned_filters(list_cmd)
    list_cmd.add_argument(
        "--search",
        default=None,
        help="Case-insensitive substring match on the name, or an exact id.",
    )
    list_cmd.add_argument(
        "--limit",
        type=_positive_int,
        default=20,
        help="Maximum rows to print. Default 20.",
    )
    list_cmd.add_argument("--all", action="store_true", help="Print every match, ignoring --limit.")
    list_cmd.add_argument(
        "--no-cache",
        action="store_true",
        help="Refetch pages instead of serving them from the 5 minute page cache.",
    )
    list_cmd.set_defaults(handler=handlers.sherlock_list)

    tasks = _leaf(sherlock_sub, "tasks", common, help="List a Sherlock's task ids and questions.")
    tasks.add_argument("id", type=_positive_int)
    tasks.add_argument("--hints", action="store_true", help="Include each task's hint (spoilers).")
    tasks.set_defaults(handler=handlers.sherlock_tasks)

    answer = _leaf(sherlock_sub, "answer", common, help="Answer one Sherlock task.")
    answer.add_argument("id", type=_positive_int)
    answer.add_argument("task_id", type=_positive_int)
    answer.add_argument("answer", help="The graded answer string.")
    answer.set_defaults(handler=handlers.sherlock_answer)

    info = _leaf(
        sherlock_sub,
        "info",
        common,
        help="Show one Sherlock's metadata, including the archive password.",
    )
    info.add_argument("id", type=_positive_int)
    info.set_defaults(handler=handlers.sherlock_info)

    dl = _leaf(
        sherlock_sub,
        "download",
        common,
        help="Download a Sherlock archive (API currently answers file-not-found).",
    )
    dl.add_argument("id", type=_positive_int)
    dl.add_argument("-o", "--out", type=Path, default=None, help="Output zip path.")
    dl.add_argument("--extract", action="store_true", help="Extract after download.")
    dl.add_argument(
        "--password",
        default=None,
        help="Archive password. Defaults to the instance's file_password.",
    )
    dl.set_defaults(handler=handlers.sherlock_download)

    progress = _leaf(
        sherlock_sub,
        "progress",
        common,
        help="Show answered/total tasks and ownership for one Sherlock.",
    )
    progress.add_argument("id", type=_positive_int)
    progress.set_defaults(handler=handlers.sherlock_progress)


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
    servers.set_defaults(
        handler=handlers.vpn_servers,
        needs_auth=_vpn_servers_needs_auth,
    )

    switch = _leaf(vpn_sub, "switch", common, help="Switch to a VPN server by id, alias, or name.")
    switch.add_argument("server")
    switch.set_defaults(handler=handlers.vpn_switch)

    download = _leaf(vpn_sub, "download", common, help="Download an OVPN file.")
    download.add_argument("server")
    download.add_argument("-o", "--output", type=Path, default=Path("lab-vpn.ovpn"))
    download.add_argument("--variant", type=_non_negative_int, default=0)
    download.set_defaults(handler=handlers.vpn_download)

    connect = _leaf(vpn_sub, "connect", common, help="Switch, download, then run OpenVPN.")
    connect.add_argument("server")
    connect.add_argument("-o", "--output", type=Path, default=Path("lab-vpn.ovpn"))
    connect.add_argument("--variant", type=_non_negative_int, default=0)
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
    speedrun.add_argument("--variant", type=_non_negative_int, default=0)
    speedrun.add_argument("--interface", default="tun0", help="Tunnel interface to tune. Default tun0.")
    speedrun.add_argument(
        "--mtu",
        type=_positive_int,
        default=1300,
        help="MTU to set on the interface. Default 1300.",
    )
    speedrun.add_argument("--mode", choices=["auto", "play", "spawn"], default="auto")
    speedrun.add_argument(
        "--retry-for",
        type=_positive_int,
        default=900,
        metavar="SECONDS",
        help="Keep retrying the spawn for up to this long. Default 900.",
    )
    speedrun.add_argument(
        "--interval",
        type=_positive_int,
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


def _add_lab_commands(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    prolab = subparsers.add_parser(
        "prolab",
        help="List Pro Labs and their machines.",
        description="Pro Labs are multiplayer networks reached over their own VPN"
        " profile. There is no /prolab/<id> detail route, so the list payload is the"
        " only source of lab metadata.",
    )
    prolab_sub = prolab.add_subparsers(dest="prolab_command")
    labs = _leaf(prolab_sub, "list", common, help="List Pro Labs.")
    labs.set_defaults(handler=handlers.prolab_list)
    info = _leaf(
        prolab_sub, "info", common, help="Show one Pro Lab's detail (entry points, counts)."
    )
    info.add_argument("id", type=_positive_int)
    info.set_defaults(handler=handlers.prolab_info)
    flags = _leaf(
        prolab_sub, "flags", common, help="List a Pro Lab's flags with points and ownership."
    )
    flags.add_argument("id", type=_positive_int)
    flags.set_defaults(handler=handlers.prolab_flags)
    machines = _leaf(
        prolab_sub, "machines", common, help="List the machines inside one Pro Lab."
    )
    machines.add_argument("id", type=_positive_int)
    machines.set_defaults(handler=handlers.prolab_machines)
    pown = _leaf(prolab_sub, "own", common, help="Submit one Pro Lab flag.")
    pown.add_argument("id", type=_positive_int)
    pown.add_argument("--flag", required=True, help="The flag value, for example HTB{...}.")
    pown.set_defaults(handler=handlers.prolab_own)

    fortress = subparsers.add_parser(
        "fortress",
        help="List Fortresses and inspect their flags.",
        description="A fortress is scored by named flags rather than user/root"
        " pairs; /fortress/<id> returns them with points and owned state.",
    )
    fortress_sub = fortress.add_subparsers(dest="fortress_command")
    flist = _leaf(fortress_sub, "list", common, help="List Fortresses.")
    flist.set_defaults(handler=handlers.fortress_list)
    finfo = _leaf(
        fortress_sub, "info", common, help="Show one Fortress, its flags, and progress."
    )
    finfo.add_argument("id", type=_positive_int)
    finfo.set_defaults(handler=handlers.fortress_info)
    fown = _leaf(fortress_sub, "own", common, help="Submit one fortress flag.")
    fown.add_argument("id", type=_positive_int)
    fown.add_argument("--flag", required=True, help="The flag value, for example HTB{...}.")
    fown.set_defaults(handler=handlers.fortress_own)


def _add_progress_commands(subparsers: _SubParsers, common: argparse.ArgumentParser) -> None:
    progress = subparsers.add_parser(
        "progress",
        help="Show your own owns, fortress, and Pro Lab progress.",
        description="Read-only account views. /profile/progress/machines/os/<id> is gone;"
        " the aggregate routes (/machines, /challenges, /fortress, /prolab) still work.",
    )
    progress_sub = progress.add_subparsers(dest="progress_command")
    show = _leaf(
        progress_sub,
        "show",
        common,
        help="Summary of machines and challenges, or one category.",
    )
    show.add_argument(
        "kind",
        nargs="?",
        choices=["machines", "challenges", "fortress", "prolab"],
        default=None,
        help="Omit for a summary of everything.",
    )
    show.set_defaults(handler=handlers.progress_show)
    submissions = _leaf(
        progress_sub, "submissions", common, help="Your machine or challenge submissions."
    )
    submissions.add_argument(
        "kind", nargs="?", choices=["machines", "challenges"], default="machines"
    )
    submissions.set_defaults(handler=handlers.progress_submissions)
    connection = _leaf(
        progress_sub, "connection", common, help="VPN/tunnel connection status."
    )
    connection.set_defaults(handler=handlers.progress_connection)
