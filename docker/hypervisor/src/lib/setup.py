import fcntl
import json
import logging
import os
import sys
import traceback
from distutils.util import strtobool
from importlib.machinery import SourceFileLoader
from pprint import pprint
from time import monotonic, sleep

from api_client import ApiClient
from gpu_discovery import (
    discover_gpus,
    discover_hugepages,
    discover_numa_topology,
    discover_pci_devices,
    ensure_sriov_vfs,
)
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
    SourceFileLoader("storage_pool", "/src/_common/default_storage_pool.py")
    .load_module()
    .DEFAULT_STORAGE_POOL_ID
)

# Instantiate connection
try:
    apic = ApiClient()
except:
    raise

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
    nvidia_gpus = _discover_gpus_locked()

    HYPERVISOR = {
        "hyper_id": os.environ.get("HYPER_ID", "isard-hypervisor"),
        "hostname": hostname,
        "port": "2022",
        "cap_disk": bool(strtobool(os.environ.get("CAPABILITIES_DISK", "true"))),
        "cap_hyper": bool(strtobool(os.environ.get("CAPABILITIES_HYPER", "true"))),
        "enabled": False,
        "description": "Added through api",
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
        "nvidia_gpus": json.dumps(nvidia_gpus),
        "nvidia_enabled": False,  # Will be set below based on discovery
        "hugepages_info": json.dumps(discover_hugepages()),
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
    }

    gpu_list = nvidia_gpus
    HYPERVISOR["nvidia_enabled"] = len(gpu_list) > 0
    HYPERVISOR["pci_devices"] = json.dumps(discover_pci_devices(gpu_list))
    HYPERVISOR["numa_topology"] = json.dumps(discover_numa_topology())
    # This hypervisor can apply GPU profiles locally at registration, so the API
    # returns per-card targets (gpu_targets) in the response. Old hypervisors
    # omit this flag and the engine keeps applying as before.

    ## Adding hyper. Received dict with certs and number
    ok = False
    while not ok:
        try:
            data = apic.post("hypervisor", data=HYPERVISOR)
            if not data:
                print("Api does not answer OK... retrying...")
                sleep(2)
                continue
        except:
            print("Could not contact api to register me... retrying...")
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
        gpu_targets = data.get("gpu_targets")
        if gpu_targets is not None:
            applied = _apply_gpus_locked(nvidia_gpus, gpu_targets)
            apic.update(
                "hypervisor/" + HYPERVISOR["hyper_id"] + "/gpu_applied",
                data={"applied": json.dumps(applied)},
            )
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

    ## Save VPN tunneling mode from API response for use by start.sh
    vpn_tunneling_mode = data.get("vpn", {}).get("tunneling_mode", "wireguard+geneve")
    print(f"VPN tunneling mode from API: {vpn_tunneling_mode}")
    with open("/tmp/vpn_tunneling_mode", "w") as f:
        f.write(vpn_tunneling_mode)

    ## Save infrastructure MTU from API response for OVS setup
    infra_mtu = data.get("vpn", {}).get("infrastructure_mtu", "")
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
    try:
        return apic.delete(
            "hypervisor/" + os.environ.get("HYPER_ID", "isard-hypervisor")
        )
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
        apic.update(
            "hypervisor/" + hyper_id,
            data={"numa_topology": json.dumps(topo), "enabled": True},
        )
        print(
            f"NUMA refresh: libvirt_numa_ok={topo.get('libvirt_numa_ok')} "
            f"reason={topo.get('reason')} nodes={list(topo.get('nodes', {}).keys())}"
        )
    except Exception as e:
        print(f"NUMA refresh: failed to update hypervisor record: {e}")


def EnableHypervisor():
    _refresh_numa_topology_with_libvirt()
    data = {"enabled": True}
    ok = False
    while not ok:
        try:
            enabled = apic.update(
                "hypervisor/" + os.environ.get("HYPER_ID", "isard-hypervisor"),
                data=data,
            )
            ok = True
        except:
            print("Could not contact api to enable me... retrying...")
            sleep(1)
    return enabled


def DisableHypervisor():
    data = {"enabled": False}
    ok = False
    while not ok:
        try:
            enabled = apic.update(
                "hypervisor/" + os.environ.get("HYPER_ID", "isard-hypervisor"),
                data=data,
            )
            ok = True
        except:
            print("Could not contact api to disable me... retrying...")
            sleep(1)
    return enabled
