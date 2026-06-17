#!/usr/bin/env python3
"""Render a realistic `htb speedrun` status for screenshots.

Uses the real StepRunner so the output matches production, but drives it with a
fixed script so it needs no token, no root, and no network. Run it directly:

    python3 scripts/demo_speedrun.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from htb_terminal.ui import StepRunner  # noqa: E402

STEPS = [
    ("resolve machine 'Seasonal'", 0.0),
    ("switch vpn server us-free-1", 0.0),
    ("download ovpn config", 0.0),
    ("start openvpn", 0.0),
    ("wait for tun0", 2.0),
    ("set tun0 mtu 1300", 0.0),
    ("spawn machine", 2.0),
    ("wait for machine ip", 2.0),
]


def main() -> None:
    ui = StepRunner(color="always", stream=sys.stdout)
    ui.header("speedrun: Seasonal via us-free-1")
    for label, delay in STEPS:
        with ui.step(label):
            if delay:
                time.sleep(delay)
    print("ready: Seasonal 10.10.11.50")
    ui.note("machine up on tun0 (mtu 1300). VPN is foreground; Ctrl-C to disconnect.")


if __name__ == "__main__":
    main()
