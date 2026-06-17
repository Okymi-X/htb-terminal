"""Detection of transient spawn failures.

At peak moments (seasonal releases, Saturdays 19:00 UTC) ``/vm/spawn`` rejects
requests until a slot frees up. Telling those temporary rejections apart from
real errors is its own concern, kept out of ``MachineService``.
"""

from __future__ import annotations

from htb_terminal.http import ApiError

TRANSIENT_SPAWN_STATUSES = {429, 500, 502, 503, 504}
TRANSIENT_SPAWN_KEYWORDS = (
    "full",
    "busy",
    "capacity",
    "high load",
    "too many",
    "try again",
    "later",
    "wait",
)


def is_transient_spawn_error(exc: ApiError) -> bool:
    if exc.status in TRANSIENT_SPAWN_STATUSES:
        return True
    message = str(exc).lower()
    return any(keyword in message for keyword in TRANSIENT_SPAWN_KEYWORDS)
