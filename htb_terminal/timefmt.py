"""Small, dependency-free time formatting helpers for display."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def relative_expiry(value: Any, *, now: datetime | None = None) -> str | None:
    """Turn an ISO-8601 timestamp into a short relative string.

    Returns ``"in 47m"`` / ``"in 1h 12m"`` for the future, ``"expired"`` for the
    past, and ``None`` when the value is missing or unparseable.
    """
    moment = _parse(value)
    if moment is None:
        return None
    current = now or datetime.now(timezone.utc)
    seconds = (moment - current).total_seconds()
    if seconds <= 0:
        return "expired"
    return f"in {_humanize(seconds)}"


def _humanize(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment
