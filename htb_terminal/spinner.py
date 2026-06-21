"""A minimal, thread-driven ASCII spinner for long-running steps.

Used as a context manager: it animates ``label ... <frame> (<elapsed>s)`` in
place on its stream, then clears the line on exit so the caller can print the
final status. ASCII frames only (no emoji). The caller is responsible for
enabling it only on a TTY.
"""

from __future__ import annotations

import itertools
import threading
import time
from types import TracebackType
from typing import TextIO

_FRAMES = "|/-\\"
_CLEAR_LINE = "\r\033[K"


class Spinner:
    def __init__(self, label: str, *, stream: TextIO, interval: float = 0.1):
        self.label = label
        self.stream = stream
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Spinner:
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.stream.write(_CLEAR_LINE)
        self.stream.flush()

    def _spin(self) -> None:
        start = time.monotonic()
        for frame in itertools.cycle(_FRAMES):
            if self._stop.is_set():
                return
            elapsed = time.monotonic() - start
            self.stream.write(f"\r  {self.label} ... {frame} ({elapsed:.0f}s)")
            self.stream.flush()
            time.sleep(self.interval)
