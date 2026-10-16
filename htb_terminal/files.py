"""Private credential-file writes shared by token and VPN configuration storage."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path


def write_private_file(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise OSError(errno.EINVAL, "output must be a single-link regular file")
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        os.ftruncate(descriptor, 0)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(content)
    except OSError as exc:
        raise RuntimeError(f"Could not securely write private file {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
