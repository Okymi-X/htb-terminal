"""Light box-drawing helpers: rules, section headers, and framed panels.

Pure string builders. They take already-plain text and an ``enabled`` flag and
return styled strings; the caller decides where to print them. No emoji, only
single-line box-drawing characters.
"""

from __future__ import annotations

from collections.abc import Iterable

_H = "─"
_V = "│"
_TL = "┌"
_TR = "┐"
_BL = "└"
_BR = "┘"


def rule(width: int, *, enabled: bool) -> str:
    from htb_terminal.output import style

    return style(_H * max(1, width), "dim", enabled)


def section_header(title: str, *, enabled: bool) -> list[str]:
    """A bold title above a dim underline the width of the title."""
    from htb_terminal.output import style

    return [style(title, "bold", enabled), rule(len(title), enabled=enabled)]


def panel(lines: Iterable[str], *, title: str = "", enabled: bool = False) -> list[str]:
    """Frame plain-text lines in a single-line box with an optional title."""
    from htb_terminal.output import style

    body = list(lines)
    inner = max((len(line) for line in body), default=0)
    inner = max(inner, len(title))

    top = _TL + _H + _titled_rule(title, inner) + _H + _TR
    bottom = _BL + _H * (inner + 2) + _BR
    out = [style(top, "dim", enabled)]
    for line in body:
        bar = style(_V, "dim", enabled)
        out.append(f"{bar} {line.ljust(inner)} {bar}")
    out.append(style(bottom, "dim", enabled))
    return out


def _titled_rule(title: str, inner: int) -> str:
    if not title:
        return _H * inner
    return f"{title} ".ljust(inner, _H)
