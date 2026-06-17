from __future__ import annotations

import io
import unittest

from htb_terminal.ui import StepRunner


class StepRunnerTests(unittest.TestCase):
    def test_success_prints_ok(self) -> None:
        stream = io.StringIO()
        runner = StepRunner(color="never", stream=stream)
        with runner.step("connect"):
            pass
        self.assertEqual("  connect ... ok\n", stream.getvalue())

    def test_failure_prints_failed_and_reraises(self) -> None:
        stream = io.StringIO()
        runner = StepRunner(color="never", stream=stream)
        with self.assertRaises(ValueError):
            with runner.step("set mtu"):
                raise ValueError("boom")
        self.assertIn("set mtu ... FAILED", stream.getvalue())

    def test_header_and_note(self) -> None:
        stream = io.StringIO()
        runner = StepRunner(color="never", stream=stream)
        runner.header("speedrun")
        runner.note("done")
        self.assertEqual("speedrun\ndone\n", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
