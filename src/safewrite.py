"""Atomic text-file writes.

Writes to a temp file in the target's directory, then os.replace()s it over
the destination -- an atomic operation on the same volume. A crash, power
cut, or task-scheduler kill mid-write can no longer leave a state file
(posted_log.json above all) half-written and unparseable.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
