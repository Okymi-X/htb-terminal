from __future__ import annotations

import unittest
from typing import Any
from unittest import mock

from htb_terminal.http import ApiError
from htb_terminal.services.machines import MachineService
from htb_terminal.services.spawn import (
    is_active_instance_conflict,
    is_transient_spawn_error,
)


class SequenceClient:
    """Returns or raises queued responses per (method, path)."""

    def __init__(self, queues: dict[str, list[Any]]):
        self.queues = queues
        self.calls: list[str] = []

    def _next(self, path: str) -> Any:
        self.calls.append(path)
        value = self.queues[path].pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def get(self, path: str, query: dict[str, Any] | None = None) -> Any:
        return self._next(path)

    def post(self, path: str, data: dict[str, Any] | None = None) -> Any:
        return self._next(path)


class TransientSpawnErrorTests(unittest.TestCase):
    def test_capacity_statuses_and_messages_are_transient(self):
        self.assertTrue(is_transient_spawn_error(ApiError(503, "HTTP 503")))
        self.assertTrue(is_transient_spawn_error(ApiError(429, "HTTP 429")))
        self.assertTrue(
            is_transient_spawn_error(
                ApiError(400, "HTTP 400: All spawn slots are full, try again later")
            )
        )

    def test_other_errors_are_not_transient(self):
        self.assertFalse(is_transient_spawn_error(ApiError(401, "HTTP 401: Unauthorized")))
        self.assertFalse(is_transient_spawn_error(ApiError(404, "HTTP 404: Not found")))


class ActiveInstanceConflictTests(unittest.TestCase):
    def test_detects_active_instance_rejection(self):
        self.assertTrue(
            is_active_instance_conflict(
                ApiError(403, "HTTP 403: You already have an active instance")
            )
        )

    def test_ignores_capacity_and_unrelated_errors(self):
        # A full spawn server is transient capacity, not an active-instance lock.
        self.assertFalse(
            is_active_instance_conflict(ApiError(403, "HTTP 403: spawn capacity full"))
        )
        # 409 "already active elsewhere" is the play->spawn fallback, not a lock.
        self.assertFalse(
            is_active_instance_conflict(ApiError(409, "HTTP 409: already active elsewhere"))
        )
        self.assertFalse(is_active_instance_conflict(ApiError(500, "boom")))


class StartWithRetryTests(unittest.TestCase):
    def test_retries_capacity_errors_until_spawn_succeeds(self):
        client = SequenceClient(
            {
                "/machine/play/100": [
                    ApiError(409, "HTTP 409: already active elsewhere"),
                    ApiError(409, "HTTP 409: already active elsewhere"),
                ],
                "/vm/spawn": [
                    ApiError(503, "HTTP 503: spawn capacity full"),
                    {"message": "Machine deployed"},
                ],
            }
        )
        service = MachineService(client)

        with mock.patch("htb_terminal.services.machines.time.sleep") as sleep:
            result = service.start_with_retry("100", "auto", retry_for=600, interval=15)

        self.assertEqual({"message": "Machine deployed"}, result)
        self.assertEqual(1, sleep.call_count)
        # Jittered delay stays within 20% of the base interval.
        delay = sleep.call_args.args[0]
        self.assertGreaterEqual(delay, 12.0)
        self.assertLessEqual(delay, 18.0)

    def test_non_transient_error_raises_immediately(self):
        client = SequenceClient(
            {"/machine/play/100": [ApiError(401, "HTTP 401: Unauthorized")]}
        )
        service = MachineService(client)

        with mock.patch("htb_terminal.services.machines.time.sleep") as sleep:
            with self.assertRaises(ApiError):
                service.start_with_retry("100", "play", retry_for=600, interval=15)

        sleep.assert_not_called()

    def test_gives_up_when_deadline_is_reached(self):
        client = SequenceClient(
            {"/machine/play/100": [ApiError(503, "HTTP 503: full")] * 10}
        )
        service = MachineService(client)

        clock = iter(range(0, 10_000, 100))
        with (
            mock.patch("htb_terminal.services.machines.time.sleep"),
            mock.patch(
                "htb_terminal.services.machines.time.monotonic",
                side_effect=lambda: next(clock),
            ),
        ):
            with self.assertRaises(ApiError) as ctx:
                service.start_with_retry("100", "play", retry_for=300, interval=15)

        self.assertIn("Gave up", str(ctx.exception))


class WaitForActiveIpTests(unittest.TestCase):
    def test_polls_until_ip_is_assigned(self):
        client = SequenceClient(
            {
                "/machine/active": [
                    {"info": {"id": 100, "ip": None}},
                    {"info": {"id": 100, "ip": "10.129.1.2", "name": "Seasonal"}},
                ],
            }
        )
        service = MachineService(client)

        with mock.patch("htb_terminal.services.machines.time.sleep"):
            info = service.wait_for_active_ip(100, timeout=120, interval=10)

        self.assertEqual("10.129.1.2", info["ip"])

    def test_fails_fast_when_instance_collapses(self):
        # Seen active once, then it vanishes ("No data"): stop waiting, diagnose.
        client = SequenceClient(
            {
                "/machine/active": [
                    {"info": {"id": 100, "ip": None}},
                    {"info": None},
                ],
            }
        )
        service = MachineService(client)

        with mock.patch("htb_terminal.services.machines.time.sleep"):
            with self.assertRaises(RuntimeError) as ctx:
                service.wait_for_active_ip(100, timeout=120, interval=10)

        self.assertIn("dropped out", str(ctx.exception))
        # Only two polls happened — it did not burn the whole timeout.
        self.assertEqual(2, client.calls.count("/machine/active"))

    def test_times_out_without_ip(self):
        client = SequenceClient({"/machine/active": [{"info": {"id": 100, "ip": None}}] * 50})
        service = MachineService(client)

        clock = iter(range(0, 10_000, 60))
        with (
            mock.patch("htb_terminal.services.machines.time.sleep"),
            mock.patch(
                "htb_terminal.services.machines.time.monotonic",
                side_effect=lambda: next(clock),
            ),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                service.wait_for_active_ip(100, timeout=120, interval=10)

        self.assertIn("no IP", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
