#!/usr/bin/env python3
"""Render a realistic `htb machine start --wait` seasonal flow for screenshots.

Fixed script (no token, no root, no network): it mirrors the retry messages the
real command prints to stderr while the spawn server is full, then the
pretty-printed result it prints once a slot frees and the IP lands.

    python3 scripts/demo_seasonal_start.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from htb_terminal.output import print_pretty  # noqa: E402

_BUSY = "HTTP 500: Failed to spawn machine on the Release Arena server. Please try again."


def main() -> None:
    print(f"spawn server busy (attempt 1): {_BUSY}; retrying in 5s")
    print(f"spawn server busy (attempt 2): {_BUSY}; retrying in 4s")
    print(f"spawn server busy (attempt 3): {_BUSY}; retrying in 6s")
    print("waiting for machine IP...")
    print_pretty(
        {
            "id": 901,
            "name": "Connected",
            "ip": "10.129.231.88",
            "spawn": {"message": "Machine deployed to lab."},
        },
        color="always",
    )


if __name__ == "__main__":
    main()
