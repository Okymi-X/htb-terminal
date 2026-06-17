"""Live step status for multi-step workflows.

``StepRunner`` prints a tidy, color- and TTY-aware line per step (``ok`` or
``FAILED``). It is stdlib-only and emoji-free, and writes to stderr by default
so stdout stays clean for machine-readable output.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO

from htb_terminal.output import color_enabled, style


class StepRunner:
    def __init__(self, *, color: str = "auto", stream: TextIO | None = None):
        self.stream = stream if stream is not None else sys.stderr
        self.enabled = color_enabled(color)

    def header(self, text: str) -> None:
        self._writeln(style(text, "bold", self.enabled))

    def note(self, text: str) -> None:
        self._writeln(style(text, "dim", self.enabled))

    @contextmanager
    def step(self, label: str) -> Iterator[None]:
        start = time.monotonic()
        try:
            yield
        except BaseException:
            self._writeln(f"  {label} ... {style('FAILED', 'red', self.enabled)}")
            raise
        else:
            elapsed = time.monotonic() - start
            status = f"ok ({elapsed:.0f}s)" if elapsed >= 1.5 else "ok"
            self._writeln(f"  {label} ... {style(status, 'green', self.enabled)}")

    def _writeln(self, text: str) -> None:
        print(text, file=self.stream, flush=True)
