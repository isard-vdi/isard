"""Apply a vGPU / MIG / passthrough profile to a physical GPU LOCALLY.

Runs inside the hypervisor container at registration time. The container already
has /sys, nvidia-smi, sriov-manage and (privileged) /dev/nvidia* + /dev/vfio, so
the host-command sequences the engine used to run over SSH can run here directly.
This module imports the SAME shared builders the engine uses
(``gpu_cmds`` / ``gpu_pool_policy`` from /src/isardvdi_common/lib) so the two paths cannot
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
import re
import shlex
import signal
import time
import uuid as _uuid

import gpu_probe
from gpu_discovery import (
    _card_in_use,
    _get_vgpu_profiles,
    _get_vgpu_profiles_vfio,
    _normalize_pci_bus_id,
    _vfio_group_in_use,
)
from gpu_probe import (
    FRAMEWORK_VFIO_VARIANT,
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


def new_vfio_pool_entry(vf_bdf, type_id, mig=False, mig_profile_id=None):
    """Build one ``vgpus.mdevs[profile][entry_id]`` entry for the vendor-specific
    VFIO framework, keyed by the VF's PCI BDF (no mdev UUID -- the VF *is* the
    vGPU). Returned as ``(vf_bdf, entry)`` to mirror :func:`new_mdev_pool_entry`.
    The ``framework`` + ``vf_bdf`` fields let the engine emit a vfio-pci VF
    hostdev (not an mdev hostdev) and the reconcile distinguish this entry kind.
    ``pci_mdev_id`` is kept = the VF BDF for downstream readers that expect it.

    ``mig``/``mig_profile_id`` tag a MIG-backed vGPU VF (the GIs are carved before
    the per-VF ``current_vgpu_type`` write), mirroring :func:`new_mdev_pool_entry`
    so bookings/reconcile track a vfio MIG entry exactly as the legacy mdev one."""
    entry = {
        "framework": FRAMEWORK_VFIO_VARIANT,
        "vf_bdf": vf_bdf,
        "pci_mdev_id": vf_bdf,
        "type_id": type_id,
        "created": True,
        "domain_started": False,
        "domain_reserved": False,
    }
    if mig:
        entry["mig"] = True
        entry["mig_profile_id"] = mig_profile_id
    return vf_bdf, entry


def _live_profiles_vfio(vf_bdf):
    """Live vGPU profiles a VF can create on the vendor-specific VFIO framework,
    via the discovery reader (``nvidia/creatable_vgpu_types``). The vfio twin of
    :func:`_live_profiles`."""
    return _get_vgpu_profiles_vfio(vf_bdf) or []


def _resolve_type_id_vfio(suffix, sub_paths):
    """Numeric vGPU type-id (written to ``current_vgpu_type``) for a profile
    suffix on the vendor-specific VFIO framework, or None. Matches by canonical
    profile NAME against each VF's ``creatable_vgpu_types`` -- the vfio twin of
    :func:`_resolve_type_id`."""
    want = canonical_suffix(suffix)
    for sp in sub_paths or []:
        for prof in _live_profiles_vfio(os.path.basename(sp)):
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


def _mig_vgpu_entry(gpu, suffix):
    """The MIG-backed vGPU profile entry for ``suffix`` (canonical), or None.

    Discovery (``_annotate_mig_backed_vgpu_profiles``) tags each vGPU mdev
    profile that is realized via MIG slices (the ``DC-N-<mem>Q`` family, suffix
    like ``"1_24Q"``) with ``mig=True`` plus ``mig_profile_id`` (the matching
    ``+gfx`` GPU-instance profile to create) and ``mig_count`` (how many GIs /
    bookable slices the card yields). This looks that entry up so ``_apply``
    knows to carve N GIs + re-enable SR-IOV before the per-VF mdev carve. Returns
    None for plain (non-MIG) vGPU profiles like the full-card ``"24Q"``."""
    if not suffix:
        return None
    want = canonical_suffix(suffix)
    for prof in gpu.get("vgpu_profiles") or []:
        if not prof.get("mig"):
            continue
        name = prof.get("name") or ""
        if canonical_suffix(name.rsplit("-", 1)[-1]) == want:
            return prof
    return None


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


def _live_vgpu_count(sub_paths, run):
    """How many SR-IOV VFs hold a live vGPU on the vendor-specific VFIO framework
    (``nvidia/current_vgpu_type`` present and != 0). The vfio twin of
    :func:`_live_mdev_count`, used to confirm a vfio carve materialised."""
    paths = " ".join(
        f"'{sp.rstrip('/')}/nvidia/current_vgpu_type'" for sp in sub_paths or []
    )
    if not paths:
        return 0
    res = run(
        [
            f'for f in {paths}; do v=$(cat "$f" 2>/dev/null); '
            f'[ -n "$v" ] && [ "$v" != 0 ] && echo 1; done | wc -l'
        ],
        timeout=10,
    )
    try:
        return int((_out(res) or "0").strip())
    except ValueError:
        return 0


def _live_mdev_pool(pci_bdf, run, current_suffix, gpu, sub_paths=None):
    """Enumerate the card's LIVE mdevs into the ``vgpus.mdevs`` schema
    ``{suffix: {uuid: entry}}`` carrying the EXISTING host UUIDs (entries free;
    the API ingest re-adopts ``domain_started``/``domain_reserved`` for any UUID
    it already tracked, so a running desktop is never dropped).

    Used so a ``noop``/``skipped_busy`` report can re-pin the DB pool to host
    reality (same profile, but the live UUIDs may have changed -- e.g. discovery
    re-carved, or a hypervisor-container recreate minted a fresh set). Returns
    ``None`` for passthrough/MIG_CURRENT (pseudo pool) or when nothing is live, so
    the caller keeps the timestamp-only path."""
    if not current_suffix or current_suffix in ("passthrough", MIG_CURRENT):
        return None
    type_id = _resolve_type_id(pci_bdf, current_suffix, sub_paths)
    if not type_id:
        return None
    bases = list(sub_paths or [f"/sys/bus/pci/devices/{pci_bdf}"])
    res = (
        run(
            [
                f"ls -1 '{b.rstrip('/')}/mdev_supported_types/{type_id}/devices' "
                "2>/dev/null || true"
                for b in bases
            ],
            timeout=20,
        )
        or []
    )
    # A truncated batch (fewer results than bases) would yield a PARTIAL pool
    # that, r.literal-replaced, drops the running-desktop UUIDs on the missing
    # bases. Never reconcile from a partial enumeration: fall back to the
    # timestamp-only path (which keeps the existing pool intact).
    if len(res) != len(bases):
        return None
    mig_ids = _mig_profile_ids(gpu)
    is_mig = current_suffix in mig_ids
    pool = {}
    for idx, b in enumerate(bases):
        out = (res[idx].get("out") if idx < len(res) else "") or ""
        for uuid in out.split():
            uuid = uuid.strip()
            if not uuid:
                continue
            entry = {
                "pci_mdev_id": os.path.basename(b.rstrip("/")),
                "type_id": type_id,
                "created": True,
                "domain_started": False,
                "domain_reserved": False,
            }
            if is_mig:
                entry["mig"] = True
                entry["mig_profile_id"] = mig_ids.get(current_suffix)
            pool[uuid] = entry
    return {current_suffix: pool} if pool else None


def _running_mdev_uuids(run):
    """Set of vGPU pool KEYS currently attached to a RUNNING libvirt domain --
    mdev UUIDs (legacy framework) AND vfio-variant VF BDFs (the vfio vGPU hostdev
    has no uuid; its key is the VF BDF, reconstructed from the ``ua-isard-vgpu-*``
    engine alias). The pool is keyed by whichever identifier the framework uses,
    and ``reconcile_pool_to_live`` matches on that key, so both forms belong here.

    Carried on a ``noop``/``skipped_busy`` report so the ingest reconcile adopts
    ``domain_started``/``domain_reserved`` ONLY for a key a desktop is actually
    running on right now -- never on the strength of a (possibly stale) DB flag.
    At hypervisor startup the entrypoint kills leftover qemu BEFORE registration,
    so this set is empty and a re-pin frees every entry (clean slate) instead of
    re-asserting a desktop that is not running. Best-effort: returns an empty set
    on any virsh failure (the reconcile then frees, which a real running desktop's
    next start/booking-align re-reserves)."""
    res = (
        run(["virsh list --name --state-running 2>/dev/null || true"], timeout=15) or []
    )
    out = (res[0].get("out") if res else "") or ""
    # `virsh list --name` prints one domain name per line; split on lines (NOT
    # whitespace) so a name containing a space stays intact.
    names = [n.strip() for n in out.splitlines() if n.strip()]
    # Each name is interpolated into a shell command below. shlex.quote neutralises
    # embedded quotes/metacharacters; additionally skip the (never-valid for an
    # IsardVDI desktop) leading-dash names so they can't smuggle a virsh flag. A
    # skipped name only means its mdev is treated as free, and real desktop ids
    # start with '_' or an alphanumeric -- so this never drops a live desktop.
    safe = [n for n in names if not n.startswith("-")]
    if not safe:
        return set()
    dumps = (
        run(
            [f"virsh dumpxml {shlex.quote(n)} 2>/dev/null || true" for n in safe],
            timeout=30,
        )
        or []
    )
    uuids = set()
    for d in dumps:
        xml = (d.get("out") if isinstance(d, dict) else "") or ""
        # Legacy mdev: the only uuid= ATTRIBUTE in a domain XML is an mdev
        # hostdev's <source><address uuid='...'/> (the domain's own uuid is an
        # element, never matched here).
        for m in re.finditer(r"<address[^>]*\buuid=['\"]([0-9a-fA-F-]+)['\"]", xml):
            uuids.add(m.group(1).lower())
        # vfio_variant: a vGPU hostdev carries NO uuid -- its pool key is the VF
        # BDF, surfaced via the engine's ``ua-isard-vgpu-<vf>`` user-alias marker
        # (alias = vf_bdf with ':'/'.' -> '-'; see engine domain_xml). Reconstruct
        # the BDF so reconcile_pool_to_live re-adopts domain_started for the live
        # vfio desktop (else its VF is rebuilt FREE and the next start collides).
        for m in re.finditer(
            r"<alias[^>]*\bname=['\"]ua-isard-vgpu-([0-9a-fA-F-]+)['\"]", xml
        ):
            parts = m.group(1).split("-")
            if len(parts) == 4:
                uuids.add(f"{parts[0]}:{parts[1]}:{parts[2]}.{parts[3]}".lower())
    return uuids


def _apply(gpu, current, wanted, run):
    """Execute the host commands to apply ``wanted`` (from ``current``), in
    phases, and return ``(mdevs_pool, error)``. ``error`` is a string on a
    build/resolve/create failure (the caller then reports 'error'). vGPU carving
    resolves the live mdev type AFTER the driver rebind has actually run, and
    per VF on SR-IOV cards."""
    pci_bdf = gpu["pci_bus_id"]
    base_path = gpu.get("path") or f"/sys/bus/pci/devices/{pci_bdf}"
    sub_paths = gpu.get("sub_paths") or None
    # Per-card vGPU framework (discovery sets gpu['framework']). On the vendor-
    # specific VFIO framework (Ubuntu 24.04+) the vGPU is created by writing the
    # type-id to each VF's nvidia/current_vgpu_type and the pool entry is keyed
    # by VF BDF, not an mdev UUID. Absent => legacy mdev (the 22.04 fleet).
    is_vfio = gpu.get("framework") == FRAMEWORK_VFIO_VARIANT
    sriov_totalvfs = gpu.get("sriov_totalvfs", 0) or 0
    sriov_numvfs = gpu.get("sriov_numvfs", 0) or 0
    companions = gpu.get("companion_pci_bdfs") or []
    mig_ids = _mig_profile_ids(gpu)
    mig_vgpu = _mig_vgpu_entry(gpu, wanted)
    # A MIG-backed vGPU target (DC-N-<mem>Q, e.g. "1_24Q") is recognised via the
    # discovery annotation, NOT mig_ids (which is keyed by the GI name like
    # "1g.24gb+gfx"). Both forms count as "MIG" for the transition decision.
    new_is_mig = wanted in mig_ids or mig_vgpu is not None
    old_is_mig = (
        current == MIG_CURRENT
        or (current in mig_ids if current else False)
        or _mig_vgpu_entry(gpu, current) is not None
    )

    # vf_cap / mig_meta drive the shared vGPU carve below: a MIG-backed vGPU
    # carves one mdev per GI (capped at the slice count) and tags each entry.
    vf_cap = None
    mig_meta = {}

    if mig_vgpu is not None:
        # MIG-backed vGPU: create `mig_count` graphics GPU-instances of the +gfx
        # profile, then FALL THROUGH to the per-VF vGPU carve (tagged mig=True,
        # capped at the slice count). The VF DC-N-Q mdev type only exposes
        # available_instances once the GIs exist.
        gfx_id = mig_vgpu.get("mig_profile_id")
        count = mig_vgpu.get("mig_count") or 1
        # WARM repartition: if the card is ALREADY MIG-enabled with SR-IOV VFs up
        # (a MIG-vGPU -> MIG-vGPU profile switch), re-lay-out the GIs at the GI
        # level ONLY -- no sriov-manage / -mig toggle / GPU reset (validated on
        # Blackwell: SR-IOV/VFs and the PF binding stay intact). Otherwise COLD:
        # from passthrough / MIG-off, do the full enable-MIG + re-enable-SR-IOV
        # carve. (mig.mode is the reliable signal; numvfs is read live so a card
        # with VFs torn down still takes the cold path.)
        mig_mode = _read_mig_mode(pci_bdf, run)
        nv = _out(
            run(
                [f"cat /sys/bus/pci/devices/{pci_bdf}/sriov_numvfs 2>/dev/null"],
                timeout=10,
            )
        ).strip()
        warm = (
            current != "passthrough"
            and isinstance(mig_mode, str)
            and "enabled" in mig_mode.lower()
            and nv.isdigit()
            and int(nv) > 0
        )
        if warm:
            run(_cmds.build_mig_clear_card_mdevs_cmds(pci_bdf), timeout=60)
            run(_cmds.build_mig_recarve_cmds(pci_bdf, gfx_id, count), timeout=180)
        else:
            if current == "passthrough":
                # reverse passthrough first so the PF is nvidia-bound for MIG enable
                pre = _cmds.build_vfio_unbind_cmds(pci_bdf, sriov_totalvfs)
                for cbdf in companions:
                    pre += _cmds.build_companion_release_cmds(cbdf)
                run(pre, timeout=180)
            run(_cmds.build_mig_vgpu_carve_cmds(pci_bdf, gfx_id, count), timeout=240)
        # (re-)enumerate the VFs for the carve.
        sub_paths = _enumerate_vf_sub_paths(pci_bdf, run) or sub_paths
        vf_cap = count
        mig_meta = {"mig": True, "mig_profile_id": gfx_id}
        current = None  # now a MIG-enabled card; carve the vGPU mdevs on its VFs
    elif new_is_mig or old_is_mig:
        # Plain (GI-name) MIG transition, or tearing MIG down to a vGPU/PT target.
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
    #
    # vfio RECARVE SAFETY (load-bearing): a VF that already holds a
    # current_vgpu_type stops listing the OTHER creatable_vgpu_types and will not
    # accept a new type (write -> "Operation not permitted"); a larger profile
    # also won't fit until the framebuffer the OLD carve consumed ACROSS ALL the
    # card's VFs is released (write -> "Input/output error"). So on a switch we
    # must free the WHOLE card to 0 BEFORE resolving the new profile's type-id
    # (else _resolve_type_id_vfio sees the restricted list and reports "not
    # exposed") and before carving. Idempotent (already-0 VFs no-op, e.g. the
    # fresh boot carve); safe because the engine quiesces running domains first.
    if is_vfio and sub_paths:
        run(
            [_cmds.build_vgpu_clear_cmd(os.path.basename(p)) for p in sub_paths],
            timeout=120,
        )
    if is_vfio:
        type_id = _resolve_type_id_vfio(wanted, sub_paths)
    else:
        type_id = _resolve_type_id(pci_bdf, wanted, sub_paths)
    if not type_id:
        return {}, f"profile {wanted} not exposed by the driver"
    # Carve one mdev per VF (SR-IOV) or per pool slot (PF-mdev). Record ONLY the
    # mdevs whose create actually succeeded, so a partial failure neither reports
    # phantom mdevs nor orphans the ones that did get created (those are tracked
    # and the engine reconcile can fill the rest). Only a total failure errors.
    planned = []  # (entry_id, entry, create_cmd)
    first_err = None
    if is_vfio and sub_paths:
        # Vendor-specific VFIO framework: one vGPU per VF. Write the type-id to
        # each VF's current_vgpu_type (no mdev create, no UUID). The pool entry
        # is keyed by VF BDF. vf_cap caps the count for a MIG-backed carve; a
        # plain vGPU carves one per VF. (The card was already cleared to 0 above,
        # before type resolution, so every target VF is free to accept the type.)
        carve_vfs = sub_paths[:vf_cap] if vf_cap else sub_paths
        for vf_path in carve_vfs:
            vf_bdf = os.path.basename(vf_path)
            # **mig_meta tags MIG-backed vGPU entries (mig=True, mig_profile_id);
            # empty for a plain vGPU -- same contract as the legacy mdev carve.
            entry_id, entry = new_vfio_pool_entry(vf_bdf, type_id, **mig_meta)
            planned.append((entry_id, entry, _cmds.build_vgpu_set_cmd(vf_bdf, type_id)))
    elif sub_paths:
        # A MIG-backed vGPU carves exactly `vf_cap` mdevs (one per GI); a plain
        # SR-IOV vGPU carves one per VF. mig_meta tags MIG entries (mig=True,
        # mig_profile_id) so the engine emits display='off' for them.
        carve_vfs = sub_paths[:vf_cap] if vf_cap else sub_paths
        # Read each VF's available_instances for this type first: a VF reporting
        # 0 has no backing GPU-instance (a racy/short MIG carve, or SR-IOV not
        # settled) so its create would fail -- skip it with a precise reason
        # instead of an opaque create stderr. Unreadable (attr absent / older
        # driver) -> "x", treated as usable (unchanged behaviour).
        avail_res = (
            run(
                [
                    f"cat '{vf}/mdev_supported_types/{type_id}/available_instances' "
                    "2>/dev/null || echo x"
                    for vf in carve_vfs
                ],
                timeout=30,
            )
            or []
        )
        for idx, vf_path in enumerate(carve_vfs):
            out = (avail_res[idx].get("out") if idx < len(avail_res) else "") or ""
            out = out.strip()
            if out.isdigit() and int(out) == 0:
                first_err = first_err or (
                    f"available_instances=0 on {os.path.basename(vf_path)} "
                    f"(no backing GPU-instance for {type_id})"
                )
                continue
            uuid, entry = new_mdev_pool_entry(
                os.path.basename(vf_path), type_id, **mig_meta
            )
            planned.append((uuid, entry, build_mdev_create_cmd(vf_path, type_id, uuid)))
    else:
        for _ in range(_pool_size(pci_bdf, wanted)):
            uuid, entry = new_mdev_pool_entry(pci_bdf, type_id, **mig_meta)
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
    for (uuid, entry, _), res in zip(planned, results):
        err = (res.get("err") or "").strip()
        if err:
            first_err = first_err or err
            continue
        mdevs[wanted][uuid] = entry
    if not mdevs[wanted]:
        return {}, f"mdev create failed: {(first_err or 'no mdev created')[:160]}"
    # A MIG-backed vGPU must carve EXACTLY `vf_cap` slices (one mdev per +gfx
    # GPU-instance). A short carve means some GIs/VFs didn't materialise (e.g. a
    # racy SR-IOV re-enable) -> the pool would be silently under-provisioned yet
    # reported "applied". Error the card so the engine reconcile retries from
    # live state instead of publishing a partial MIG pool. (Plain vGPU keeps the
    # lenient behaviour: a partial SR-IOV carve is topped up by the reconcile.)
    if mig_meta.get("mig") and vf_cap and len(mdevs[wanted]) < vf_cap:
        return {}, (
            f"MIG vGPU {wanted}: carved {len(mdevs[wanted])}/{vf_cap} slices "
            f"(GPU-instances incomplete){': ' + first_err[:120] if first_err else ''}"
        )
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
        # Nothing was applied, but the live UUID set may have drifted from the DB
        # (same profile, but discovery re-carved or a hypervisor-container recreate
        # minted a fresh set). Report the LIVE pool so the API re-pins the DB to
        # reality (r.literal replace). Carry the set of UUIDs a desktop is ACTUALLY
        # running on right now (running_mdev_uuids) so the ingest re-adopts
        # domain_started ONLY for those -- never on a stale DB flag, and never at
        # startup (the entrypoint already killed leftover qemu, so the set is
        # empty -> clean slate). _live_mdev_pool returns None (-> timestamp-only)
        # for passthrough/MIG_CURRENT or an empty card, so those keep prior
        # behaviour and we skip the (then unused) running-uuid virsh probe.
        live_pool = _live_mdev_pool(pci_bdf, run, current, gpu, gpu.get("sub_paths"))
        return _report(
            pci_bdf,
            action,
            applied=current,
            previous=current,
            binding=driver,
            mig_mode=mig_mode,
            mdevs=live_pool,
            running_mdev_uuids=(
                sorted(_running_mdev_uuids(run)) if live_pool else None
            ),
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
        if is_vgpu:
            # Confirm the carve materialised. The vendor-specific VFIO framework
            # has no mdevs -- count VFs with current_vgpu_type != 0 instead.
            if gpu.get("framework") == FRAMEWORK_VFIO_VARIANT:
                live = _live_vgpu_count(gpu.get("sub_paths"), run)
            else:
                live = _live_mdev_count(pci_bdf, run, gpu.get("sub_paths"))
            if live == 0:
                last_error = f"vGPU {wanted} carve did not materialise (no live vGPU)"
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
