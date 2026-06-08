"""Shared vGPU reconcile policy + profile-suffix canonicalization.

Pure, dependency-free (stdlib only) so it is importable from the engine
(``isardvdi_common.gpu_pool_policy``), the API (same), and the hypervisor
container (loaded from ``/src/_common`` via SourceFileLoader). It carries the
ONE copy of:

  * the profile-suffix canonicalization (MIG dash-form ``"1-2Q"`` ->
    underscore-form ``"1_2Q"`` so a booking/planner suffix compares equal to the
    driver/discovery key), and
  * ``decide_reconcile_action`` -- the single policy that resolves, for one GPU,
    which profile should be applied (scheduled booking > operator intent >
    passthrough default) and whether it is realizable on the current hardware.

Both the engine reconcile and the API's registration-time target computation use
this same function so they cannot diverge.
"""

import re

# MIG dash-form ("1-2Q") -> underscore-form ("1_2Q"); dot-form ("1g.24gb"),
# plain vGPU suffixes ("4Q", "1C") and "passthrough" are left untouched.
# Idempotent.
_MIG_DASH_RE = re.compile(r"^(\d+)-(\d+[A-Za-z].*)$")


def canonical_suffix(suffix):
    """Canonicalize a profile suffix for comparison. Idempotent; non-str passes
    through unchanged."""
    if not isinstance(suffix, str):
        return suffix
    s = suffix.strip()
    m = _MIG_DASH_RE.match(s)
    if m:
        return f"{m.group(1)}_{m.group(2)}"
    return s


def split_qualifier(reservable_id):
    """Split an optional ``@<name>`` variant qualifier off a reservable id.

    Admins may differentiate otherwise-identical brand-model-profile cards by
    appending ``@<name>`` (e.g. ``NVIDIA-L40S-8Q@lab``). ``@`` is forbidden in
    profile suffixes, so a single right-split is unambiguous. Returns
    ``(base_id, name_or_None)``."""
    if not isinstance(reservable_id, str) or "@" not in reservable_id:
        return reservable_id, None
    base, name = reservable_id.rsplit("@", 1)
    return base, (name or None)


def canonical_profile_id(reservable_id):
    """Canonicalize a ``NVIDIA-<model>-<suffix>[@<name>]`` id by canonicalizing
    only its suffix, preserving any ``@<name>`` variant qualifier. Model tokens
    are dash-free by construction, so the first two hyphens delimit brand/model
    and everything after (up to an optional ``@``) is the (possibly dash-bearing
    MIG) suffix."""
    if not isinstance(reservable_id, str):
        return reservable_id
    base, name = split_qualifier(reservable_id)
    parts = base.split("-", 2)
    if len(parts) == 3:
        base = f"{parts[0]}-{parts[1]}-{canonical_suffix(parts[2])}"
    return base if name is None else f"{base}@{name}"


def profile_suffix_from_id(reservable_id):
    """Reduce a profile id to its canonical bare suffix, dropping any ``@<name>``
    variant qualifier. Accepts either a full ``NVIDIA-<model>-<suffix>[@<name>]``
    catalog id (the scheduler) or an already-bare suffix (the webapp force
    button). Canonicalizes BEFORE reducing, so a dash-form MIG id
    (``NVIDIA-<model>-1-2Q``) yields ``"1_2Q"`` instead of a mis-split ``"2Q"``;
    a bare dash-form suffix is canonicalized too. The bare suffix is what matches
    a host's ``vgpus.info.types`` keys. Non-str / falsy passes through."""
    if not isinstance(reservable_id, str):
        return reservable_id
    base, _ = split_qualifier(reservable_id)
    cid = canonical_profile_id(base)
    parts = cid.split("-", 2)
    return canonical_suffix(parts[2] if len(parts) == 3 else cid)


def decide_reconcile_action(
    requested_profile,
    scheduled_profile,
    available_types,
    sriov_totalvfs,
    operator_passthrough,
    fallback_default,
    keep_current=False,
):
    """Decide what reconcile should do for a single GPU.

    Pure decision logic so the policy is unit-testable without a hypervisor
    object, a RethinkDB connection, or libvirt. The caller executes the chosen
    action.

    Inputs
    ------
    requested_profile : str | None
        Operator-set profile from ``vgpus.requested_profile`` (the durable
        intent — webui/API is the only writer).
    scheduled_profile : str | None
        Booking-system override from the resource planner (None when no active
        booking).
    available_types : dict
        Profiles surfaced by current discovery (``info_nvidia[pci]["types"]`` /
        the registration payload). Keys are profile suffixes like ``"2Q"``,
        ``"4Q"``, ``"1g.24gb"``, ``"passthrough"``.
    sriov_totalvfs : int
        Non-zero means SR-IOV-capable card; empty ``available_types`` is then
        almost always a discovery race, not a real "no profiles" state.
    operator_passthrough : bool
        ``vgpus.operator_passthrough``; gates reconcile-driven vfio-pci rebinds.
    fallback_default : str | None
        Default to seed on a fresh GPU with no prior intent. Callers pass
        ``"passthrough"`` for an unconfigured card (whole GPU; needs no mdev
        types), so a new/rebooted card with no planning stays usable instead of
        being auto-carved into the max vGPU profile.
    keep_current : bool
        When True (registration with a real LIVE carve as ``fallback_default``)
        the no-intent fallback emits ``keep_current`` instead of
        ``seed_and_apply``: apply the live profile but do NOT write
        ``requested_profile``, so keeping the card's current carve stays
        EPHEMERAL (a card left in some profile by an expired booking is not
        turned into durable operator intent). Default False preserves the
        seed-on-first-discovery behaviour the engine reconcile relies on. NOTE:
        this controls the POLICY decision only -- the registration apply-report
        ingest (``vgpu_state.build_applied_state_patch``) still seeds
        ``requested_profile`` from the applied profile when it was unset, so the
        persisted row is not guaranteed unseeded. The kept profile is identical
        either way (the engine reconcile's fallback is the live ``vgpu_profile``),
        so "ephemeral" describes the decision, not the row.

    Returns
    -------
    dict with key ``action`` plus action-specific fields:

      * ``{"action": "skip_retry", ...}``  discovery incomplete (sentinel-empty
        types on an SR-IOV PF); preserve DB, retry later.
      * ``{"action": "skip_fault", ...}``  requested profile genuinely
        unavailable on this hardware; surface a fault and skip, never mutate.
      * ``{"action": "refuse_passthrough", ...}``  effective resolved to
        passthrough but ``operator_passthrough`` is False AND it is not a
        planning-scheduled passthrough — refuse, skip. A passthrough scheduled
        by the planning calendar (``scheduled_profile == "passthrough"``) is
        authoritative and returns ``apply`` instead.
      * ``{"action": "apply", "profile": ...}``  valid; apply.
      * ``{"action": "seed_and_apply", "profile": ...}``  first-ever discovery
        with no operator intent yet — caller writes ``requested_profile`` (and
        ``operator_passthrough`` if passthrough) BEFORE applying.
      * ``{"action": "keep_current", "profile": ...}``  apply the live/kept
        profile WITHOUT writing ``requested_profile`` — ephemeral, non-sticky
        (only when ``keep_current`` is set and the fallback is the live carve).
      * ``{"action": "skip_noop", ...}``  nothing to do.

    Both ``effective`` and the ``available_types`` keys are canonicalized before
    the realizability test so a dash-form MIG suffix (``"1-2Q"``) is not
    misclassified ``skip_fault`` against an underscore-form driver key
    (``"1_2Q"``).
    """
    effective = scheduled_profile or requested_profile
    available_types = available_types or {}
    only_passthrough = not available_types or list(available_types.keys()) == [
        "passthrough"
    ]
    canon_available = {canonical_suffix(k) for k in available_types}
    effective_canon = canonical_suffix(effective) if effective else effective

    if effective and effective_canon not in canon_available:
        if only_passthrough and sriov_totalvfs > 0:
            return {
                "action": "skip_retry",
                "reason": "discovery_incomplete",
                "profile": effective,
            }
        return {
            "action": "skip_fault",
            "reason": "requested_profile_unavailable",
            "profile": effective,
        }

    if not effective:
        if not fallback_default:
            return {
                "action": "skip_noop",
                "reason": "no_profile_resolvable",
            }
        if requested_profile is None:
            if keep_current:
                # Keep the live carve but do NOT seed durable intent — ephemeral
                # so an incidental profile never becomes sticky operator intent.
                return {"action": "keep_current", "profile": fallback_default}
            # Seed operator intent so next cycle stops re-deriving the default.
            return {"action": "seed_and_apply", "profile": fallback_default}
        # requested_profile was set but resolved to None somehow — degenerate;
        # treat as apply.
        return {"action": "apply", "profile": fallback_default}

    if (
        effective == "passthrough"
        and not operator_passthrough
        and scheduled_profile != "passthrough"
    ):
        # A reconcile-driven vfio-pci rebind (destructive: tears down SR-IOV) is
        # refused unless the operator opted in -- BUT a passthrough that the
        # planning calendar schedules for this card IS that opt-in (the booking
        # planner is authoritative for what a card runs now). So refuse only a
        # passthrough coming from requested_profile/fallback without a scheduled
        # plan; a scheduled passthrough falls through to "apply".
        return {
            "action": "refuse_passthrough",
            "reason": "operator_passthrough_not_set",
        }

    return {"action": "apply", "profile": effective}
