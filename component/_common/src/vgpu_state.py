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
