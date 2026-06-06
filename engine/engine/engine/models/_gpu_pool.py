"""Pure helpers for sizing GPU vGPU/MIG mdev pools.

Kept in a dependency-free leaf module so it can be unit-tested without
importing :mod:`engine.models.hyp` (which imports ``libvirt`` at module
scope and is not importable in the lint/test environment).

``decide_reconcile_action`` now lives in
:mod:`isardvdi_common.gpu_pool_policy` (shared with the API so the policy
cannot diverge); it is re-exported here so existing engine imports keep
working. This module retains only the pool-sizing/trim helpers.
"""

from isardvdi_common.gpu_pool_policy import (  # noqa: F401  (re-exported)
    decide_reconcile_action,
)


def _profile_pool_size(d_type):
    """Realisable mdev pool size for a single GPU profile.

    The NVIDIA driver ``max`` (``max_instance``) is the hard cap of
    concurrently realisable mdevs for that profile on the PF.
    ``available`` (``available_instances`` / free SR-IOV VFs) counts a
    different axis and can legitimately exceed ``max`` on VF/SR-IOV
    boards; using it to grow the pool past ``max`` is the root cause of
    permanent "pool over-sized vs hardware" warnings and doomed UUIDs.

    Contract:
      * Use ``max`` when it is a known positive int.
      * Fall back to ``available`` only when ``max`` is missing / None
        / <= 0 (e.g. some A40 firmware reports ``max`` as None).
      * Never return less than 1 (a profile that exists has >= 1 slot;
        passthrough/MIG callers rely on this).

    Applies identically to vGPU and MIG profiles (both carry a
    per-profile driver ``max``). Passthrough does not call this (it is
    single-UUID by construction). Does not mutate ``d_type``.
    """
    max_instance = d_type.get("max")
    if isinstance(max_instance, bool):
        # bool is a subclass of int; treat True/False as "unset"
        max_instance = None
    if isinstance(max_instance, int) and max_instance > 0:
        return max_instance
    available = d_type.get("available", 1)
    try:
        available = int(available)
    except (TypeError, ValueError):
        available = 1
    return available if available > 0 else 1


def _mdev_is_free(entry):
    """An mdev pool entry is FREE (safe to drop) only if it is not
    created on the host and not bound/reserved to any domain.

    ``domain_started``/``domain_reserved`` are ``False`` when unbound or
    a domain-id string when bound; ``created`` is ``True`` once the host
    realised the mdev. Treat anything other than the unbound sentinels
    as in-use (conservative).
    """
    if not isinstance(entry, dict):
        return False
    return (
        entry.get("created") in (False, None)
        and entry.get("domain_started") in (False, None)
        and entry.get("domain_reserved") in (False, None)
    )


def plan_pool_trim(pool, cap, bound_uuids=frozenset()):
    """Plan a FREE-only down-trim of one profile's mdev pool to ``cap``.

    Returns ``(kept, removed)`` where ``kept`` is the new ``{uuid: entry}``
    map and ``removed`` is the list of dropped UUIDs, or ``None`` when no
    safe action applies (pool already within cap, unknown cap, or too
    many in-use entries to reach cap without touching a bound mdev —
    the "needs review" case, left intact).

    An entry is in-use (never removed) if it fails :func:`_mdev_is_free`
    OR its UUID is in ``bound_uuids`` (referenced by some domain's
    ``vgpu_info`` — the pool flags can lag a Stopped/reserved domain).
    Deterministic (sorted UUIDs) so repeated runs are idempotent.
    """
    if not isinstance(cap, int) or cap < 1:
        return None
    if not isinstance(pool, dict) or len(pool) <= cap:
        return None
    in_use = {u: e for u, e in pool.items() if not _mdev_is_free(e) or u in bound_uuids}
    if len(in_use) >= cap:
        return None
    free_sorted = sorted(u for u in pool if u not in in_use)
    kept = dict(in_use)
    for u in free_sorted[: cap - len(in_use)]:
        kept[u] = pool[u]
    removed = [u for u in pool if u not in kept]
    if not removed:
        return None
    return kept, removed


def plan_passthrough_dedup(pool, bound_uuids=frozenset()):
    """Plan dedup of a passthrough pool to a single canonical entry.

    A passthrough card maps to exactly one assignable device, but the
    legacy lazy-seed vs authoritative-rebuild paths could persist
    duplicate entries differing only by ``pci_mdev_id`` format
    (``pci_0000_63_00_0`` vs ``0000:63:00.0``). Keep one canonical
    (``0000:..`` sysfs form preferred) entry, drop the rest.

    Returns ``(kept, removed)`` or ``None`` when nothing to do or unsafe
    (<=1 entry, or any entry bound/reserved to a domain — by pool flag
    or by ``bound_uuids`` cross-check).
    """
    if not isinstance(pool, dict) or len(pool) <= 1:
        return None
    for uid, e in pool.items():
        if not isinstance(e, dict):
            return None
        if uid in bound_uuids or not (
            e.get("domain_started") in (False, None)
            and e.get("domain_reserved") in (False, None)
        ):
            return None
    canonical = sorted(
        u for u, e in pool.items() if str(e.get("pci_mdev_id", "")).startswith("0000:")
    )
    chosen = canonical[0] if canonical else sorted(pool)[0]
    removed = [u for u in pool if u != chosen]
    return {chosen: pool[chosen]}, removed
