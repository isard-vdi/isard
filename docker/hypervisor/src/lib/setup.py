import fcntl
import json
import logging
import os
import sys
import traceback
from importlib.machinery import SourceFileLoader
from pprint import pprint
from time import monotonic, sleep


def strtobool(val):
    """Replacement for ``distutils.util.strtobool``, removed in Python 3.12.

    Returns 1 for truthy strings ('y', 'yes', 'true', 't', '1', 'on'),
    0 for falsy ('n', 'no', 'false', 'f', '0', 'off'). Raises ValueError
    on anything else, matching the legacy contract.
    """
    val = (val or "").strip().lower()
    if val in {"y", "yes", "t", "true", "on", "1"}:
        return 1
    if val in {"n", "no", "f", "false", "off", "0"}:
        return 0
    raise ValueError(f"invalid truth value: {val!r}")


from gpu_discovery import (
    discover_gpus,
    discover_hugepages,
    discover_numa_topology,
    discover_pci_devices,
    ensure_sriov_vfs,
)
from isardvdi_apiv4_client.api.role_admin import (
    admin_hypervisor_create,
    admin_hypervisor_delete,
    admin_hypervisor_enable,
    admin_hypervisor_gpu_applied,
)
from isardvdi_apiv4_client.models import (
    AdminGpuAppliedRequest,
    AdminHypervisorCreateData,
    AdminHypervisorEnableData,
    AdminHypervisorEnableDataNumaTopology,
)
from isardvdi_apiv4_client_auth import ApiV4Error, build_client, raise_for_status
from progress import report_progress

# Surface this entrypoint's own progress logs to stdout (docker logs). The
# gpu_discovery module configures its own handler; this covers setup.py.
logging.basicConfig(
    level=os.environ.get("HYPERVISOR_LOG_LEVEL", "INFO"),
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("hypervisor.setup")

# Serializes GPU discovery/reset across concurrent `hypervisor.py setup`
# invocations (the engine re-runs setup over SSH while the hyp is
# unregistered). Without it, parallel GPU resets race and pile up stuck
# nvidia-smi -r processes — itself a source of the "VFs busy" anomaly.
SETUP_GPU_LOCK = "/run/isard-hyp-setup.lock"

DEFAULT_STORAGE_POOL_ID = (
    SourceFileLoader(
        "storage_pool", "/src/isardvdi_common/helpers/default_storage_pool.py"
    )
    .load_module()
    .DEFAULT_STORAGE_POOL_ID
)

flavour = os.environ.get("FLAVOUR", False)
## We only check the flavours that have hypervisor:
## all-in-one, hypervisor, hypervisor-standalone
if str(flavour) == "all-in-one" or not flavour:
    hostname = "isard-hypervisor"
    static_url = os.environ.get("DOMAIN")
    video_domain = os.environ.get("DOMAIN")
    proxy_hyper_url = "isard-hypervisor"
if str(flavour) == "hypervisor":
    hostname = os.environ.get("DOMAIN")
    static_url = os.environ.get("STATIC_DOMAIN")
    video_domain = os.environ.get("VIDEO_DOMAIN")
    proxy_hyper_url = "isard-hypervisor"
if str(flavour) == "hypervisor-standalone":
    hostname = os.environ.get("DOMAIN")
    static_url = os.environ.get("STATIC_DOMAIN")
    video_domain = os.environ.get("VIDEO_DOMAIN")
    proxy_hyper_url = os.environ.get("DOMAIN")

isard_hyper_vpn_host = os.environ.get("VPN_DOMAIN", "isard-vpn")


def _detect_kvm_module():
    """Read /proc/modules to identify the loaded KVM module.

    Returns "intel" / "amd" when kvm_intel or kvm_amd is loaded,
    "bios_disabled" when only the generic kvm module is present (BIOS has
    virtualisation extensions disabled), and "false" otherwise. Engine
    uses this string verbatim as the gate that decides whether the
    hypervisor can come Online.
    """
    try:
        with open("/proc/modules") as fh:
            modules = {line.split(" ", 1)[0] for line in fh if line.strip()}
    except OSError:
        return "false"
    if "kvm_intel" in modules:
        return "intel"
    if "kvm_amd" in modules:
        return "amd"
    if "kvm" in modules:
        return "bios_disabled"
    return "false"


def _detect_nested_virtualization():
    """Read kvm_intel / kvm_amd nested parameter from sysfs."""
    for path in (
        "/sys/module/kvm_intel/parameters/nested",
        "/sys/module/kvm_amd/parameters/nested",
    ):
        try:
            with open(path) as fh:
                value = fh.read().strip()
        except OSError:
            continue
        return value[:1] in ("1", "Y")
    return False


def _discover_gpus_locked():
    """Run SR-IOV enablement + GPU discovery under an exclusive lock.

    Holds ``SETUP_GPU_LOCK`` so a second concurrent ``hypervisor.py setup``
    (the engine re-runs it over SSH while the hyp is unregistered) does not race
    GPU resets. Reports a boot-progress step so the admin UI is not blank during
    the sometimes-long discovery, and an error step if it raises. Returns the
    list of discovered GPU dicts.
    """
    report_progress(0, 9, "GPU/hardware discovery")
    try:
        lock_f = open(SETUP_GPU_LOCK, "w")
    except OSError as e:
        log.warning(
            "Could not open GPU setup lock %s (%s); proceeding without it",
            SETUP_GPU_LOCK,
            e,
        )
        lock_f = None
    t0 = monotonic()
    try:
        if lock_f is not None:
            try:
                fcntl.flock(lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                log.warning(
                    "Another hypervisor setup holds %s — waiting for it to "
                    "finish before GPU discovery (avoids racing concurrent GPU "
                    "resets)...",
                    SETUP_GPU_LOCK,
                )
                fcntl.flock(lock_f, fcntl.LOCK_EX)
        log.info("Enabling SR-IOV VFs where needed...")
        ensure_sriov_vfs()
        log.info(
            "Starting GPU discovery (can be slow on vGPU hosts; see per-GPU "
            "logs below)..."
        )
        nvidia_gpus = discover_gpus()
        log.info(
            "GPU discovery complete: %d GPU(s) in %.1fs",
            len(nvidia_gpus),
            monotonic() - t0,
        )
        return nvidia_gpus
    except Exception:
        report_progress(
            0, 9, "GPU/hardware discovery", error=traceback.format_exc()[-800:]
        )
        raise
    finally:
        if lock_f is not None:
            try:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
            finally:
                lock_f.close()


def _apply_gpus_locked(nvidia_gpus, targets):
    """Apply the API's per-card target profiles locally, under the SAME
    exclusive lock _discover_gpus_locked uses so a concurrent setup cannot race
    driver swaps. Returns the applied-state report {pci_bus_id: {...}}.

    Reports per-card boot progress so the admin UI is not stuck on
    "GPU/hardware discovery" for the whole (sometimes multi-minute) apply: each
    card updates the boot_progress label + timestamp as it is carved."""
    import gpu_apply

    def _report_apply_progress(idx, total, pci_bdf, wanted):
        report_progress(
            0,
            9,
            f"Applying GPU profiles ({idx}/{total}): {pci_bdf} -> {wanted}",
        )

    try:
        lock_f = open(SETUP_GPU_LOCK, "w")
    except OSError:
        lock_f = None
    try:
        if lock_f is not None:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
        return gpu_apply.apply_targets(
            nvidia_gpus, targets, progress=_report_apply_progress
        )
    finally:
        if lock_f is not None:
            try:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
            finally:
                lock_f.close()


def SetupHypervisor():
    log.info(
        "Hypervisor setup starting (hyper_id=%s)",
        os.environ.get("HYPER_ID", "isard-hypervisor"),
    )
    # GPU discovery runs unconditionally (the GPU_NVIDIA_SCAN opt-in gate
    # was dropped on this branch) and now goes through the upstream locked
    # helper: SR-IOV enablement + discovery under SETUP_GPU_LOCK with boot
    # progress reporting. A discovery failure aborts registration loudly --
    # registering half-discovered hides cards and skips the local apply.
    nvidia_gpus = _discover_gpus_locked()
    nvidia_enabled = bool(nvidia_gpus)

    # Sysfs-only discovery (no libvirt required, runs before libvirtd). The
    # engine balancer reads ``pci_devices[<sysfs-bdf>].numa_node`` to set
    # ``gpu_numa_node`` on gpu_selected, and ``hugepages_info`` to gate
    # ``<memoryBacking><hugepages/>`` emission and pick the NUMA-local node
    # for non-GPU desktops. Both are best-effort: a failure here must not
    # block registration.
    hugepages_info = None
    try:
        hugepages_info = discover_hugepages()
    except Exception as exc:
        print(f"discover_hugepages failed: {type(exc).__name__}: {exc}")
        traceback.print_exc()
    pci_devices = None
    try:
        pci_devices = discover_pci_devices(nvidia_gpus)
    except Exception as exc:
        print(f"discover_pci_devices failed: {type(exc).__name__}: {exc}")
        traceback.print_exc()

    HYPERVISOR = {
        "hyper_id": os.environ.get("HYPER_ID", "isard-hypervisor"),
        "hostname": hostname,
        "port": "2022",
        "cap_disk": bool(strtobool(os.environ.get("CAPABILITIES_DISK", "true"))),
        "cap_hyper": bool(strtobool(os.environ.get("CAPABILITIES_HYPER", "true"))),
        "enabled": False,
        "description": "Added through api",
        "kvm_module": _detect_kvm_module(),
        "nested": _detect_nested_virtualization(),
        "browser_port": (
            os.environ["VIEWER_BROWSER"]
            if os.environ.get("VIEWER_BROWSER", False)
            else "443"
        ),
        "spice_port": (
            os.environ["VIEWER_SPICE"]
            if os.environ.get("VIEWER_SPICE", False)
            else "80"
        ),
        "isard_static_url": static_url,
        "isard_video_url": video_domain,
        "isard_proxy_hyper_url": proxy_hyper_url,
        "isard_hyper_vpn_host": isard_hyper_vpn_host,
        "only_forced": json.loads(os.environ.get("ONLY_FORCED_HYP", "false").lower()),
        "nvidia_enabled": nvidia_enabled,
        "nvidia_gpus": nvidia_gpus,
        "force_get_hyp_info": (
            True if os.environ.get("GPU_NVIDIA_RESCAN") == "true" else False
        ),
        "min_free_mem_gb": os.environ.get("HYPER_FREEMEM", "0"),
        "min_free_gpu_mem_gb": os.environ.get("GPU_ONLY_MEM", "0"),
        "storage_pools": os.environ.get(
            "CAPABILITIES_STORAGE_POOLS", DEFAULT_STORAGE_POOL_ID
        ),
        "virt_pools": os.environ.get(
            "CAPABILITIES_VIRT_POOLS",
            os.environ.get("CAPABILITIES_STORAGE_POOLS", DEFAULT_STORAGE_POOL_ID),
        ),
        "buffering_hyper": json.loads(
            os.environ.get("BUFFERING_HYPER", "false").lower()
        ),
        "gpu_only": True if os.environ.get("GPU_ONLY") == "true" else False,
        "hugepages_info": hugepages_info,
        "pci_devices": pci_devices,
    }

    ## Adding hyper. Received dict with certs and number
    ok = False
    data = None
    while not ok:
        try:
            with build_client("isard-hypervisor", role="hypervisor") as client:
                body = AdminHypervisorCreateData.from_dict(HYPERVISOR)
                resp = admin_hypervisor_create.sync_detailed(client=client, body=body)
                raise_for_status(resp)
                data = resp.parsed
            if not data:
                print("Api does not answer OK... retrying...")
                sleep(2)
                continue
        except ApiV4Error as e:
            # Log the typed apiv4 error: status code + body. Surfaces
            # 4xx/5xx from /admin/item/hypervisor (e.g. KeyError on partial
            # rows, schema validation 422, ssh-keyscan 500) instead of
            # the misleading "Could not contact api" — which only used
            # to be true when the apiv4 socket itself was unreachable.
            print(f"Failed to register hypervisor (apiv4 error): {e}. Retrying...")
            sleep(2)
            continue
        except Exception as e:
            print(
                f"Failed to register hypervisor: {type(e).__name__}: {e}. Retrying..."
            )
            traceback.print_exc()
            sleep(2)
            continue
        if not data["certs"]["ca-cert.pem"]:
            print("Certificate not found in main isard host.")
            sleep(2)
        else:
            ok = True

    ## Apply the per-card GPU target profiles the API returned locally, then
    ## report the applied state back so the API/engine DB reflects reality and
    ## the engine reconcile confirms instead of re-applying. Best-effort: any
    ## failure (or an old API that returns no gpu_targets) falls back to the
    ## engine applying, exactly as before.
    try:
        # `data` is the generated client's parsed model; gpu_targets is an
        # undeclared extra (extra="allow"), exposed via subscript -- not .get().
        try:
            gpu_targets = data["gpu_targets"]
        except (KeyError, TypeError):
            gpu_targets = None
        if gpu_targets is not None:
            applied = _apply_gpus_locked(nvidia_gpus, gpu_targets)
            with build_client("isard-hypervisor", role="hypervisor") as client:
                resp = admin_hypervisor_gpu_applied.sync_detailed(
                    HYPERVISOR["hyper_id"],
                    client=client,
                    body=AdminGpuAppliedRequest.from_dict({"applied": applied}),
                )
                raise_for_status(resp)
    except Exception:
        print("GPU target apply/report-back failed (engine will reconcile):")
        print(traceback.format_exc())

    ## Check if certificates have changed and needs updating
    try:
        update = False
        with open("/etc/pki/libvirt-spice/ca-cert.pem", "r") as clientcert:
            if clientcert.read() not in data["certs"]["ca-cert.pem"]:
                print("ca-cert differs from existing one, needs updating.")
                update = True
            else:
                print("Viewers certificates seem to be ok.")
        with open("/root/.ssh/authorized_keys", "r") as hostkey:
            if hostkey.read() not in data["certs"]["id_rsa.pub"]:
                print("id_rsa key differs from existing one, needs updating")
                update = True
            else:
                print("Authorized key from engine seem to be ok.")
    except:
        print("New certificates found so updating it from main isard...")
        update = True

    ## Updating certificates if needed
    try:
        if update:
            print("Updating viewer certificates from main isard host...")
            for k, v in data["certs"].items():
                if k == "id_rsa.pub":
                    with open("/root/.ssh/authorized_keys", "w") as f:
                        f.write(v)
                else:
                    with open("/etc/pki/libvirt-spice/" + k, "w") as f:
                        f.write(v)
    except:
        raise

    ## Save VPN tunneling mode + infrastructure MTU from the API response
    ## for use by start.sh / OVS setup. start.sh reads
    ## /tmp/vpn_tunneling_mode and otherwise defaults to "wireguard+geneve";
    ## on geneve-only infrastructure (no WireGuard hyper peer) that default
    ## makes the hypervisor take the wg VPNc path and fail. main writes
    ## these files; apiv4-integration lost the write side while keeping the
    ## read side in start.sh.
    ##
    ## NOTE: unlike main (where `data` is the raw JSON dict), here `data` is
    ## the generated apiv4 client's parsed model. The server returns `vpn`
    ## as an undeclared extra (AdminHypervisorCreateResponse has
    ## extra="allow"); the client exposes it via __getitem__ (subscript),
    ## not dict .get() — so `data.get("vpn")` would always miss it. Access
    ## by subscript with a safe fallback, mirroring the existing
    ## `data["certs"]` usage above.
    try:
        vpn_info = data["vpn"] or {}
    except (KeyError, TypeError):
        vpn_info = {}
    vpn_tunneling_mode = vpn_info.get("tunneling_mode", "wireguard+geneve")
    print(f"VPN tunneling mode from API: {vpn_tunneling_mode}")
    with open("/tmp/vpn_tunneling_mode", "w") as f:
        f.write(vpn_tunneling_mode)

    infra_mtu = vpn_info.get("infrastructure_mtu", "")
    if infra_mtu:
        print(f"Infrastructure MTU from API: {infra_mtu}")
        with open("/tmp/infrastructure_mtu", "w") as f:
            f.write(str(infra_mtu))


def DeleteHypervisor():
    """Best-effort API unregister. Bounded: one attempt, logged on failure.

    The old unbounded retry loop blocked shutdown indefinitely if the API
    was unreachable — docker's stop_grace_period would then SIGKILL us
    before any cleanup ran. Shutdown is handled by lib/shutdown.py now
    (with its own timeout-bounded DELETE), so this function is only left
    as a CLI entry point for manual operator use.
    """
    hyper_id = os.environ.get("HYPER_ID", "isard-hypervisor")
    try:
        with build_client("isard-hypervisor", role="hypervisor") as client:
            resp = admin_hypervisor_delete.sync_detailed(
                client=client, hyper_id=hyper_id
            )
            raise_for_status(resp)
            return resp.parsed
    except Exception as e:
        print(f"Could not contact api to delete me: {e}")
        return False


def _refresh_numa_topology_with_libvirt():
    """Re-run NUMA discovery now that libvirtd is up and publish to the API.

    SetupHypervisor() runs before libvirtd starts, so its numa_topology is
    sysfs-only with libvirt_numa_ok=False. This runs at enable time and
    publishes the validated topology (libvirt_numa_ok=True when libvirt's
    NUMA view matches sysfs, False otherwise — engine gates <numatune> on
    that flag).
    """
    try:
        topo = discover_numa_topology(probe_libvirt=True)
    except Exception as e:
        print(f"NUMA refresh: discovery failed: {e}")
        return
    if not topo:
        return
    hyper_id = os.environ.get("HYPER_ID", "isard-hypervisor")
    try:
        # The generated client's ``AdminHypervisorEnableData.to_dict``
        # calls ``self.numa_topology.to_dict()``, so passing a raw dict
        # raises ``AttributeError: 'dict' object has no attribute
        # 'to_dict'``. Wrap via the typed helper that the codegen
        # produced from the same OpenAPI schema.
        numa_topology = AdminHypervisorEnableDataNumaTopology.from_dict(topo)
        with build_client("isard-hypervisor", role="hypervisor") as client:
            resp = admin_hypervisor_enable.sync_detailed(
                client=client,
                hyper_id=hyper_id,
                body=AdminHypervisorEnableData(
                    enabled=True, numa_topology=numa_topology
                ),
            )
            raise_for_status(resp)
        print(
            f"NUMA refresh: libvirt_numa_ok={topo.get('libvirt_numa_ok')} "
            f"reason={topo.get('reason')} nodes={list(topo.get('nodes', {}).keys())}"
        )
    except Exception as e:
        print(f"NUMA refresh: failed to update hypervisor record: {e}")


def EnableHypervisor():
    _refresh_numa_topology_with_libvirt()
    return _set_enabled(True)


def DisableHypervisor():
    return _set_enabled(False)


def _set_enabled(enabled):
    hyper_id = os.environ.get("HYPER_ID", "isard-hypervisor")
    action = "enable" if enabled else "disable"
    ok = False
    result = None
    while not ok:
        try:
            with build_client("isard-hypervisor", role="hypervisor") as client:
                resp = admin_hypervisor_enable.sync_detailed(
                    client=client,
                    hyper_id=hyper_id,
                    body=AdminHypervisorEnableData(enabled=enabled),
                )
                raise_for_status(resp)
                result = resp.parsed
            ok = True
        except Exception:
            print(f"Could not contact api to {action} me... retrying...")
            sleep(1)
    return result
