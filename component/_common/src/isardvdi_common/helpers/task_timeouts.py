# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-action RQ ``job_timeout`` budgets for storage tasks.

Every storage task runs in an RQ work-horse that is hard-killed (SIGALRM,
``JobTimeoutException``) once ``job_timeout`` wall-clock seconds elapse --
progress reporting does NOT extend it. Tasks enqueued without an explicit
timeout fall back to RQ's ``Queue.DEFAULT_TIMEOUT`` (180 s), which silently
kills any long-running operation (a multi-GB download / convert / sparsify /
move) mid-flight and marks it FAILED.

This module centralises a sane, configurable budget per action:

* Fast metadata tasks (delete, touch, info, status finalizes) keep a small
  ceiling that still catches a hung process.
* Long-running tasks scale with the disk/file size when it is known
  (``size_bytes / MIN_THROUGHPUT`` clamped to ``[FLOOR, CEIL]``), or get the
  CEIL when the size is unknown up front (e.g. a download whose length the
  upstream did not advertise).

All bounds are overridable via the environment so an install on slow storage
or a slow uplink can widen them without a code change.
"""

import os


def _int_env(name, default):
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


# Fast metadata / finalize tasks: enough to ride out an NFS stall, small
# enough to surface a genuinely hung worker.
FAST_TIMEOUT = _int_env("STORAGE_TASK_FAST_TIMEOUT", 300)

# Long-running tasks: the size-derived budget is clamped to this window.
LONG_FLOOR = _int_env("STORAGE_TASK_TIMEOUT_FLOOR", 600)  # 10 min
LONG_CEIL = _int_env("STORAGE_TASK_TIMEOUT_CEIL", 6 * 3600)  # 6 h

# Conservative sustained throughput used to turn a byte size into a second
# budget. 5 MB/s is deliberately pessimistic so the budget errs generous.
MIN_THROUGHPUT_BPS = _int_env("STORAGE_TASK_MIN_THROUGHPUT_BPS", 5 * 1024 * 1024)

# Actions whose duration scales with disk/file size or a network transfer.
LONG_ACTIONS = frozenset(
    {
        "download_url",
        "download_url_for_domain",
        "convert",
        "sparsify",
        "move",
        "create",
        "disconnect",
        "virt_win_reg",
        "find",
    }
)


def job_timeout_for(action, size_bytes=None):
    """Return the RQ ``job_timeout`` (seconds) for a storage ``action``.

    ``action`` is the task function name (``"download_url"``, ``"convert"``,
    ``"create"``, the ``core.*`` finalize names, ...). ``size_bytes`` is the
    disk/file size when the caller knows it, used to scale long-running
    budgets. Fast/unknown actions get :data:`FAST_TIMEOUT`; long actions get a
    size-derived budget clamped to ``[LONG_FLOOR, LONG_CEIL]`` (or ``LONG_CEIL``
    when the size is unknown).
    """
    if action not in LONG_ACTIONS:
        return FAST_TIMEOUT
    if size_bytes and size_bytes > 0:
        budget = int(size_bytes // MIN_THROUGHPUT_BPS)
        return max(LONG_FLOOR, min(LONG_CEIL, budget))
    return LONG_CEIL
