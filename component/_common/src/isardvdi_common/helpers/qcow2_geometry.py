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
# Mirrors the ${QCOW2_*:-...} defaults in docker-compose-parts/apiv4.yml, which is the reference.
_DEFAULTS = {
    "cluster_size": "128k",
    "extended_l2": "on",
    "lazy_refcounts": "off",
    "preallocation": "off",
}
_ON_OFF = ("on", "off")
_PREALLOCATION = ("off", "metadata", "falloc", "full")

# qemu-img only accepts a power-of-two cluster between 512 and 2M.
_MIN_CLUSTER = 512
_MAX_CLUSTER = 2 * 1024 * 1024
# extended_l2 splits a cluster into 32 subclusters of >=512 bytes, so it needs >=16k.
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
    cluster = parse_cluster_size(geometry["cluster_size"])
    if (
        cluster < _MIN_CLUSTER
        or cluster > _MAX_CLUSTER
        or (cluster & (cluster - 1)) != 0
    ):
        raise Qcow2PolicyError(
            f"QCOW2_CLUSTER_SIZE={geometry['cluster_size']} is not a valid qcow2 "
            "cluster size: it must be a power of two between 512 and 2M"
        )
    if geometry["extended_l2"] == "on" and cluster < _EXTENDED_L2_MIN_CLUSTER:
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


def env_sources(environ=None):
    """Report where each key's value came from: ``"env"`` when the process set
    the var, ``"default"`` when it fell back. A policy whose four keys are all
    ``"default"`` on the enqueuer is the distributed-install trap -- the vars may
    have been set on a different node -- so the caller can warn about it."""
    env = os.environ if environ is None else environ
    return {k: ("env" if (env.get(_ENV[k]) or "") != "" else "default") for k in KEYS}


_cached = None


def policy():
    """Memoised per process. Lazy on purpose: engine/scheduler/change-handler
    import models.storage but never enqueue a disk-writing task, and must not
    crash at import because they do not carry the vars."""
    global _cached
    if _cached is None:
        _cached = from_env()
    return _cached


def create_options(geometry, has_backing_file, with_preallocation=None):
    """The qemu-img ``-o`` string for this ``geometry``.

    ``with_preallocation`` overrides whether the ``preallocation=`` term is
    appended. Left ``None`` it is derived: preallocation applies when there is no
    backing file, or when extended_l2 is on (subcluster allocation bits make it
    meaningful with one). A caller sets it ``False`` explicitly when qemu-img
    would reject preallocation regardless -- e.g. ``convert -c``, which refuses
    any preallocation other than off.
    """
    validate(geometry)
    options = (
        f"cluster_size={geometry['cluster_size']},"
        f"extended_l2={geometry['extended_l2']},"
        f"lazy_refcounts={geometry['lazy_refcounts']}"
    )
    if with_preallocation is None:
        with_preallocation = not has_backing_file or geometry["extended_l2"] == "on"
    if with_preallocation:
        options += f",preallocation={geometry['preallocation']}"
    return options
