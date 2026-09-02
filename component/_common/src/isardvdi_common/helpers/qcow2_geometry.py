#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Installation-wide qcow2 geometry.

Resolved ONCE by the enqueuing process from its own environment, carried
inside the task payload, applied verbatim by whichever storage worker
dequeues the job. The worker never reads the environment for this: the
same logical action must produce the same disk shape on every host.

Keep this module ``os``-only. It is imported by the storage worker
(``docker/storage/task/task.py``), which runs on nodes with no database;
pulling in ``rethinkdb`` or ``isardvdi_common.models.*`` here would break
``docker/storage/task/tests/test_no_database_from_the_worker.py``.
"""

import os

KEYS = ("cluster_size", "extended_l2", "lazy_refcounts", "preallocation")

_ENV = {
    "cluster_size": "QCOW2_CLUSTER_SIZE",
    "extended_l2": "QCOW2_EXTENDED_L2",
    "lazy_refcounts": "QCOW2_LAZY_REFCOUNTS",
    "preallocation": "QCOW2_PREALLOCATION",
}
# The documented install defaults (isardvdi.cfg.example).
# These belong on the ENQUEUE side only: docker-compose passes the four
# vars bare (``QCOW2_CLUSTER_SIZE:``), so an install that never set them in
# its cfg has them ABSENT from the container env, not empty.
_DEFAULTS = {
    "cluster_size": "4k",
    "extended_l2": "off",
    "lazy_refcounts": "off",
    "preallocation": "off",
}
_ON_OFF = ("on", "off")
_PREALLOCATION = ("off", "metadata", "falloc", "full")

# extended_l2 subclusters need a >=16k cluster (a cluster is split into 32
# subclusters, each of which must be at least 512 bytes).
_EXTENDED_L2_MIN_CLUSTER = 16384


class Qcow2PolicyError(ValueError):
    """The install's qcow2 policy is not a policy qemu-img can honour."""


def parse_cluster_size(value):
    """``'128k'`` -> ``131072``. Moved verbatim from the worker."""
    s = str(value).upper().strip()
    multipliers = {"K": 1024, "M": 1024**2}
    digits = "".join(c for c in s if c.isdigit())
    unit = "".join(c for c in s if c.isalpha())
    if not digits:
        raise Qcow2PolicyError(f"QCOW2_CLUSTER_SIZE={value!r} is not a size")
    return int(digits) * multipliers.get(unit, 1)


def validate(geometry):
    """Raise :class:`Qcow2PolicyError` unless ``geometry`` is a policy
    qemu-img can honour. Returns the same mapping on success."""
    missing = [k for k in KEYS if geometry.get(k) in (None, "")]
    if missing:
        raise Qcow2PolicyError(f"qcow2 geometry is missing {missing}")
    if geometry["extended_l2"] not in _ON_OFF:
        raise Qcow2PolicyError(
            f"QCOW2_EXTENDED_L2={geometry['extended_l2']!r} must be one of {_ON_OFF}"
        )
    if geometry["lazy_refcounts"] not in _ON_OFF:
        raise Qcow2PolicyError(
            f"QCOW2_LAZY_REFCOUNTS={geometry['lazy_refcounts']!r} must be one of "
            f"{_ON_OFF}"
        )
    if geometry["preallocation"] not in _PREALLOCATION:
        raise Qcow2PolicyError(
            f"QCOW2_PREALLOCATION={geometry['preallocation']!r} must be one of "
            f"{_PREALLOCATION}"
        )
    if (
        geometry["extended_l2"] == "on"
        and parse_cluster_size(geometry["cluster_size"]) < _EXTENDED_L2_MIN_CLUSTER
    ):
        raise Qcow2PolicyError(
            f"QCOW2_CLUSTER_SIZE={geometry['cluster_size']} is too small for "
            "extended_l2=on (minimum 16k). Either set QCOW2_CLUSTER_SIZE>=16k "
            "or QCOW2_EXTENDED_L2=off"
        )
    return geometry


def from_env(environ=None):
    """Resolve the policy from ``environ`` (defaults to ``os.environ``),
    filling absent/empty vars with the documented install defaults."""
    env = os.environ if environ is None else environ
    return validate({k: env.get(_ENV[k]) or _DEFAULTS[k] for k in KEYS})


_cached = None


def policy():
    """Memoised per process. Lazy on purpose: engine/scheduler/change-handler
    import models.storage but never enqueue a disk-writing task, and must not
    crash at import because they do not carry the vars."""
    global _cached
    if _cached is None:
        _cached = from_env()
    return _cached


def create_options(geometry, has_backing_file):
    """The qemu-img ``-o`` string for this ``geometry``. Moved from the worker."""
    validate(geometry)
    options = (
        f"cluster_size={geometry['cluster_size']},"
        f"extended_l2={geometry['extended_l2']},"
        f"lazy_refcounts={geometry['lazy_refcounts']}"
    )
    # Preallocation applies when there is no backing file, or when extended_l2
    # is on (subcluster allocation bits make it meaningful with one).
    if not has_backing_file or geometry["extended_l2"] == "on":
        options += f",preallocation={geometry['preallocation']}"
    return options
