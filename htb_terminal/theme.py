"""Semantic style decisions.

Maps a value (and, where it helps, its column/field name) to a style name from
:mod:`htb_terminal.output`. This is the only place that knows that ``Easy`` is
green and ``Insane`` is magenta; the renderers just ask for a style name.
"""

from __future__ import annotations

from typing import Any

_DIFFICULTY = {
    "easy": "green",
    "medium": "yellow",
    "hard": "red",
    "insane": "magenta",
}

_OS = {
    "windows": "cyan",
    "linux": "green",
    "freebsd": "yellow",
    "openbsd": "yellow",
}

_DIFFICULTY_FIELDS = {"difficulty", "difficultytext"}
_OS_FIELDS = {"os"}


def value_style(value: Any) -> str:
    """Style a value by its Python type alone (no field context)."""
    if isinstance(value, bool):
        return "green" if value else "red"
    if value is None:
        return "dim"
    return "yellow"


def difficulty_style(value: Any) -> str | None:
    if isinstance(value, str):
        return _DIFFICULTY.get(value.strip().lower())
    return None


def os_style(value: Any) -> str | None:
    if isinstance(value, str):
        return _OS.get(value.strip().lower())
    return None


def cell_style(column: str, value: Any) -> str:
    """Style a value using its field name for extra meaning, then its type."""
    key = column.strip().lower()
    if key in _DIFFICULTY_FIELDS:
        return difficulty_style(value) or value_style(value)
    if key in _OS_FIELDS:
        return os_style(value) or value_style(value)
    return value_style(value)
