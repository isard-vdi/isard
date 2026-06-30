"""Lightweight progress helpers: human-readable sizes/durations and a
background file-growth reporter used to show live transfer rate while a
subprocess streams an archive to disk."""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from pathlib import Path


def human_bytes(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_dur(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


@contextlib.contextmanager
def report_file_growth(
    path: Path,
    log: logging.Logger,
    *,
    label: str = "received",
    idle_msg: str | None = None,
    interval: float = 2.0,
):
    """While the `with` block runs, periodically log `path`'s size and the
    instantaneous growth rate. Emits `idle_msg` once while the file is still
    empty (e.g. a remote dump that hasn't started streaming yet)."""
    stop = threading.Event()

    def _run() -> None:
        last_t = time.monotonic()
        last_sz = 0
        announced = False
        while not stop.wait(interval):
            try:
                sz = path.stat().st_size
            except OSError:
                sz = 0
            now = time.monotonic()
            if sz <= 0:
                if idle_msg and not announced:
                    log.info("  %s", idle_msg)
                    announced = True
                continue
            rate = (sz - last_sz) / (now - last_t) if now > last_t else 0.0
            log.info("  …%s %s  (%.1f MB/s)", label, human_bytes(sz), rate / 1e6)
            last_t, last_sz = now, sz

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=2)
