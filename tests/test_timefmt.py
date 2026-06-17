from __future__ import annotations

import unittest
from datetime import datetime, timezone

from htb_terminal.timefmt import relative_expiry

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class RelativeExpiryTests(unittest.TestCase):
    def test_future_hours_and_minutes(self) -> None:
        self.assertEqual("in 1h 12m", relative_expiry("2026-01-01T13:12:00Z", now=NOW))

    def test_future_minutes_only(self) -> None:
        self.assertEqual("in 47m", relative_expiry("2026-01-01T12:47:00Z", now=NOW))

    def test_past_is_expired(self) -> None:
        self.assertEqual("expired", relative_expiry("2026-01-01T11:00:00Z", now=NOW))

    def test_naive_timestamp_is_treated_as_utc(self) -> None:
        self.assertEqual("in 30m", relative_expiry("2026-01-01T12:30:00", now=NOW))

    def test_missing_or_bad_values_return_none(self) -> None:
        self.assertIsNone(relative_expiry(None, now=NOW))
        self.assertIsNone(relative_expiry("", now=NOW))
        self.assertIsNone(relative_expiry("not-a-date", now=NOW))


if __name__ == "__main__":
    unittest.main()
