"""Pure decision logic for reconciling the vGPU profile catalog against what
the hardware can actually realize.

Dependency-free leaf module (only the stdlib) so the SAFETY-CRITICAL removal
gate is fully unit-testable without booting Flask, a RethinkDB connection, or
an app context. The orchestration that reads the DB and executes the SUPPORTED
Reservables/Planner/Bookings calls lives in :mod:`api_hypervisors`; this module
only DECIDES what is eligible for removal.

Design invariants (the whole point of this module):

  * Removal is ASYMMETRIC. Re-adding a profile that became realizable again is
    cheap and already handled by ``ensure_gpu_profiles``; REMOVING a profile is
    destructive (it can tear down reservables/plannings/bookings), so a profile
    is pruned ONLY when a healthy, settled, trustworthy hypervisor reading
    POSITIVELY confirms the card cannot realize it. Anything ambiguous (a
    failed/incomplete/degraded discovery) -> PRESERVE.

  * The removal primitive is PER PHYSICAL CARD, PER SERVER. Every ``gpus`` /
    ``vgpus`` row is exactly one physical card on one hypervisor and carries its
    own realizable type set (``vgpus.info.types`` / the registration payload's
    ``vgpu_profiles``). A card's enabled profile is pruned only against THAT
    card's own verified reading -- never an install-wide aggregate.

  * The model-level ``reservables_vgpus`` / ``gpu_profiles`` row is NEVER deleted
    by a model-wide predicate. It collapses only as the cascade of the LAST card
    dropping the profile (``enable_subitem`` -> last-card ->
    ``delete_reservable_vgpu``), i.e. only when NO card in the whole install can
    realize it. Because we disable a card's profile only on a fresh trustworthy
    reading, the reservable survives as long as ANY card is unverified or still
    realizes it -- which is exactly "remove only if no other card in the
    infrastructure can handle that brand-model-profile".
"""

import re

# MIG dash-form ("1-2Q") -> underscore-form ("1_2Q") so a legacy dash-form
# reservable id suffix compares equal to the engine's info.types key, which is
# always ``name.split("-", 1)[1]``. Dot-form ("1g.24gb"), plain vGPU suffixes
# ("4Q", "1C") and "passthrough" are left untouched. Mirrors the v189 migration
# canonicalization; idempotent. NOTE: the canonical home of this logic is
# isardvdi_common.gpu_pool_policy (used by the engine reconcile + API target
# computation); kept duplicated here only so this module stays importable
# without isardvdi_common on the path (the prune unit tests run it directly).
# Keep the two in sync.
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
    are dash-free by construction (see ``canonical_gpu_model``), so the first two
    hyphens delimit brand/model and everything after (up to an optional ``@``) is
    the (possibly dash-bearing MIG) suffix."""
    if not isinstance(reservable_id, str):
        return reservable_id
    base, name = split_qualifier(reservable_id)
    parts = base.split("-", 2)
    if len(parts) == 3:
        base = f"{parts[0]}-{parts[1]}-{canonical_suffix(parts[2])}"
    return base if name is None else f"{base}@{name}"


def bare_suffix(reservable_id):
    """The canonical profile SUFFIX of a reservable id with any ``@<name>``
    qualifier stripped, for matching against a host's ``vgpus.info.types`` keys
    (which are bare suffixes like ``8Q`` / ``1g.24gb``). Returns the input
    unchanged when it is not a 3-part ``brand-model-suffix`` id."""
    if not isinstance(reservable_id, str):
        return reservable_id
    base, _ = split_qualifier(reservable_id)
    parts = base.split("-", 2)
    return canonical_suffix(parts[2]) if len(parts) == 3 else base


def realizable_suffixes(gpu_payload):
    """The set of profile SUFFIXES a single card's CURRENT discovery proves
    realizable, or ``None`` when the reading must NOT drive a removal.

    ``gpu_payload`` is one entry of the hypervisor's ``nvidia_gpus`` POST:

      * ``vgpu_profiles is None`` -> the DISCOVERY_FAILED sentinel (the engine
        deliberately retains the prior ``info`` on failure); return ``None`` so
        nothing is pruned from a failed cycle.
      * ``vgpu_profiles`` is a list (possibly empty) -> a real reading. Each
        entry is ``{"name": "<model>-<suffix>", ...}``; the suffix is
        ``name.split("-", 1)[1]``.
      * ``mig_profiles`` entries contribute their bare ``name`` as suffix.
      * ``passthrough`` is always realizable on a real reading (whole-GPU; needs
        no mdev type).
    """
    if gpu_payload.get("vgpu_profiles") is None:
        return None
    out = {"passthrough"}
    for prof in gpu_payload.get("vgpu_profiles") or []:
        name = prof.get("name")
        if isinstance(name, str) and "-" in name:
            out.add(canonical_suffix(name.split("-", 1)[1]))
    for mig in gpu_payload.get("mig_profiles") or []:
        name = mig.get("name")
        if isinstance(name, str):
            out.add(canonical_suffix(name))
    return out


def reading_trustworthy(gpu_payload, sriov_totalvfs):
    """Whether a card's CURRENT reading is trustworthy enough to DRIVE removal
    of that card's profiles. Fail-closed: any doubt -> ``False``.

    All gates must hold:

      * Discovery succeeded -- ``vgpu_profiles`` is not the ``None`` sentinel.
      * Not the SR-IOV "discovery-incomplete" / vgpud-down signature: an
        SR-IOV-capable card (``sriov_totalvfs > 0``) reporting ONLY passthrough
        (no vGPU and no MIG types) this cycle is almost always a transient or
        degraded read (half-initialized VFs, the host vGPU manager not yet
        publishing types), NOT a genuine "this card has no vGPU types". A card
        that is truly passthrough-only is non-SR-IOV (``sriov_totalvfs == 0``)
        and is correctly trusted.

    The settled-VF guarantee (``nvidia-*`` not the transient ``pci-*`` mdev type
    dir names) is enforced UPSTREAM by discovery, which builds ``vgpu_profiles``
    from the type ``name`` files only after the VF cycle settles -- so a
    trustworthy ``vgpu_profiles`` list already reflects settled names.
    """
    suffixes = realizable_suffixes(gpu_payload)
    if suffixes is None:
        return False
    try:
        sriov = int(sriov_totalvfs or 0)
    except (TypeError, ValueError):
        sriov = 0
    if not (suffixes - {"passthrough"}) and sriov > 0:
        return False
    return True


def realizable_profile_ids(model, gpu_payload):
    """Full reservable/profile ids a card's reading proves realizable
    (``{"NVIDIA-<model>-<suffix>", ...}``), or ``None`` if not trustworthy.
    Ids are canonical and match ``reservables_vgpus.id`` / the nested
    ``gpu_profiles`` ids / ``gpus.profiles_enabled`` entries."""
    suffixes = realizable_suffixes(gpu_payload)
    if suffixes is None:
        return None
    return {f"NVIDIA-{model}-{s}" for s in suffixes}


def plan_card_prunes(model, cards):
    """Decide, per card, which enabled reservable ids to DISABLE on that card.

    ``cards`` is a list of dicts::

        {"id": <gpus row id>,
         "profiles_enabled": [<reservable id>, ...],
         "gpu_payload": <this registration's reading for the card, or None>,
         "sriov_totalvfs": <int, from the card's persisted vgpus.info>}

    A card is pruned ONLY when:
      * it was read THIS cycle (``gpu_payload`` is not ``None``), and
      * that reading is trustworthy (:func:`reading_trustworthy`), and
      * an enabled id of THIS model is absent from the card's own realizable set.

    Returns a deterministic sorted list of ``(card_id, reservable_id)`` to
    disable via the supported ``Reservables.enable_subitems(..., False)`` path.
    Cards not read this cycle, or with an ambiguous reading, are left untouched
    -- which is what keeps the model-level reservable alive until EVERY card has
    a fresh trustworthy reading that drops the profile.
    """
    prefix = f"NVIDIA-{model}-"
    prunes = set()
    for card in cards:
        payload = card.get("gpu_payload")
        if payload is None:
            continue
        if not reading_trustworthy(payload, card.get("sriov_totalvfs")):
            continue
        realizable = {
            canonical_profile_id(i) for i in realizable_profile_ids(model, payload)
        }
        for enabled_id in card.get("profiles_enabled") or []:
            if not isinstance(enabled_id, str) or not enabled_id.startswith(prefix):
                continue
            if canonical_profile_id(enabled_id) not in realizable:
                prunes.add((card["id"], enabled_id))
    return sorted(prunes)
