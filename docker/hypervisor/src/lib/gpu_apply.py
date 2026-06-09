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

import logging
import os
import signal
import time
import uuid as _uuid

import gpu_probe
from gpu_discovery import (
    _card_in_use,
    _get_vgpu_profiles,
    _normalize_pci_bus_id,
    _vfio_group_in_use,
)
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

# Per-card apply progress goes to stdout (docker logs isard-hypervisor). The
# apply phase runs inside `hypervisor.py setup`, which configures the root
# logger to stdout, so this child logger propagates there. Without it the
# multi-minute GPU apply at registration is completely silent and looks like a
# hang (it is not -- each card carve can legitimately take minutes + retries).
log = logging.getLogger("gpu_apply")


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
    """True if a live VFIO consumer holds this card -- the PF passthrough group
    OR any SR-IOV VF mdev (vGPU/MIG desktops). Never disturb a busy card at
    registration. _card_in_use is conservative (True on any read error)."""
    return _card_in_use(base_path)


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


# Transient post-restart settle. A hypervisor (container) restart can leave the
# card briefly unsettled: the carve's ``--gpu-reset`` / SR-IOV re-enable can
# return before the kernel re-attaches nvidia to the PF ("post-apply driver
# None") or before a freshly-created VF accepts the mdev sysfs write ("mdev
# create ... I/O error"). Both clear within seconds. We poll for the driver to
# settle and retry the whole carve a few times so a boot-time race self-heals,
# instead of giving up and leaving the card uncarved with a phantom (created)
# pool the engine then trusts -> GPU desktops fail to start until a manual
# re-force.
_APPLY_ATTEMPTS = 3
_APPLY_RETRY_DELAY = 3  # seconds between whole-carve retries
_DRIVER_SETTLE_ATTEMPTS = 10
_DRIVER_SETTLE_DELAY = 2  # seconds (~20s max for the driver to re-attach)
_SLEEP = time.sleep  # indirection so tests can stub the settle waits


def _wait_for_driver(pci_bdf, expected, run):
    """Poll the PF driver until it settles to ``expected`` (or attempts run out).

    After a ``--gpu-reset`` / SR-IOV re-enable the kernel re-binds the driver
    asynchronously, so the first readback right after the carve can be ``None``
    even though the sequence actually succeeded. Returns the last driver read."""
    drv = _read_driver(pci_bdf, run)
    for _ in range(_DRIVER_SETTLE_ATTEMPTS):
        if drv == expected:
            return drv
        _SLEEP(_DRIVER_SETTLE_DELAY)
        drv = _read_driver(pci_bdf, run)
    return drv


# --------------------------------------------------------------------------- #
# Deliberate profile-change quiesce: force-stop every qemu holding the card
# (PF or any VF) before a teardown, then verify release. NEVER unbind an in-use
# vfio device -- that wedges the PF in uninterruptible D-state (reboot-only).
# Used ONLY on a deliberate change (runtime profile change / operator force),
# never on registration/advisory applies. Runtime: libvirtd is up so we virsh
# destroy the owning domains; boot: libvirtd is down and normally no qemu
# exists, so the SIGKILL fallback handles a stray leftover. The /proc + os.kill
# probes are the unit-test monkeypatch points.
# --------------------------------------------------------------------------- #
_QUIESCE_ATTEMPTS = 10
_QUIESCE_DELAY = 1  # s; ~10s for qemu to release the vfio fd after destroy


def _card_vfio_targets(base_path):
    """Realpaths of /dev/vfio/<group> for this card's PF and every VF."""
    groups = []
    try:
        groups.append(
            os.path.basename(os.path.realpath(os.path.join(base_path, "iommu_group")))
        )
    except OSError:
        pass
    try:
        for name in os.listdir(base_path):
            if name.startswith("virtfn"):
                groups.append(
                    os.path.basename(
                        os.path.realpath(os.path.join(base_path, name, "iommu_group"))
                    )
                )
    except OSError:
        pass
    targets = set()
    for g in groups:
        dev = f"/dev/vfio/{g}"
        if os.path.exists(dev):
            try:
                targets.add(os.path.realpath(dev))
            except OSError:
                pass
    return targets


def _card_holder_pids(base_path):
    """PIDs holding this card's PF or any VF /dev/vfio group (the qemu(s) using
    the card). Best-effort (empty on read errors); the conservative bool guard
    is gpu_discovery._card_in_use."""
    targets = _card_vfio_targets(base_path)
    pids = set()
    if not targets:
        return pids
    try:
        proc = os.listdir("/proc")
    except OSError:
        return pids
    for pid in proc:
        if not pid.isdigit():
            continue
        fd_dir = f"/proc/{pid}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                if os.path.realpath(os.path.join(fd_dir, fd)) in targets:
                    pids.add(int(pid))
                    break
            except OSError:
                pass
    return pids


def _domain_of_pid(pid):
    """libvirt domain name from a qemu PID's cmdline (``-name guest=<dom>``),
    or None."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            args = f.read().split(b"\x00")
    except OSError:
        return None
    for i, a in enumerate(args):
        if a == b"-name" and i + 1 < len(args):
            a = args[i + 1]
        for part in a.decode("utf-8", "replace").split(","):
            if part.startswith("guest="):
                return part[len("guest=") :]
    return None


def _quiesce_card(gpu, run):
    """Force-stop every qemu holding this card (PF or VFs), then verify the card
    is released. Returns ``(cleared, reason)``. The caller MUST NOT proceed to a
    teardown when this returns False -- unbinding an in-use vfio device wedges
    the PF in uninterruptible D-state."""
    pci_bdf = gpu["pci_bus_id"]
    base_path = gpu.get("path") or f"/sys/bus/pci/devices/{pci_bdf}"
    if not _card_in_use(base_path):
        return True, "no holders"
    pids = _card_holder_pids(base_path)
    log.info(
        "quiesce %s: card in use, holder pids=%s -- stopping", pci_bdf, sorted(pids)
    )
    for pid in pids:
        dom = _domain_of_pid(pid)
        if dom:
            log.info("quiesce %s: virsh destroy %s (pid %s)", pci_bdf, dom, pid)
            run([f"virsh destroy {dom} 2>/dev/null || true"], timeout=20)
    for _ in range(_QUIESCE_ATTEMPTS):
        if not _card_in_use(base_path):
            return True, "cleared"
        _SLEEP(_QUIESCE_DELAY)
    # Last resort: SIGKILL whatever still holds it (orphaned qemu / boot-time
    # leftover with no libvirt domain).
    for pid in _card_holder_pids(base_path):
        try:
            os.kill(pid, signal.SIGKILL)
            log.warning(
                "quiesce %s: SIGKILL pid %s (destroy did not release)", pci_bdf, pid
            )
        except OSError:
            pass
    for _ in range(_QUIESCE_ATTEMPTS):
        if not _card_in_use(base_path):
            return True, "cleared after SIGKILL"
        _SLEEP(_QUIESCE_DELAY)
    return False, (
        f"card {pci_bdf} still held after destroy+kill "
        f"(pids={sorted(_card_holder_pids(base_path))})"
    )


def apply_target(gpu, target, run=run_local, deliberate=False):
    """Apply one card's target profile locally and return the applied-state
    report the caller POSTs back to the API.

    Reports 'applied' ONLY after a post-apply driver readback (and, for vGPU, a
    materialised mdev) confirms the sysfs sequence took; otherwise 'error', so
    ingest never persists a lie and the engine reconcile recovers on the next
    cycle.

    On a ``deliberate`` change (runtime profile change / operator force) any
    qemu holding the card (PF or a VF) is force-stopped before teardown; the
    apply ABORTS with ``result='teardown_blocked'`` if a holder can't be cleared
    (unbinding an in-use vfio device wedges the PF in D-state). A non-deliberate
    (registration/advisory) apply leaves a busy card untouched (skipped_busy)."""
    # Normalize to the 4-digit sysfs BDF. Discovery emits the nvidia-smi 8-digit
    # form (e.g. 00000000:83:00.0), but every sysfs readlink/bind and command
    # builder -- here AND in _apply, which inherits this gpu dict -- needs the
    # 4-digit sysfs form (0000:83:00.0); otherwise /sys/bus/pci/devices/<bdf>
    # does not exist, _read_driver returns None, and _card_busy mis-reads the
    # card as busy, so the whole startup apply is skipped (no profile ever
    # applied at boot). apply_targets keys the report by the ORIGINAL pci_bus_id,
    # so the per-card result still matches on the API side. Idempotent for a BDF
    # already in sysfs form (the engine-driven runtime path).
    pci_bdf = _normalize_pci_bus_id(gpu["pci_bus_id"]).lower()
    base_path = f"/sys/bus/pci/devices/{pci_bdf}"
    gpu = {**gpu, "pci_bus_id": pci_bdf, "path": base_path}
    reset_at = gpu.get("mdevs_reset_at")

    t0 = time.monotonic()

    if not is_actionable(target):
        # Advisory skip (skip_retry / skip_fault): nothing applied, but preserve
        # the existing pool -- carry mdevs_reset_at so the API re-pins
        # mdevs_last_synced_at and the engine confirms instead of rebuilding.
        log.info("apply %s: advisory skip (target=%r), pool preserved", pci_bdf, target)
        return _report(pci_bdf, "skipped_advisory", mdevs_reset_at=reset_at)

    wanted = target_suffix(target)
    driver = _read_driver(pci_bdf, run)
    if driver not in ("nvidia", "vfio-pci"):
        # The PF is bound to NO driver (orphaned by a transition interrupted
        # mid-flight -- e.g. the hypervisor crashed/restarted between the vfio
        # unbind and the nvidia rebind) or to a stray transient (pci-pf-stub
        # left over from a half-done SR-IOV dance). In that state nvidia-smi /
        # sysfs ops and current-detection misbehave and the apply fails. Recover
        # the PF to the nvidia base so ANY apply self-heals, then re-read.
        run(_cmds.build_pf_recover_nvidia_cmds(pci_bdf), timeout=60)
        driver = _read_driver(pci_bdf, run)
    mig_mode = _read_mig_mode(pci_bdf, run)
    current = current_profile_from_state(
        driver, mig_mode, _live_mdev_suffix(pci_bdf, run)
    )

    action = decide_apply_action(current, wanted, _card_busy(base_path))
    log.info(
        "apply %s: current=%s wanted=%s action=%s (driver=%s mig=%s deliberate=%s)",
        pci_bdf,
        current,
        wanted,
        action,
        driver,
        mig_mode,
        deliberate,
    )
    if action == "noop" or (action == "skipped_busy" and not deliberate):
        log.info("apply %s: %s -- nothing to do, existing pool kept", pci_bdf, action)
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

    # We are about to MUTATE the card (action == "apply", or a deliberate change
    # on a busy card). On a deliberate change, force-stop any qemu holding the
    # card FIRST -- unbinding an in-use vfio device wedges the PF in D-state.
    if deliberate:
        cleared, reason = _quiesce_card(gpu, run)
        if not cleared:
            log.error("apply %s: deliberate change ABORTED -- %s", pci_bdf, reason)
            return _report(
                pci_bdf,
                "teardown_blocked",
                previous=current,
                binding=_read_driver(pci_bdf, run),
                mig_mode=mig_mode,
                error=reason,
            )

    # Apply + verify, with a bounded retry so a transient post-restart settle
    # race (driver not yet re-attached, VF not yet ready for the mdev write)
    # self-heals instead of leaving the card uncarved with a phantom pool. Each
    # retry first recovers an orphaned PF and re-reads `current`.
    expected_driver = "vfio-pci" if wanted == "passthrough" else "nvidia"
    last_error = None
    for attempt in range(_APPLY_ATTEMPTS):
        if attempt:
            log.info(
                "apply %s: retry %d/%d after error: %s",
                pci_bdf,
                attempt + 1,
                _APPLY_ATTEMPTS,
                last_error,
            )
            _SLEEP(_APPLY_RETRY_DELAY)
            if expected_driver == "nvidia" and _read_driver(pci_bdf, run) != "nvidia":
                run(_cmds.build_pf_recover_nvidia_cmds(pci_bdf), timeout=60)
            driver = _read_driver(pci_bdf, run)
            mig_mode = _read_mig_mode(pci_bdf, run)
            current = current_profile_from_state(
                driver, mig_mode, _live_mdev_suffix(pci_bdf, run)
            )

        try:
            mdevs, err = _apply(gpu, current, wanted, run)
        except Exception as e:  # never abort the whole registration for one card
            last_error = str(e)
            log.warning("apply %s: carve raised: %s", pci_bdf, last_error)
            continue
        if err:
            last_error = err
            log.warning("apply %s: carve returned error: %s", pci_bdf, err)
            continue

        # Verify the realised state matches intent before claiming success.
        # `_wait_for_driver` polls because the kernel re-attaches the driver
        # asynchronously after the carve's gpu-reset/SR-IOV cycle.
        new_driver = _wait_for_driver(pci_bdf, expected_driver, run)
        if new_driver != expected_driver:
            last_error = (
                f"post-apply driver {new_driver!r} != expected {expected_driver!r}"
            )
            continue
        is_mig = wanted in _mig_profile_ids(gpu)
        if is_mig:
            # The driver readback above is a tautology for MIG (a MIG card stays
            # nvidia-bound), so gate on the actual MIG state: a failed nvidia-smi
            # -mig 1 leaves mig.mode Disabled and must report 'error'.
            post_mig = _read_mig_mode(pci_bdf, run)
            if not (isinstance(post_mig, str) and "enabled" in post_mig.lower()):
                last_error = f"MIG {wanted} enable did not take (mig_mode={post_mig!r})"
                continue
        is_vgpu = wanted != "passthrough" and not is_mig
        if is_vgpu and _live_mdev_count(pci_bdf, run, gpu.get("sub_paths")) == 0:
            last_error = f"vGPU {wanted} carve did not materialise (no live mdev)"
            continue
        log.info(
            "apply %s: applied %s (was %s) in %.1fs",
            pci_bdf,
            wanted,
            current,
            time.monotonic() - t0,
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

    log.error(
        "apply %s: FAILED after %d attempts in %.1fs -- %s",
        pci_bdf,
        _APPLY_ATTEMPTS,
        time.monotonic() - t0,
        last_error,
    )
    return _report(
        pci_bdf,
        "error",
        previous=current,
        binding=_read_driver(pci_bdf, run),
        error=f"apply failed after {_APPLY_ATTEMPTS} attempts: {last_error}",
    )


def _is_mig_target(gpu, targets):
    """Whether this card's target is a MIG profile."""
    return target_suffix(targets.get(gpu.get("pci_bus_id"))) in _mig_profile_ids(gpu)


def apply_targets(nvidia_gpus, targets, run=run_local, progress=None, deliberate=False):
    """Apply the per-card targets (keyed by pci_bus_id) for all discovered GPUs.
    Returns {pci_bus_id: report}. Best-effort: one card failing never aborts the
    others.

    Non-MIG cards (vGPU/passthrough) are applied BEFORE MIG cards: a MIG
    transition issues ``nvidia-smi --gpu-reset``, which on a multi-GPU board can
    disturb a sibling, so we finish the carves that don't need a reset first.

    ``progress`` is an optional callback ``(index, total, pci_bdf, wanted)``
    invoked before each card so the caller can surface live boot-progress (the
    apply phase can take minutes on multi-card vGPU/MIG hosts)."""
    applied = {}
    targets = targets or {}
    cards = [
        gpu
        for gpu in (nvidia_gpus or [])
        if gpu.get("pci_bus_id") and gpu.get("vgpu_profiles") is not None
    ]
    # stable sort: False (non-MIG) before True (MIG)
    cards.sort(key=lambda gpu: _is_mig_target(gpu, targets))
    total = len(cards)
    t0 = time.monotonic()
    log.info(
        "applying GPU targets to %d card(s): %s",
        total,
        ", ".join(
            f"{g['pci_bus_id']}->{target_suffix(targets.get(g['pci_bus_id']))}"
            for g in cards
        )
        or "(none)",
    )
    for idx, gpu in enumerate(cards, start=1):
        pci_bdf = gpu["pci_bus_id"]
        wanted = target_suffix(targets.get(pci_bdf))
        log.info("apply [%d/%d] %s -> %s starting", idx, total, pci_bdf, wanted)
        if progress is not None:
            try:
                progress(idx, total, pci_bdf, wanted)
            except Exception:
                pass  # progress reporting must never break the apply
        try:
            applied[pci_bdf] = apply_target(
                gpu, targets.get(pci_bdf), run=run, deliberate=deliberate
            )
        except Exception as e:
            log.warning("apply [%d/%d] %s raised: %s", idx, total, pci_bdf, e)
            applied[pci_bdf] = _report(pci_bdf, "error", error=str(e))
    log.info("GPU apply complete: %d card(s) in %.1fs", total, time.monotonic() - t0)
    return applied
