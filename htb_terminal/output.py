from __future__ import annotations

import json
import os
import re
import shutil
import sys
import textwrap
from typing import Any


RESET = "\033[0m"
STYLES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
}


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


def print_table(rows: list[dict[str, Any]], columns: list[str], color: str = "auto") -> None:
    enabled = _color_enabled(color)
    if not rows:
        print(_style("No rows.", "dim", enabled))
        return

    widths = {
        column: max(len(column), *(len(_format_cell(row.get(column))) for row in rows))
        for column in columns
    }
    print("  ".join(_style(column.ljust(widths[column]), "bold", enabled) for column in columns))
    print(_style("  ".join("-" * widths[column] for column in columns), "dim", enabled))
    for row in rows:
        cells = []
        for column in columns:
            raw = row.get(column)
            text = _format_cell(raw).ljust(widths[column])
            cells.append(_format_cell_for_output(raw, text, enabled))
        print("  ".join(cells))


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _print_mapping(mapping: dict[str, Any], *, color: bool, width: int, indent: int = 0) -> None:
    if len(mapping) == 1:
        key, value = next(iter(mapping.items()))
        if isinstance(value, dict):
            print(f"{' ' * indent}{_style(str(key), 'bold', color)}")
            _print_mapping(value, color=color, width=width, indent=indent + 2)
            return

    items = [(str(key), value) for key, value in mapping.items() if not _is_empty(value)]
    if not items:
        print(f"{' ' * indent}{_style('No data.', 'dim', color)}")
        return

    key_width = min(max(len(key) for key, _ in items), 22)
    for key, value in items:
        _print_field(key, value, key_width=key_width, color=color, width=width, indent=indent)


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

    text = _format_value(value, color)
    plain_text = _strip_ansi(text)
    available = max(24, width - len(plain_label))
    wrapped = textwrap.wrap(plain_text, width=available, break_long_words=False, break_on_hyphens=False) or [""]
    print(f"{label}{_style(wrapped[0], _value_style(value), color)}")
    for line in wrapped[1:]:
        print(f"{' ' * len(plain_label)}{_style(line, _value_style(value), color)}")


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
    return _style(_format_cell(value), _value_style(value), color)


def _format_cell_for_output(value: Any, text: str, color: bool) -> str:
    return _style(text, _value_style(value), color)


def _value_style(value: Any) -> str:
    if isinstance(value, bool):
        return "green" if value else "red"
    if value is None:
        return "dim"
    if isinstance(value, (int, float)):
        return "yellow"
    return "yellow"


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


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)
