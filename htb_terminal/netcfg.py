"""Host network and process operations for the speedrun workflow.

This is the only module that touches the local machine's network stack and
OpenVPN process. Everything is injectable (subprocess runner, clock, interface
probe) so the orchestration can be tested without root or a real tunnel.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path


def ensure_root() -> None:
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise RuntimeError(
            "speedrun needs root to run OpenVPN and set the MTU. Re-run with sudo."
        )


def start_openvpn(
    config_path: Path,
    *,
    command: Sequence[str] = ("openvpn",),
    log_path: Path | None = None,
) -> subprocess.Popen:
    args = [*command, "--config", str(config_path)]
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "ab") as handle:
            return subprocess.Popen(args, stdout=handle, stderr=handle)
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def interface_exists(name: str) -> bool:
    return Path(f"/sys/class/net/{name}").exists()


def ensure_openvpn_active(
    process: subprocess.Popen,
    interface: str,
    *,
    exists: Callable[[str], bool] = interface_exists,
    log_path: Path | None = None,
) -> None:
    return_code = process.poll()
    if return_code is not None:
        log_hint = f" Check {log_path}." if log_path is not None else ""
        raise RuntimeError(
            f"OpenVPN exited unexpectedly with code {return_code}.{log_hint}"
        )
    if not exists(interface):
        raise RuntimeError(f"VPN interface {interface} is no longer active.")


def stop_openvpn(process: subprocess.Popen, *, timeout: float = 10.0) -> None:
    """Stop and reap an OpenVPN process, escalating when it ignores SIGTERM."""
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        process.wait()
        return
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            process.wait()
            return
        process.wait()


def wait_for_interface(
    name: str,
    *,
    is_alive: Callable[[], bool] | None = None,
    exists: Callable[[str], bool] = interface_exists,
    timeout: float = 30.0,
    interval: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    deadline = monotonic() + timeout
    while True:
        if exists(name):
            return
        if is_alive is not None and not is_alive():
            raise RuntimeError(f"OpenVPN exited before {name} came up. Check the VPN log.")
        if monotonic() >= deadline:
            raise RuntimeError(f"{name} did not come up within {timeout:.0f}s.")
        sleep(interval)


def set_mtu(
    name: str,
    mtu: int,
    *,
    runner: Callable[..., object] = subprocess.run,
) -> None:
    runner(["ip", "link", "set", name, "mtu", str(mtu)], check=True)
