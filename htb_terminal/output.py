from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from typing import Any

from htb_terminal import box, theme

RESET = "\033[0m"
STYLES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "magenta": "\033[35m",
}


def color_enabled(mode: str = "auto") -> bool:
    """Public wrapper: should colored output be emitted for this mode?"""
    return _color_enabled(mode)


def style(text: str, name: str, enabled: bool) -> str:
    """Public wrapper: wrap text in an ANSI style when enabled."""
    return _style(text, name, enabled)


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def print_pretty(value: Any, color: str = "auto") -> None:
    enabled = _color_enabled(color)
    width = shutil.get_terminal_size((100, 24)).columns
    if isinstance(value, dict):
        _print_mapping(value, color=enabled, width=width)
        return
    if isinstance(value, list):
        _print_list(value, indent=0, color=enabled, width=width)
        return
    print(_format_value(value, enabled))


def print_table(
    rows: list[dict[str, Any]],
    columns: list[str],
    color: str = "auto",
    *,
    wide: bool = False,
) -> None:
    enabled = _color_enabled(color)
    if not rows:
        print(_style("No rows.", "dim", enabled))
        return

    widths = _table_widths(rows, columns, wide=wide)
    print("  ".join(_style(column.ljust(widths[column]), "bold", enabled) for column in columns))
    print(_style("  ".join("-" * widths[column] for column in columns), "dim", enabled))
    for row in rows:
        cells = []
        for column in columns:
            raw = row.get(column)
            text = _truncate(_format_cell(raw), widths[column]).ljust(widths[column])
            cells.append(_style(text, theme.cell_style(column, raw), enabled))
        print("  ".join(cells))


def print_status_line(info: dict[str, Any], color: str = "auto") -> None:
    """Print a compact one-line summary of the active machine."""
    enabled = _color_enabled(color)
    name = info.get("name")
    if not name:
        print(_style("No active machine.", "dim", enabled))
        return

    parts = [_style("ACTIVE", "green", enabled), _style(str(name), "bold", enabled)]
    if info.get("ip"):
        parts.append(str(info["ip"]))
    os_diff = "/".join(str(value) for value in (info.get("os"), info.get("difficulty")) if value)
    if os_diff:
        parts.append(os_diff)
    expires = info.get("expires_in")
    if expires:
        label = expires if expires == "expired" else f"expires {expires}"
        parts.append(_style(label, "yellow", enabled))
    if info.get("spawned"):
        parts.append(_style("[spawned]", "cyan", enabled))
    print("  ".join(parts))


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _table_widths(rows: list[dict[str, Any]], columns: list[str], *, wide: bool) -> dict[str, int]:
    natural = {
        column: max(len(column), *(len(_format_cell(row.get(column))) for row in rows))
        for column in columns
    }
    if wide:
        return natural

    terminal_width = shutil.get_terminal_size((100, 24)).columns
    separator_width = max(0, len(columns) - 1) * 2
    available = max(len(columns), terminal_width - separator_width)
    minimums = {column: min(max(len(column), 3), 8) for column in columns}
    widths = {
        column: min(natural[column], _preferred_column_width(column, terminal_width))
        for column in columns
    }

    overflow = sum(widths.values()) - available
    while overflow > 0:
        candidates = [
            column
            for column in columns
            if widths[column] > minimums[column] and widths[column] == max(widths.values())
        ]
        if not candidates:
            break
        column = candidates[0]
        widths[column] -= 1
        overflow -= 1

    return widths


def _preferred_column_width(column: str, terminal_width: int) -> int:
    defaults = {
        "id": 6,
        "name": 28,
        "alias": 18,
        "os": 10,
        "difficulty": 12,
        "points": 8,
        "active": 7,
        "spawned": 7,
        "free": 5,
        "retired": 7,
        "scope": 10,
        "location": 10,
    }
    return min(defaults.get(column, 24), max(8, terminal_width // 3))


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 3:
        return "." * width
    return f"{text[: width - 3]}..."


def _print_mapping(mapping: dict[str, Any], *, color: bool, width: int, indent: int = 0) -> None:
    if len(mapping) == 1:
        key, value = next(iter(mapping.items()))
        if isinstance(value, dict):
            _print_section_header(str(key), color=color, indent=indent)
            _print_mapping(value, color=color, width=width, indent=indent + 2)
            return

    items = [(str(key), value) for key, value in mapping.items() if not _is_empty(value)]
    if not items:
        print(f"{' ' * indent}{_style('No data.', 'dim', color)}")
        return

    key_width = min(max(len(key) for key, _ in items), 22)
    for key, value in items:
        _print_field(key, value, key_width=key_width, color=color, width=width, indent=indent)


def _print_section_header(title: str, *, color: bool, indent: int) -> None:
    left = " " * indent
    if indent == 0:
        for line in box.section_header(title, enabled=color):
            print(f"{left}{line}")
        return
    print(f"{left}{_style(title, 'bold', color)}")


def _print_field(key: str, value: Any, *, key_width: int, color: bool, width: int, indent: int) -> None:
    left = " " * indent
    key_text = key.ljust(key_width)
    label = f"{left}{_style(key_text, 'cyan', color)}  "
    plain_label = f"{left}{key_text}  "

    if isinstance(value, dict):
        print(f"{label.rstrip()}:")
        _print_mapping(value, color=color, width=width, indent=indent + 2)
        return

    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            joined = ", ".join(_format_cell(item) for item in value)
            if len(plain_label) + len(joined) <= width:
                print(f"{label}{_style(joined, 'yellow', color)}")
            else:
                print(f"{label.rstrip()}:")
                _print_list(value, indent=indent + 2, color=color, width=width)
            return
        print(f"{label.rstrip()}:")
        _print_list(value, indent=indent + 2, color=color, width=width)
        return

    field_style = theme.cell_style(key, value)
    plain_text = _format_cell(value)
    available = max(24, width - len(plain_label))
    wrapped = textwrap.wrap(plain_text, width=available, break_long_words=False, break_on_hyphens=False) or [""]
    print(f"{label}{_style(wrapped[0], field_style, color)}")
    for line in wrapped[1:]:
        print(f"{' ' * len(plain_label)}{_style(line, field_style, color)}")


def _print_list(values: list[Any], *, indent: int, color: bool, width: int) -> None:
    if not values:
        print(f"{' ' * indent}{_style('none', 'dim', color)}")
        return

    for value in values:
        prefix = f"{' ' * indent}- "
        if isinstance(value, dict):
            summary = _item_summary(value)
            if summary:
                print(f"{prefix}{_style(summary, 'yellow', color)}")
            else:
                print(prefix.rstrip())
            _print_mapping(value, color=color, width=width, indent=indent + 2)
        elif isinstance(value, list):
            print(prefix.rstrip())
            _print_list(value, indent=indent + 2, color=color, width=width)
        else:
            text = _format_cell(value)
            wrapped = textwrap.wrap(
                text,
                width=max(24, width - len(prefix)),
                break_long_words=False,
                break_on_hyphens=False,
            ) or [""]
            print(f"{prefix}{_style(wrapped[0], 'yellow', color)}")
            for line in wrapped[1:]:
                print(f"{' ' * len(prefix)}{_style(line, 'yellow', color)}")


def _item_summary(value: dict[str, Any]) -> str:
    if value.get("name") and value.get("id") is not None:
        return f"{value['name']} ({value['id']})"
    if value.get("name"):
        return str(value["name"])
    if value.get("message"):
        return str(value["message"])
    return ""


def _format_value(value: Any, color: bool) -> str:
    return _style(_format_cell(value), theme.value_style(value), color)


def _is_empty(value: Any) -> bool:
    return value is None or value == [] or value == {}


def _color_enabled(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def _style(text: str, style: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{STYLES[style]}{text}{RESET}"
