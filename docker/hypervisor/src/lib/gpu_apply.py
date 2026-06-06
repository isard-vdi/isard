"""Apply a vGPU / MIG / passthrough profile to a physical GPU LOCALLY.

Runs inside the hypervisor container at registration time. The container already
has /sys, nvidia-smi, sriov-manage and (privileged) /dev/nvidia* + /dev/vfio, so
the host-command sequences the engine used to run over SSH can run here directly.
This module imports the SAME shared builders the engine uses
(``gpu_cmds`` / ``gpu_pool_policy`` from /src/_common) so the two paths cannot
drift; the engine keeps owning runtime (scheduler-driven) profile changes.

Design:
  * No libvirt at registration (libvirtd starts later in start.sh), so we never
    stop domains; instead we SKIP any card with a live VFIO consumer.
  * Per card: detect the current applied profile, compare to the API-provided
    target (planning -> current -> passthrough default), apply only if it
    differs, and return an applied-state report the caller POSTs back to the API.

The pure decision/command helpers (no subprocess, sysfs or imports of
gpu_discovery) are unit-tested in gpu_apply_test.py; the orchestration that
touches the host is validated on a GPU host.
"""

import os
import uuid as _uuid

import gpu_probe
from gpu_discovery import _get_vgpu_profiles, _vfio_group_in_use
from gpu_probe import (
    MIG_CURRENT,
    _enumerate_vf_sub_paths,
    _load_shared,
    _out,
    _read_driver,
    _read_mig_mode,
    canonical_suffix,
    current_profile_from_state,
    run_local,
)

# The read-only probe primitives (run_local, MIG_CURRENT,
# current_profile_from_state, the sysfs/nvidia-smi readers, _out) and the shared
# loader + canonical_suffix now live in gpu_probe -- the leaf both gpu_apply and
# gpu_discovery import, which breaks the old gpu_apply <-> gpu_discovery cycle.
# They are re-exported above so this module's public surface (and the test
# monkeypatch points ga._read_driver / ga.run_local / ...) is unchanged.
# gpu_cmds (host-command builders) is apply-only; load it via the same loader.
# _get_vgpu_profiles / _vfio_group_in_use are pure-read discovery helpers,
# imported at module level now (no cycle: gpu_discovery no longer imports us).
_cmds = _load_shared("gpu_cmds")


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested; no host access).
# --------------------------------------------------------------------------- #
def decide_apply_action(current_profile, target_profile, busy):
    """Decide noop / skipped_busy / apply for one card. ``target_profile`` None
    or empty is treated as the passthrough default."""
    target = target_profile or "passthrough"
    if current_profile == target:
        return "noop"
    if busy:
        return "skipped_busy"
    return "apply"


def build_mdev_create_cmd(base_path, type_id, mdev_uuid):
    """Command to instantiate one mdev of ``type_id`` under ``base_path``
    (the VF / PF path that exposes mdev_supported_types). Matches the engine's
    create form (single-quoted path)."""
    return f"echo {mdev_uuid} > '{base_path}/mdev_supported_types/{type_id}/create'"


def new_mdev_pool_entry(pci_mdev_id, type_id, mig=False, mig_profile_id=None):
    """Build one ``vgpus.mdevs[profile][uuid]`` entry (engine schema) plus a
    fresh UUID. Returned as ``(uuid, entry)``."""
    entry = {
        "pci_mdev_id": pci_mdev_id,
        "type_id": type_id,
        "created": True,
        "domain_started": False,
        "domain_reserved": False,
    }
    if mig:
        entry["mig"] = True
        entry["mig_profile_id"] = mig_profile_id
    return str(_uuid.uuid4()), entry


def target_suffix(target):
    """The bare, canonical profile suffix to apply from an API target dict
    ({"target_profile","action",...}); passthrough default if absent."""
    if not target:
        return "passthrough"
    return canonical_suffix(target.get("target_profile") or "passthrough")


def is_actionable(target):
    """Whether an API target is one the hypervisor should apply now. apply /
    seed_and_apply / keep_current (and a target with no explicit action) are
    applied; skip_retry / skip_fault / refuse_passthrough / skip_noop are
    advisory -> leave to the engine reconcile."""
    if not target:
        # No target for this card -> apply the passthrough default.
        return True
    return target.get("action") in (None, "apply", "seed_and_apply", "keep_current")


# --------------------------------------------------------------------------- #
# Host-touching helpers (validated on a GPU host). The low-level read-only
# probes (run_local, _read_driver, _read_mig_mode, _enumerate_vf_sub_paths, the
# parametrized _live_mdev_suffix) live in gpu_probe; these are the apply-side
# helpers that build on them + the discovery profile reader.
# --------------------------------------------------------------------------- #
def _live_profiles(pci_bdf):
    """Live mdev types currently exposed by this card, via the discovery helper
    (resolves the settled nvidia-* / transient pci-* dir names). Returns the
    list of {name,type_id,...} dicts or []. _get_vgpu_profiles is a module-level
    import now (no cycle: gpu_discovery no longer imports gpu_apply)."""
    return _get_vgpu_profiles(pci_bdf) or []


def _live_mdev_suffix(pci_bdf, run):
    """Suffix of a profile that currently has a live mdev created on the card,
    or None. Thin wrapper over gpu_probe._live_mdev_suffix, injecting this
    module's _live_profiles as the profile source (keeps the discovery reader
    out of the leaf, and the test's ga._live_profiles monkeypatch still
    applies)."""
    return gpu_probe._live_mdev_suffix(pci_bdf, run, _live_profiles)


def _resolve_type_id(pci_bdf, suffix, sub_paths=None):
    """Live mdev type_id (dir name) for a profile suffix on this card, or None.
    Matches by type NAME (robust to pci-* vs nvidia-* dir naming). On SR-IOV
    cards (A16/A40/L40/Blackwell) the mdev types live on the VFs, not the PF, so
    probe the VF sub_paths when given; falls back to the PF for T4-style cards
    that expose mdev_supported_types on the PF itself."""
    want = canonical_suffix(suffix)
    bdfs = [os.path.basename(p) for p in (sub_paths or [])] or [pci_bdf]
    for bdf in bdfs:
        for prof in _live_profiles(bdf):
            name = prof.get("name") or ""
            if "-" in name and canonical_suffix(name.split("-", 1)[1]) == want:
                return prof.get("type_id")
    return None


def _card_busy(base_path):
    """True if a live VFIO consumer holds this card (never disturb it at
    registration). _vfio_group_in_use is itself conservative (True on any read
    error) and is a module-level import now (no cycle)."""
    return _vfio_group_in_use(base_path)


def _mig_profile_ids(gpu):
    """Map of MIG suffix -> mig_profile_id from the discovery payload."""
    out = {}
    for mig in gpu.get("mig_profiles") or []:
        name = mig.get("name")
        if name:
            out[canonical_suffix(name)] = mig.get("profile_id")
    return out


def _report(pci_bdf, result, applied=None, previous=None, **extra):
    rep = {"applied_profile": applied, "previous_profile": previous, "result": result}
    rep.update({k: v for k, v in extra.items() if v is not None})
    return rep


def _pool_size(pci_bdf, suffix, sub_paths=None):
    """Realisable mdev count for a vGPU profile. On SR-IOV cards each VF realizes
    one mdev, so the count is the number of VFs; on PF-mdev cards (T4) use the
    driver max/available (>=1). Mirrors the engine's per-VF model."""
    if sub_paths:
        return len(sub_paths)
    want = canonical_suffix(suffix)
    for prof in _live_profiles(pci_bdf):
        name = prof.get("name") or ""
        if "-" in name and canonical_suffix(name.split("-", 1)[1]) == want:
            for key in ("max_instances", "available_instances"):
                val = prof.get(key)
                if isinstance(val, int) and val > 0:
                    return val
    return 1


def _live_mdev_count(pci_bdf, run, sub_paths=None):
    """How many live mdev devices exist under this card's PF + VFs (existence
    check, no type mapping). Used to confirm a vGPU carve materialised. When
    sub_paths are known, glob those too: SR-IOV VFs are normally reachable via
    the virtfn* symlinks, but legacy <base>.N sub-functions have no virtfn*
    link, so a successful carve there would otherwise be miscounted as zero."""
    globs = [
        f"/sys/bus/pci/devices/{pci_bdf}/mdev_supported_types/*/devices/*",
        f"/sys/bus/pci/devices/{pci_bdf}/virtfn*/mdev_supported_types/*/devices/*",
    ]
    for sp in sub_paths or []:
        globs.append(f"{sp.rstrip('/')}/mdev_supported_types/*/devices/*")
    res = run([f"ls -d {' '.join(globs)} 2>/dev/null | wc -l"], timeout=10)
    try:
        return int((_out(res) or "0").strip())
    except ValueError:
        return 0


def _apply(gpu, current, wanted, run):
    """Execute the host commands to apply ``wanted`` (from ``current``), in
    phases, and return ``(mdevs_pool, error)``. ``error`` is a string on a
    build/resolve/create failure (the caller then reports 'error'). vGPU carving
    resolves the live mdev type AFTER the driver rebind has actually run, and
    per VF on SR-IOV cards."""
    pci_bdf = gpu["pci_bus_id"]
    base_path = gpu.get("path") or f"/sys/bus/pci/devices/{pci_bdf}"
    sub_paths = gpu.get("sub_paths") or None
    sriov_totalvfs = gpu.get("sriov_totalvfs", 0) or 0
    sriov_numvfs = gpu.get("sriov_numvfs", 0) or 0
    companions = gpu.get("companion_pci_bdfs") or []
    mig_ids = _mig_profile_ids(gpu)
    new_is_mig = wanted in mig_ids
    old_is_mig = current == MIG_CURRENT or (current in mig_ids if current else False)

    # MIG on either side: handle the MIG mode transition up front.
    if new_is_mig or old_is_mig:
        cmds = _cmds.build_mig_transition_cmds(
            pci_bdf, old_is_mig, new_is_mig, current, wanted, mig_ids.get(wanted)
        )
        if cmds is None:
            return {}, "mig transition with no MIG profile"
        run(cmds, timeout=180)
        if new_is_mig:
            # MIG enable + GPU-instance carve happened in the transition. The
            # caller gates this on a mig.mode==Enabled readback so a failed
            # -mig 1 reports 'error', not a silent 'applied'.
            type_id = _resolve_type_id(pci_bdf, wanted, sub_paths) or wanted
            uuid, entry = new_mdev_pool_entry(
                pci_bdf, type_id, mig=True, mig_profile_id=mig_ids.get(wanted)
            )
            return {wanted: {uuid: entry}}, None
        # old_is_mig and the target is NOT MIG: build_mig_transition_cmds only
        # TORE MIG DOWN (destroy instances + -mig 0 + gpu-reset, re-enabling
        # SR-IOV for a vGPU target). That is just the prep -- fall through to
        # bind passthrough / carve the vGPU on the now-plain card. MIG is gone,
        # so treat it as a plain nvidia-bound card (current=None => the vGPU
        # prep correctly skips the passthrough unbind). The vGPU block below
        # re-enumerates the now-live VFs (sub_paths was empty for a MIG card).
        current = None

    if wanted == "passthrough":
        cmds = _cmds.build_vfio_bind_cmds(pci_bdf, sriov_totalvfs, sriov_numvfs)
        cmds += _cmds.build_vfio_group_mknod_cmds(pci_bdf)
        for cbdf in companions:
            cmds += _cmds.build_companion_bind_cmds(cbdf)
        run(cmds, timeout=180)
        # Report ONE passthrough pool entry (not an empty pool): passthrough is
        # bookable via a single pseudo-mdev slot whose type_id is the sentinel
        # "passthrough" (the engine never echoes it to mdev_supported_types, just
        # marks it created). Without this entry the engine's no-fight confirm
        # path would leave the card with an empty pool -> no created==True slot
        # -> unbookable. Matches the engine's lazy passthrough mint schema.
        uuid, entry = new_mdev_pool_entry(pci_bdf, "passthrough")
        return {"passthrough": {uuid: entry}}, None

    # vGPU target. PHASE 1: ensure nvidia-bound (reverse passthrough if needed)
    # and settle, and RUN it -- so the VFs/PF expose mdev_supported_types BEFORE
    # we resolve the live type dir (resolving while still vfio-bound finds none).
    prep = []
    if current == "passthrough":
        prep += _cmds.build_vfio_unbind_cmds(pci_bdf, sriov_totalvfs)
        for cbdf in companions:
            prep += _cmds.build_companion_release_cmds(cbdf)
    prep.append("udevadm settle 2>/dev/null || true")
    run(prep, timeout=180)

    # If the SR-IOV VFs weren't known when the descriptor was built (a card in
    # passthrough has its VFs torn down -> sub_paths empty; a MIG card reports
    # none), the prep above just re-enabled them (vfio-unbind re-creates VFs, or
    # the MIG teardown ran sriov-manage -e). Enumerate them now so the carve
    # targets the VFs, where SR-IOV/datacenter cards expose mdev_supported_types
    # (the PF exposes none). No-op when sub_paths is already known (registration)
    # or for a genuine PF-mdev card (T4) with no virtfn links.
    if not sub_paths:
        sub_paths = _enumerate_vf_sub_paths(pci_bdf, run) or sub_paths

    # PHASE 2: resolve against the now-exposed VF (or PF) type dirs and carve one
    # mdev per VF (SR-IOV) or per pool slot (PF-mdev cards).
    type_id = _resolve_type_id(pci_bdf, wanted, sub_paths)
    if not type_id:
        return {}, f"profile {wanted} not exposed by the driver"
    # Carve one mdev per VF (SR-IOV) or per pool slot (PF-mdev). Record ONLY the
    # mdevs whose create actually succeeded, so a partial failure neither reports
    # phantom mdevs nor orphans the ones that did get created (those are tracked
    # and the engine reconcile can fill the rest). Only a total failure errors.
    planned = []  # (uuid, entry, create_cmd)
    if sub_paths:
        for vf_path in sub_paths:
            uuid, entry = new_mdev_pool_entry(os.path.basename(vf_path), type_id)
            planned.append((uuid, entry, build_mdev_create_cmd(vf_path, type_id, uuid)))
    else:
        for _ in range(_pool_size(pci_bdf, wanted)):
            uuid, entry = new_mdev_pool_entry(pci_bdf, type_id)
            planned.append(
                (uuid, entry, build_mdev_create_cmd(base_path, type_id, uuid))
            )
    # the create echo has no 2>/dev/null, so a failed '>' surfaces real stderr
    results = run([c for _, _, c in planned], timeout=180) or []
    if len(results) != len(planned):
        # run() returned a different count than commands issued (a truncated /
        # crashed batch). Do NOT silently zip-truncate -- that would under-record
        # the carve (mdevs created on the host but absent from the report). Error
        # the card so the engine reconcile retries from the live state.
        return {}, (
            f"mdev create result count {len(results)} != {len(planned)} planned"
        )
    mdevs = {wanted: {}}
    first_err = None
    for (uuid, entry, _), res in zip(planned, results):
        err = (res.get("err") or "").strip()
        if err:
            first_err = first_err or err
            continue
        mdevs[wanted][uuid] = entry
    if not mdevs[wanted]:
        return {}, f"mdev create failed: {(first_err or 'no mdev created')[:160]}"
    return mdevs, None


def apply_target(gpu, target, run=run_local):
    """Apply one card's target profile locally and return the applied-state
    report the caller POSTs back to the API.

    Reports 'applied' ONLY after a post-apply driver readback (and, for vGPU, a
    materialised mdev) confirms the sysfs sequence took; otherwise 'error', so
    ingest never persists a lie and the engine reconcile recovers on the next
    cycle."""
    pci_bdf = gpu["pci_bus_id"]
    base_path = gpu.get("path") or f"/sys/bus/pci/devices/{pci_bdf}"
    reset_at = gpu.get("mdevs_reset_at")

    if not is_actionable(target):
        # Advisory skip (skip_retry / skip_fault): nothing applied, but preserve
        # the existing pool -- carry mdevs_reset_at so the API re-pins
        # mdevs_last_synced_at and the engine confirms instead of rebuilding.
        return _report(pci_bdf, "skipped_advisory", mdevs_reset_at=reset_at)

    wanted = target_suffix(target)
    driver = _read_driver(pci_bdf, run)
    mig_mode = _read_mig_mode(pci_bdf, run)
    current = current_profile_from_state(
        driver, mig_mode, _live_mdev_suffix(pci_bdf, run)
    )

    action = decide_apply_action(current, wanted, _card_busy(base_path))
    if action in ("noop", "skipped_busy"):
        # Carry mdevs_reset_at so the API can re-pin mdevs_last_synced_at even
        # though nothing was applied: a noop/busy card's existing pool is still
        # valid (a live desktop's mdev survived this discovery's reset), so the
        # engine must CONFIRM, not run the authoritative rebuild that would stop
        # the still-alive desktop.
        return _report(
            pci_bdf,
            action,
            applied=current,
            previous=current,
            binding=driver,
            mig_mode=mig_mode,
            mdevs_reset_at=reset_at,
        )

    try:
        mdevs, err = _apply(gpu, current, wanted, run)
    except Exception as e:  # never abort the whole registration for one card
        return _report(pci_bdf, "error", previous=current, error=str(e))
    if err:
        return _report(pci_bdf, "error", previous=current, error=err)

    # Verify the realised state matches intent before claiming success.
    new_driver = _read_driver(pci_bdf, run)
    expected_driver = "vfio-pci" if wanted == "passthrough" else "nvidia"
    if new_driver != expected_driver:
        return _report(
            pci_bdf,
            "error",
            previous=current,
            binding=new_driver,
            error=f"post-apply driver {new_driver!r} != expected {expected_driver!r}",
        )
    is_mig = wanted in _mig_profile_ids(gpu)
    if is_mig:
        # The driver readback above is a tautology for MIG (a MIG card stays
        # nvidia-bound), so gate on the actual MIG state: a failed nvidia-smi
        # -mig 1 leaves mig.mode Disabled and must report 'error'.
        post_mig = _read_mig_mode(pci_bdf, run)
        if not (isinstance(post_mig, str) and "enabled" in post_mig.lower()):
            return _report(
                pci_bdf,
                "error",
                previous=current,
                binding=new_driver,
                mig_mode=post_mig,
                error=f"MIG {wanted} enable did not take (mig_mode={post_mig!r})",
            )
    is_vgpu = wanted != "passthrough" and not is_mig
    if is_vgpu and _live_mdev_count(pci_bdf, run, gpu.get("sub_paths")) == 0:
        return _report(
            pci_bdf,
            "error",
            previous=current,
            binding=new_driver,
            error=f"vGPU {wanted} carve did not materialise (no live mdev)",
        )
    return _report(
        pci_bdf,
        "applied",
        applied=wanted,
        previous=current,
        binding=new_driver,
        mig_mode=_read_mig_mode(pci_bdf, run),
        mdevs=mdevs,
        mdevs_reset_at=reset_at,
    )


def _is_mig_target(gpu, targets):
    """Whether this card's target is a MIG profile."""
    return target_suffix(targets.get(gpu.get("pci_bus_id"))) in _mig_profile_ids(gpu)


def apply_targets(nvidia_gpus, targets, run=run_local):
    """Apply the per-card targets (keyed by pci_bus_id) for all discovered GPUs.
    Returns {pci_bus_id: report}. Best-effort: one card failing never aborts the
    others.

    Non-MIG cards (vGPU/passthrough) are applied BEFORE MIG cards: a MIG
    transition issues ``nvidia-smi --gpu-reset``, which on a multi-GPU board can
    disturb a sibling, so we finish the carves that don't need a reset first."""
    applied = {}
    targets = targets or {}
    cards = [
        gpu
        for gpu in (nvidia_gpus or [])
        if gpu.get("pci_bus_id") and gpu.get("vgpu_profiles") is not None
    ]
    # stable sort: False (non-MIG) before True (MIG)
    cards.sort(key=lambda gpu: _is_mig_target(gpu, targets))
    for gpu in cards:
        pci_bdf = gpu["pci_bus_id"]
        try:
            applied[pci_bdf] = apply_target(gpu, targets.get(pci_bdf), run=run)
        except Exception as e:
            applied[pci_bdf] = _report(pci_bdf, "error", error=str(e))
    return applied
