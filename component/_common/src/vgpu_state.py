"""Shared logic for persisting a GPU card's APPLIED profile state into the
``vgpus`` row, so the API (when it ingests the hypervisor's applied-state
report) and the engine write byte-identical rows.

Pure: :func:`build_applied_state_patch` computes the update dict; the caller
applies it with its own RethinkDB connection. This is where the engine
"no-fight" guarantee lives -- see the ``mdevs_last_synced_at`` note below.
"""


def build_applied_state_patch(existing, applied_profile, mdevs, mdevs_reset_at):
    """Fields to write to a ``vgpus`` row after the hypervisor applied a profile.

    Parameters
    ----------
    existing : dict | None
        The current ``vgpus`` row (``{}``/``None`` if it does not exist yet).
    applied_profile : str
        The profile suffix the hypervisor actually applied (e.g. ``"4Q"``,
        ``"passthrough"``, a MIG suffix).
    mdevs : dict | None
        The mdev pool the hypervisor created, shaped
        ``{profile: {uuid: entry}}`` (engine schema). The host is authoritative
        now, so this REPLACES ``vgpus.mdevs`` (after a profile switch the other
        profiles have no live mdevs).
    mdevs_reset_at
        The ``mdevs_reset_at`` timestamp discovery stamped on this card.

    Returns
    -------
    dict
        The update patch. Notable fields:

        * ``vgpu_profile`` = applied_profile -- the engine reconcile reads this
          as the card's CURRENT profile, so setting it makes
          ``effective == current`` and the engine confirms instead of
          re-applying.
        * ``mdevs_last_synced_at`` = ``mdevs_reset_at`` -- THE no-fight key:
          the engine rebuilds the pool authoritatively only when
          ``mdevs_reset_at > mdevs_last_synced_at``; equal timestamps disable
          that rebuild for cards the hypervisor already populated.
        * ``requested_profile`` is SEEDED only when currently unset (mirrors the
          engine's ``seed_and_apply``); never clobbers existing operator intent.
        * ``operator_passthrough`` is set True only for a first-time passthrough
          seed (so reconcile-driven passthrough rebinds stay gated).
        * ``changing_to_profile`` is cleared.
    """
    existing = existing or {}
    patch = {
        "vgpu_profile": applied_profile,
        "mdevs": mdevs or {},
        "changing_to_profile": False,
        # Records that the hypervisor self-applied this card at registration
        # (observability; the no-fight guarantee itself rides on
        # mdevs_last_synced_at below).
        "applied_by_hypervisor": True,
    }
    if mdevs_reset_at is not None:
        patch["mdevs_last_synced_at"] = mdevs_reset_at
    if existing.get("requested_profile") is None:
        patch["requested_profile"] = applied_profile
        if applied_profile == "passthrough":
            patch["operator_passthrough"] = True
    return patch


def reconcile_pool_to_live(db_mdevs, live_mdevs, running_uuids):
    """Rebuild ``vgpus.mdevs`` to match the host's LIVE pool (reality wins) while
    NEVER stopping a running desktop. Shared by the API ingest and the engine
    force-CLI path so both reconcile identically.

    ``live_mdevs`` is the host-reported ``{suffix: {uuid: free_entry}}`` carried on
    a ``noop``/``skipped_busy`` report -- the authoritative set of UUIDs that
    actually exist on the card. DB UUIDs absent from the host are dropped (gone);
    brand-new live UUIDs are added free. This re-pins the DB to reality when the
    live UUIDs drifted (a re-carve, or a hypervisor-container recreate that minted
    a fresh set) without ever handing QEMU a phantom UUID.

    ``running_uuids`` is the set of mdev UUIDs a desktop is ACTUALLY running on
    right now (the hypervisor's live ``virsh`` view, carried on the report as
    ``running_mdev_uuids``). The two DB bindings are treated differently because
    they mean different things:

    * ``domain_started`` is a desktop with a LIVE qemu. It is re-adopted ONLY when
      its UUID is in ``running_uuids`` -- so a *stale* started flag never
      re-asserts a desktop that is not running, and at hypervisor startup (where
      the entrypoint kills every leftover qemu before registration, so the set is
      empty) it is dropped: a clean slate, not a phantom reservation.
    * ``domain_reserved`` is a short-lived compare-and-swap LOCK taken just BEFORE
      a desktop's qemu is launched (so it is correctly NOT in the running set
      yet). It is preserved as-is -- dropping it would let two concurrent starters
      claim the same UUID, the exact conflict the reservation CAS prevents. (At
      hypervisor startup this branch is not reached: a clean card re-carves via
      the 'applied' path, which replaces the pool with a fresh, fully-free one.)

    Adoption of ``domain_started`` is therefore a pure RUNTIME concept (it can only
    keep a binding a live qemu backs). Returns the new ``mdevs`` dict (the caller
    writes it via ``r.literal`` so it REPLACES the pool wholesale)."""
    running = set(running_uuids or ())
    by_uuid = {}
    for entries in (db_mdevs or {}).values():
        if isinstance(entries, dict):
            for u, e in entries.items():
                if isinstance(e, dict):
                    by_uuid[u] = e
    out = {}
    for suffix, entries in (live_mdevs or {}).items():
        out[suffix] = {}
        for u, live_e in (entries or {}).items():
            old = by_uuid.get(u) or {}
            merged = dict(live_e)  # host entry: free by default
            if u in running and old.get("domain_started"):
                merged["domain_started"] = old["domain_started"]
            if old.get("domain_reserved"):
                merged["domain_reserved"] = old["domain_reserved"]
            out[suffix][u] = merged
    return out


def parse_apply_report(stdout):
    """Parse a ``gpu_apply_cli`` stdout line into the report dict, or ``None``
    when it is missing / blank / non-JSON / not a report object.

    The engine invokes ``gpu_apply_cli`` over SSH for a runtime profile change
    and falls back to its inline apply on ``None``. Kept here (shared,
    dependency-free) so the parse is unit-testable without the engine's libvirt
    imports.
    """
    import json

    if not stdout:
        return None
    try:
        report = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    if not isinstance(report, dict) or "result" not in report:
        return None
    return report
