"""Branded help: an ASCII banner and a tidy help formatter.

The banner is plain ASCII (no emoji) and is colored only when stdout is a TTY,
so piping ``htb --help`` stays clean. The formatter widens the help column so
subcommand descriptions line up.
"""

from __future__ import annotations

import argparse

from htb_terminal.output import color_enabled, style

_BANNER = r"""
 _     _   _
| |__ | |_| |__
| '_ \| __| '_ \
| | | | |_| |_) |
|_| |_|\__|_.__/
""".strip("\n")


def banner(tagline: str) -> str:
    enabled = color_enabled("auto")
    return f"{style(_BANNER, 'cyan', enabled)}\n{style(tagline, 'dim', enabled)}"


class HtbHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Keep the banner's line breaks and give help text room to align."""

    def __init__(self, prog: str, **kwargs: object) -> None:
        super().__init__(prog, max_help_position=32, **kwargs)
