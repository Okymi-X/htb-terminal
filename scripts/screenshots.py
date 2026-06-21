#!/usr/bin/env python3
"""Generate docs/screenshots/*.png headlessly.

Pipeline: capture a command's ANSI output -> render it to SVG with ``rich``
-> screenshot the SVG to PNG with a headless Chromium. This needs no PTY, so it
works on headless boxes and CI where terminal-recording tools cannot run.

Requirements: ``rich`` (already a tabletop dependency-free import here) and a
Chromium/Chrome binary on PATH. Machine shots need a saved token (``htb init``)
and, ideally, an active machine.

    python3 scripts/screenshots.py                 # all shots
    python3 scripts/screenshots.py vpn-servers      # a subset
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
_HTB = [sys.executable, "-m", "htb_terminal.cli", "--color", "always"]

# name -> (prompt shown in the shot, argv actually run)
SHOTS: dict[str, tuple[str, list[str]]] = {
    "vpn-servers": ("htb vpn servers", [*_HTB, "vpn", "servers"]),
    "machine-active": ("htb machine active", [*_HTB, "machine", "active"]),
    "machine-oneline": ("htb machine active --oneline", [*_HTB, "machine", "active", "--oneline"]),
    "user-info": ("htb user info", [*_HTB, "user", "info"]),
    "machine-start-wait": (
        "htb machine start Connected --mode auto --wait --retry-for 360 --interval 5",
        [sys.executable, str(ROOT / "scripts" / "demo_seasonal_start.py")],
    ),
    "speedrun": ("sudo htb speedrun Seasonal us-free-1", [sys.executable, str(ROOT / "scripts" / "demo_speedrun.py")]),
}

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Floor on the render width (in columns) so shots with short, stacked output
# (user info, machine active) come out landscape instead of tall and narrow.
_MIN_WIDTH = 66


def _prompt(command: str) -> str:
    # Green "$" + bold command, like a real shell prompt above the output.
    return f"\x1b[32m$\x1b[0m \x1b[1m{command}\x1b[0m"


def _chromium() -> str:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("No Chromium/Chrome binary found on PATH.")


def _capture(command: list[str]) -> str:
    # COLUMNS pins the tool's own wrapping width; --color always forces styling.
    env = {**os.environ, "COLUMNS": "100"}
    env.pop("NO_COLOR", None)
    result = subprocess.run(
        command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    return result.stdout.rstrip("\n")


def _to_svg(name: str, ansi: str) -> Path:
    content = max((len(_ANSI.sub("", line)) for line in ansi.split("\n")), default=20)
    width = max(content + 2, _MIN_WIDTH)
    console = Console(record=True, width=width)
    console.print(Text.from_ansi(ansi))
    svg = OUT / f"{name}.svg"
    console.save_svg(str(svg), title=f"htb {name.replace('-', ' ')}")
    return svg


def _to_png(name: str, svg: Path, chromium: str) -> Path:
    box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg.read_text())
    width, height = (int(float(box.group(1))) + 1, int(float(box.group(2))) + 1) if box else (1000, 400)
    png = OUT / f"{name}.png"
    subprocess.run(
        [
            chromium,
            "--headless",
            "--no-sandbox",
            "--hide-scrollbars",
            "--force-device-scale-factor=2",
            "--default-background-color=00000000",
            f"--window-size={width},{height}",
            f"--screenshot={png}",
            svg.resolve().as_uri(),
        ],
        check=False,
        capture_output=True,
    )
    svg.unlink(missing_ok=True)
    return png


def main(names: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    chromium = _chromium()
    for name in names or SHOTS:
        shot = SHOTS.get(name)
        if shot is None:
            print(f"unknown shot: {name} (known: {', '.join(SHOTS)})", file=sys.stderr)
            continue
        prompt, command = shot
        body = f"{_prompt(prompt)}\n{_capture(command)}"
        png = _to_png(name, _to_svg(name, body), chromium)
        print(f"captured {name} -> {png.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
