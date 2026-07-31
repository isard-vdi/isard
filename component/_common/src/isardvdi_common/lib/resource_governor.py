"""Phase-1 resource governor for heavy background tasks.

Heavy background work (convert / sparsify / disconnect / downloads) is long and
high CPU+IO+RAM. Running it whenever an elastic worker is idle lets it fire
during a peak and steal CPU/IO/RAM from interactive/bulk via contention — which
the simulation showed keeps interactive latency high even with a dedicated
reserved pool. The governor gates admission of a background task so it runs in
low-load windows and never overloads the node:

* **defer under pressure** — if the kernel reports CPU, IO or MEMORY Pressure
  Stall Information (PSI ``some avg10``) above a threshold, the system is busy;
  hold the heavy task and let the elastic worker do lighter/overflow work
  instead. Memory pressure matters because qemu-img convert / virt-sparsify
  buffer whole-disk streams — several at once can exhaust RAM and drive the node
  into reclaim/swap even while CPU and IO still look calm.
* **cap heavy concurrency** — never run more than ``max_heavy`` heavy tasks at
  once (a resource-footprint cap), so heavy work alone can't oversubscribe the
  node. In a low-load trough PSI is low and the cap admits several in parallel
  to drain the backlog fast.

Guaranteed minimum progress does NOT come from this gate (which can defer to
zero): it comes from the separate bg-floor worker in docker/storage/init.sh
(ungoverned) that always runs >=1 heavy task. So a permanently-busy foreground
slows the backlog but never starves it.

Design: docs/superpowers/specs/2026-07-01-queue-worker-dimensioning-design.md
§3.3 (background floor) and §5.7 (resource governor).

Pure logic; the only side effect is reading ``/proc/pressure/*`` in the helper.
"""

import math

CPU_PRESSURE_PATH = "/proc/pressure/cpu"
IO_PRESSURE_PATH = "/proc/pressure/io"
MEMORY_PRESSURE_PATH = "/proc/pressure/memory"


def parse_psi_some_avg10(text):
    """Return the ``some avg10`` value from a /proc/pressure/{cpu,io} blob.

    Returns 0.0 when the input is empty/None or has no ``some`` line (e.g. a
    kernel built without PSI) — i.e. "no measurable pressure".
    """
    if not text:
        return 0.0
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("some "):
            continue
        for token in line.split():
            if token.startswith("avg10="):
                try:
                    return float(token.split("=", 1)[1])
                except ValueError:
                    return 0.0
    return 0.0


def read_pressure(path):
    """Best-effort read of a PSI file -> ``some avg10`` float (0.0 if absent)."""
    try:
        with open(path, "r") as fh:
            return parse_psi_some_avg10(fh.read())
    except OSError:
        return 0.0


def should_defer_heavy(
    cpu_psi, io_psi, running_heavy, psi_limit, max_heavy, mem_psi=0.0
):
    """Decide whether to DEFER admitting a heavy background task.

    :param cpu_psi: CPU PSI ``some avg10`` (percent stalled over 10s).
    :param io_psi: IO PSI ``some avg10``.
    :param running_heavy: heavy tasks currently running across the pool.
    :param psi_limit: defer while any PSI exceeds this (percent).
    :param max_heavy: hard cap on concurrent heavy tasks (footprint cap).
    :param mem_psi: MEMORY PSI ``some avg10`` (defaults to 0.0 so callers on a
        kernel without memory PSI — or that don't pass it — keep the prior
        CPU/IO-only behaviour).
    :return: ``True`` to defer (hold the task), ``False`` to admit now.
    """
    if running_heavy >= max_heavy:
        return True
    # A non-finite PSI value (``nan`` from a garbage /proc read) must DEFER, not
    # admit: ``nan > limit`` is False, so without this a corrupt reading would
    # silently let heavy work through. ``inf`` is also non-finite and correctly
    # defers.
    for psi in (cpu_psi, io_psi, mem_psi):
        if not math.isfinite(psi) or psi > psi_limit:
            return True
    return False
