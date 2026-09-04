"""Atomic text-file write: write a sibling temp file, then ``os.replace``.

``os.replace`` is atomic on POSIX and Windows, so a crash mid-write never
leaves a half-written file and concurrent writers (unique per-pid temp names)
don't clobber each other. On Windows the replace can briefly lose a race with
an AV scanner or a lingering handle, so it is retried a few times.

Used by the task DB, the sidecar collections and the settings store.
"""
import itertools
import os
import time
from pathlib import Path

_counter = itertools.count()


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{next(_counter)}.tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
