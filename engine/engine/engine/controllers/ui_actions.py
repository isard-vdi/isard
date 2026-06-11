# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from time import sleep

from cachetools import TTLCache, cached
from isardvdi_common.helpers.xml_compression import compress_xml, decompress_xml
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.storage import Storage
from rethinkdb import r

from engine.models.domain_xml import (
    BUS_TYPES,
    add_iothread_pinning,
    add_memory_backing,
    add_numa_pinning,
    add_qemu_pcie_reserve,
    count_passthrough_gpus_in_xml,
    hostdev_locked,
    numa_opts_allowed,
    pinned_cpuset_from_xml,
    recreate_xml_if_gpu,
    recreate_xml_if_start_paused,
    recreate_xml_to_start,
    vcpus_from_xml,
)
from engine.services.db import (
    delete_domain,
    domains_with_attached_storage_id,
    get_dict_from_item_in_table,
    get_domain,
    get_domain_hyp_started,
    get_table_field,
    get_table_fields,
    insert_domain,
    rethink_conn,
    update_domain_status,
    update_table_field,
    update_vgpu_info_if_stopped,
    update_vgpu_uuid_domain_action,
)
from engine.services.db.storage_pool import get_category_storage_pool_id
from engine.services.log import *

DEFAULT_HOST_MODE = "host-passthrough"

# normal priority in PriorityQueueIsard is 100
# lower number => more priority
Q_PRIORITY_START = 50
Q_PRIORITY_STARTPAUSED = 60
Q_PRIORITY_STOP = 40  # Destroy
Q_PRIORITY_SHUTDOWN = 80  # Soft Shut-Down
Q_PRIORITY_PERSONAL_UNIT = 130  # Mount personal unit inside a desktop

Q_LONGOPERATIONS_PRIORITY_CREATE_DISK_FROM_TEMPLATE = 40
Q_LONGOPERATIONS_PRIORITY_DOMAIN_FROM_TEMPLATE = 40

# TTL cache for template lookups during batch domain creation
# Avoids repeated DB queries when creating many domains from the same template
_template_cache = TTLCache(maxsize=100, ttl=60)

# Thread pool for the async post-edit "Updating" → "Stopped" transition.
# Matches the apiv4-and-websockets pattern (updating_thread_pool in that
# branch's ui_actions.py).
updating_thread_pool = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="updating_domain"
)


@cached(cache=_template_cache)
def get_template_cached(template_id):
    """Get template domain with TTL caching for batch operations."""
    return get_domain(template_id)


class UiActions(object):
    def __init__(self, manager):
        log.info("Backend uiactions created")
        self.manager = manager

    ### STARTING DOMAIN
    def start_domain_from_id(self, id_domain, ssl=True, starting_paused=False):
        # INFO TO DEVELOPER, QUE DE UN ERROR SI EL ID NO EXISTE

        domain = get_table_fields(
            "domains",
            id_domain,
            [
                "kind",
                "name",
                "category",
                {
                    "create_dict": {
                        "hardware": "memory",
                        "reservables": True,
                        "xml_protected_sections": True,
                    }
                },
                "forced_hyp",
                "favourite_hyp",
                "hypervisors_pools",
                "force_gpus",
            ],
        )
        if not domain:
            log.error(f"Domain {id_domain} not found. Can't start. Maybe deleted?")
            return False

        if domain["kind"] != "desktop":
            log.error(
                f"DANGER, domain {id_domain} ({domain['name']}) is a template and can't be started"
            )
            update_domain_status(
                "Stopped",
                id_domain,
                detail="Template can not be started",
            )
            return False

        # Domain storage and storage pool
        if Domain.exists(id_domain):
            domain_obj = Domain(id_domain)
        else:
            update_domain_status(
                "Failed",
                id_domain,
                detail="Domain storage not found in database",
            )
            return False
        if not domain_obj.storage_ready:
            if any([s.status == "non_existing" for s in domain_obj.storages]):
                log.error(
                    f"Domain {id_domain} ({domain['name']}) storage non existing. Can't start."
                )
                update_domain_status(
                    "Failed",
                    id_domain,
                    detail=f"Desktop storage non existing",
                )
            else:
                update_domain_status(
                    "Stopped",
                    id_domain,
                    detail=f"Desktop storage not ready",
                )
            return False
        domain_storage_objs = domain_obj.storages
        if len(domain_storage_objs) == 0:
            update_domain_status(
                "Failed",
                id_domain,
                detail=f"Desktop has no storage",
            )
            return False
        domain_storage_pool_obj = domain_storage_objs[0].pool
        if not domain_storage_pool_obj:
            update_domain_status(
                "Stopped",
                id_domain,
                detail=f"Desktop storage pool not found",
            )
            return False
        domain_storage_pool_id = domain_storage_pool_obj.id

        # This pool will be always the same for virtualization, nothing to do with balancers
        try:
            pool_id = domain.get("hypervisors_pools", ["default"])[0]
        except:
            pool_id = "default"
            log.error(
                f"Domain {id_domain} has no hypervisors_pools. Using default pool."
            )

        cpu_host_model = self.manager.pools[pool_id].conf.get(
            "cpu_host_model", DEFAULT_HOST_MODE
        )

        # When the admin has locked the <hostdev> XML section
        # (create_dict.xml_protected_sections contains "hostdev"), the manual
        # passthrough entries are the sole source of truth: the engine must not
        # also reserve/inject a managed GPU, or recreate_xml_if_gpu would append
        # an extra balancer-selected <hostdev> on top of the locked ones (no
        # dedup). Treat such desktops as non-GPU for balancing/reservation.
        hostdev_section_locked = hostdev_locked(domain)
        if hostdev_section_locked:
            log.info(
                f"Domain {id_domain}: 'hostdev' XML section is admin-locked; "
                f"skipping managed GPU reservation/injection "
                f"(manual passthrough owns <hostdev>)"
            )
        reservables_eff = (
            None
            if hostdev_section_locked
            else domain.get("create_dict", {}).get("reservables", {})
        )
        force_gpus_eff = None if hostdev_section_locked else domain.get("force_gpus")

        # GPU desktops cannot use the paused-start flow: start_domain_from_xml
        # drops force_gpus/reservables when action == "start_paused_domain"
        # (see start_paused_domain_from_xml), which leaves the XML without the
        # <hostdev> GPU and clashes with virtiofs hugepages backing on the QXL.
        if starting_paused and (force_gpus_eff or (reservables_eff or {}).get("vgpus")):
            log.info(
                f"Domain {id_domain} has GPU configured; using normal start "
                f"flow instead of paused-start"
            )
            starting_paused = False

        start_error = "recreate_xml_to_start returned no XML"
        try:
            xml, viewer_passwd = recreate_xml_to_start(id_domain, ssl, cpu_host_model)
        except Exception as e:
            logs.exception_id.debug("0010")
            log.error("recreate_xml_to_start in domain {}".format(id_domain))
            log.error("Traceback: \n .{}".format(traceback.format_exc()))
            log.error("Exception message: {}".format(e))
            start_error = str(e)
            xml = False
            viewer_passwd = ""

        if xml is False:
            update_domain_status(
                "Failed",
                id_domain,
                detail=f"Engine failed to build XML for start: {start_error}",
            )
            return False
        else:
            domain_memory_kb = (
                domain.get("create_dict", {}).get("hardware", {}).get("memory", 1048576)
            )
            domain_memory_gb = domain_memory_kb / 1048576
            # Which engine start-time XML injections (hugepages/NUMA/iothreads)
            # are allowed — admin-locked sections must not be overwritten.
            numa_opts = numa_opts_allowed(domain)
            # Clean up any stale vGPU reservation before starting
            update_vgpu_info_if_stopped(id_domain)
            if starting_paused is True:
                hyp = self.start_paused_domain_from_xml(
                    xml,
                    id_domain,
                    pool_id=pool_id,
                    forced_hyp=domain.get("forced_hyp"),
                    favourite_hyp=domain.get("favourite_hyp"),
                    force_gpus=force_gpus_eff,
                    reservables=reservables_eff,
                    storage_pool_id=domain_storage_pool_id,
                    domain_memory_gb=domain_memory_gb,
                    viewer_passwd=viewer_passwd,
                    numa_opts=numa_opts,
                )
            else:
                hyp = self.start_domain_from_xml(
                    xml,
                    id_domain,
                    pool_id=pool_id,
                    forced_hyp=domain.get("forced_hyp"),
                    favourite_hyp=domain.get("favourite_hyp"),
                    force_gpus=force_gpus_eff,
                    reservables=reservables_eff,
                    storage_pool_id=domain_storage_pool_id,
                    domain_memory_gb=domain_memory_gb,
                    viewer_passwd=viewer_passwd,
                    numa_opts=numa_opts,
                )
            return hyp

    def start_paused_domain_from_xml(
        self,
        xml,
        id_domain,
        pool_id="default",
        forced_hyp=None,
        favourite_hyp=None,
        force_gpus=None,
        reservables=None,
        storage_pool_id=None,
        domain_memory_gb=1.0,
        viewer_passwd="",
        numa_opts=None,
    ):
        if storage_pool_id is None:
            # Domain storage and storage pool
            if Domain.exists(id_domain):
                domain_obj = Domain(id_domain)
            else:
                update_domain_status(
                    "Failed",
                    id_domain,
                    detail="Domain storage not found in database",
                )
                return False
            if not domain_obj.storage_ready:
                update_domain_status(
                    "Stopped",
                    id_domain,
                    detail=f"Desktop storage not ready",
                )
                return False
            domain_storage_objs = domain_obj.storages
            if len(domain_storage_objs) == 0:
                update_domain_status(
                    "Failed",
                    id_domain,
                    detail=f"Desktop has no storage",
                )
                return False
            domain_storage_pool_obj = domain_storage_objs[0].pool
            if not domain_storage_pool_obj:
                update_domain_status(
                    "Stopped",
                    id_domain,
                    detail=f"Desktop storage pool not found",
                )
                return False
            domain_storage_pool_id = domain_storage_pool_obj.id
        else:
            domain_storage_pool_id = storage_pool_id
        return self.start_domain_from_xml(
            xml,
            id_domain,
            pool_id,
            action="start_paused_domain",
            forced_hyp=forced_hyp,
            favourite_hyp=favourite_hyp,
            # We set force_gpus and reservables to None because we'll override all the
            # GPU configuration in order to be able to create GPU desktops without having
            # an hypervisor online hypervisor with GPUs
            force_gpus=None,
            reservables=None,
            storage_pool_id=domain_storage_pool_id,
            domain_memory_gb=domain_memory_gb,
            numa_opts=numa_opts,
        )

    def start_domain_from_xml(
        self,
        xml,
        id_domain,
        pool_id="default",
        action="start_domain",
        forced_hyp=None,
        favourite_hyp=None,
        force_gpus=None,
        reservables=None,
        storage_pool_id=None,
        domain_memory_gb=1.0,
        viewer_passwd="",
        numa_opts=None,
    ):
        failed = False
        if pool_id in self.manager.pools.keys():
            next_hyp = False
            extra_info = {}
            is_gpu = False
            max_attempts = 5
            # vCPU footprint, used to balance non-GPU desktops across NUMA nodes.
            domain_vcpus = vcpus_from_xml(xml)

            # A desktop may request several vGPU profiles. They MUST all land on
            # ONE hypervisor (a guest runs on a single host and can only attach
            # that host's devices) and on DISTINCT cards. Pin the host to the
            # first profile's selection, reserve+inject every profile there, and
            # roll back if any can't be placed. start_paused_domain intentionally
            # starts with no GPU (minimal memory), so it takes the non-GPU path.
            gpu_profiles = []
            if action != "start_paused_domain":
                gpu_profiles = list((reservables or {}).get("vgpus") or [])

            if not gpu_profiles:
                # Non-GPU path (or paused): a single hypervisor selection, no mdev.
                next_hyp, extra_info = self.manager.pools[
                    pool_id
                ].balancer.get_next_hypervisor(
                    forced_hyp=forced_hyp,
                    favourite_hyp=favourite_hyp,
                    reservables=reservables,
                    force_gpus=force_gpus,
                    storage_pool_id=storage_pool_id,
                    domain_memory_gb=domain_memory_gb,
                    domain_vcpus=domain_vcpus,
                )
                if action == "start_paused_domain":
                    extra_info = {}
                is_gpu = extra_info.get("nvidia", False) is True
            else:
                # GPU path: reserve EVERY requested profile on a single host.
                reserved = []  # [(gpu_id, uuid, profile)] for rollback
                pinned_hyp = list(forced_hyp) if forced_hyp else None
                primary_extra = None
                placement_failed = False
                # NUMA-aware placement: if the desktop pins its vCPUs, prefer
                # GPU cards on the matching NUMA node; then group every later
                # card on the first card's node so a multi-GPU guest is not
                # split across NUMA nodes. Both are preferences (the carve falls
                # back to any free card), so single-node hosts and cards with an
                # unknown numa_node behave exactly as before.
                prefer_cpuset = pinned_cpuset_from_xml(xml)
                group_node = None

                def _rollback_vgpus():
                    for _g, _u, _p in reserved:
                        try:
                            update_vgpu_uuid_domain_action(
                                _g,
                                _u,
                                "domain_stopped",
                                domain_id=id_domain,
                                profile=_p,
                            )
                        except Exception as _re:
                            log.error(
                                f"{id_domain}: rollback release failed for "
                                f"{_u}: {_re}"
                            )

                for guest_index, profile in enumerate(gpu_profiles):
                    per_reservables = {"vgpus": [profile]}
                    placed = False
                    # Retry per profile on a lost CAS (concurrent starters).
                    for attempt in range(max_attempts):
                        nh, ei = self.manager.pools[
                            pool_id
                        ].balancer.get_next_hypervisor(
                            forced_hyp=pinned_hyp if pinned_hyp else forced_hyp,
                            favourite_hyp=favourite_hyp,
                            reservables=per_reservables,
                            force_gpus=force_gpus,
                            storage_pool_id=storage_pool_id,
                            domain_memory_gb=domain_memory_gb,
                            domain_vcpus=domain_vcpus,
                            prefer_cpuset=prefer_cpuset,
                            prefer_numa_node=group_node,
                            # Co-locate a multi-profile guest: for the FIRST card
                            # (group_node still None) seed placement onto a socket
                            # every requested profile can share; ignored once
                            # group_node is set (prefer_numa_node wins downstream).
                            coplacement_profiles=gpu_profiles,
                        )
                        if nh is False or ei.get("nvidia", False) is not True:
                            # No card for this profile on the pinned host.
                            break
                        if pinned_hyp is None:
                            pinned_hyp = [nh]
                        elif nh not in pinned_hyp:
                            # Belt-and-suspenders: never split a guest across hosts.
                            log.error(
                                f"{id_domain}: profile {profile} resolved to host "
                                f"{nh} != pinned {pinned_hyp}; refusing cross-host GPU"
                            )
                            break
                        reserved_ok = update_vgpu_uuid_domain_action(
                            ei["gpu_id"],
                            ei["uid"],
                            "domain_reserved",
                            domain_id=id_domain,
                            profile=ei["profile"],
                        )
                        if not reserved_ok:
                            log.warning(
                                f"{id_domain}: vgpu reserve lost CAS on uuid "
                                f"{ei.get('uid')} (attempt {attempt + 1}/"
                                f"{max_attempts}); re-selecting"
                            )
                            continue
                        try:
                            xml = recreate_xml_if_gpu(
                                xml,
                                ei["uid"],
                                pci_bus_id=ei.get("pci_bus_id"),
                                is_passthrough=(ei.get("profile") == "passthrough"),
                                companion_pci_bdfs=ei.get("companion_pci_bdfs") or [],
                                is_mig=ei.get("mig", False),
                                guest_index=guest_index,
                            )
                        except ValueError as e:
                            log.error(
                                "{}: recreate_xml_if_gpu failed: {}".format(
                                    id_domain, e
                                )
                            )
                            update_vgpu_uuid_domain_action(
                                ei["gpu_id"],
                                ei["uid"],
                                "domain_stopped",
                                domain_id=id_domain,
                                profile=ei["profile"],
                            )
                            _rollback_vgpus()
                            update_domain_status(
                                "Failed",
                                id_domain,
                                detail="GPU XML injection failed: {}".format(e),
                            )
                            return False
                        if ei.get("profile") == "passthrough":
                            xml = add_qemu_pcie_reserve(xml)
                        reserved.append((ei["gpu_id"], ei["uid"], ei["profile"]))
                        if primary_extra is None:
                            primary_extra = ei
                        # Group any later card on this (first) card's NUMA node
                        # so the guest's GPUs stay on one node. Skip when the
                        # node is unknown (-1/None) — then later cards just take
                        # any free card, as before.
                        if group_node is None:
                            _nn = ei.get("gpu_numa_node")
                            if _nn is not None and int(_nn) >= 0:
                                group_node = int(_nn)
                        placed = True
                        break
                    if not placed:
                        placement_failed = True
                        break

                if placement_failed:
                    _rollback_vgpus()
                    update_domain_status(
                        "Failed",
                        id_domain,
                        detail=(
                            "Could not place all {} requested vGPU profiles on a "
                            "single hypervisor with distinct free cards".format(
                                len(gpu_profiles)
                            )
                        ),
                    )
                    return False

                is_gpu = True
                next_hyp = pinned_hyp[0]
                extra_info = primary_extra
            if next_hyp is not False:
                # Flag the slow-VFIO path so the worker can extend its
                # libvirt createXML timeout for this action (see
                # LIBVIRT_CREATEXML_TIMEOUT_GPU_SLOW). A GPU domain forced
                # onto 4K-page RAM routinely exceeds the 30s default.
                # Declared before the try block below so it stays visible
                # even if the optimization block bails out.
                expects_slow_createxml = False

                # --- Large-BAR multi-GPU PCIe reserve (best-effort) ---
                # A guest with >=2 passed-through GPUs (large BARs, e.g. RTX PRO
                # 6000) needs a bigger 64-bit prefetchable MMIO window on the PCIe
                # root ports, or the second card's BAR fails to map. The per-card
                # carve loop only covers engine-reserved profiles; this also covers
                # the manual-passthrough path (hostdevs baked into the XML, no
                # reservation). add_qemu_pcie_reserve is idempotent.
                try:
                    if count_passthrough_gpus_in_xml(xml) >= 2:
                        xml = add_qemu_pcie_reserve(xml)
                except Exception as _pref_err:
                    log.warning(
                        f"{id_domain}: pcie pref64-reserve check failed: "
                        f"{_pref_err}; continuing without it"
                    )

                # --- NUMA / hugepages optimizations (best-effort) ---
                # A failure anywhere in this block (bad topology data,
                # unexpected XML shape, missing fields) must never stop the
                # domain from starting — we fall back to the pre-optimization
                # XML and log a warning.
                _xml_before_opts = xml
                try:
                    # Admin-locked XML sections must not be overwritten by the
                    # engine's start-time hugepages/NUMA/iothread injection.
                    _allow = numa_opts or {
                        "memory_backing": True,
                        "cputune": True,
                        "numatune": True,
                        "iothreads": True,
                    }
                    # --- NUMA node selection ---
                    # The engine derives CPU pinning from the sysfs view (<cputune>
                    # and <vcpu cpuset='...'> reference CPU IDs, which libvirt
                    # sees correctly even when its capability XML is broken) —
                    # UNLESS the admin locked <cputune> via xml_protected_sections,
                    # in which case the editor's manual pinning is authoritative and
                    # must not be overwritten (see cputune_locked below).
                    # The libvirt_numa_ok flag only gates <numatune>: when False
                    # (libvirt-in-container reporting duplicate cell IDs, etc.),
                    # add_numa_pinning skips the memory-binding element so
                    # libvirt doesn't reject the domain. The kernel's first-touch
                    # policy then provides soft NUMA locality via the cpuset.
                    numa_topo = extra_info.get("numa_topology", {}) or {}
                    libvirt_numa_ok = bool(numa_topo.get("libvirt_numa_ok"))
                    numa_nodes = numa_topo.get("nodes", {}) or {}
                    numa_hp_free = extra_info.get("numa_hugepages_free_kb", {})
                    domain_memory_kb = domain_memory_gb * 1048576
                    target_node = None
                    mem_mode = "preferred"
                    if len(numa_nodes) > 1:
                        gpu_numa = extra_info.get("gpu_numa_node")
                        if is_gpu and gpu_numa is not None:
                            target_node = str(gpu_numa)
                            # Use strict only if this node has enough hugepages;
                            # fall back to preferred if the node is short so the
                            # kernel can pull from a remote node instead of failing.
                            node_free = numa_hp_free.get(target_node, 0)
                            if node_free >= domain_memory_kb:
                                mem_mode = "strict"
                            else:
                                mem_mode = "preferred"
                                if node_free > 0:
                                    log.info(
                                        f"{id_domain}: GPU NUMA node {target_node} has "
                                        f"{node_free}KB free < {domain_memory_kb}KB needed, "
                                        f"using preferred mode (may cross NUMA)"
                                    )
                        elif extra_info.get("selected_numa_node") in numa_nodes:
                            # Non-GPU: the balancer load-spreads desktops across
                            # nodes (per-node RAM+vCPU in-flight accounting) so they
                            # don't all pile on the node with most free hugepages.
                            target_node = extra_info["selected_numa_node"]
                        else:
                            # Fallback (paused start / balancer gave nothing): pick
                            # NUMA node with most free hugepages, or hash-distribute.
                            if numa_hp_free:
                                candidates = {
                                    n: free_kb
                                    for n, free_kb in numa_hp_free.items()
                                    if n in numa_nodes and free_kb >= domain_memory_kb
                                }
                                if candidates:
                                    target_node = max(candidates, key=candidates.get)
                                else:
                                    valid = {
                                        n: f
                                        for n, f in numa_hp_free.items()
                                        if n in numa_nodes
                                    }
                                    target_node = (
                                        max(valid, key=valid.get) if valid else "0"
                                    )
                            else:
                                node_keys = sorted(numa_nodes.keys())
                                node_idx = hash(id_domain) % len(node_keys)
                                target_node = node_keys[node_idx]
                            mem_mode = "preferred"

                    # --- Hugepages assignment ---
                    if is_gpu:
                        hugepages = extra_info.get("hugepages", {})
                        if hugepages.get("mounted"):
                            hp_free_kb = extra_info.get("hugepages_free_kb", 0)
                            if hp_free_kb >= domain_memory_kb:
                                if not _allow["memory_backing"]:
                                    pass  # memory_backing section is admin-locked
                                elif hugepages.get("1G", {}).get("total", 0) > 0:
                                    xml = add_memory_backing(xml, "1", "G")
                                elif hugepages.get("2M", {}).get("total", 0) > 0:
                                    xml = add_memory_backing(xml, "2", "M")
                            else:
                                log.warning(
                                    f"GPU desktop {id_domain}: hugepages free "
                                    f"{hp_free_kb}KB < needed {domain_memory_kb}KB, "
                                    f"starting with 4K pages (slower VFIO mapping)"
                                )
                                expects_slow_createxml = True
                        else:
                            # GPU start on a host without a mounted hugepages
                            # pool — 4K-page mapping is the only option.
                            expects_slow_createxml = True
                    else:
                        # Non-GPU: use hugepages as fallback when regular RAM is low
                        hugepages = extra_info.get("hugepages", {})
                        if hugepages.get("mounted"):
                            mem_available_kb = extra_info.get("mem_available_kb", 0)
                            hp_free_kb = extra_info.get("hugepages_free_kb", 0)
                            min_free_kb = (
                                int(extra_info.get("min_free_mem_gb", 0)) * 1048576
                            )
                            regular_available_kb = mem_available_kb

                            if regular_available_kb - domain_memory_kb < min_free_kb:
                                if (
                                    _allow["memory_backing"]
                                    and hp_free_kb >= domain_memory_kb
                                ):
                                    if hugepages.get("1G", {}).get("total", 0) > 0:
                                        xml = add_memory_backing(xml, "1", "G")
                                    elif hugepages.get("2M", {}).get("total", 0) > 0:
                                        xml = add_memory_backing(xml, "2", "M")

                    # --- NUMA CPU pinning + IO thread pinning ---
                    # Honor an admin-locked CPU pinning: when the desktop protects
                    # <cputune> in its XML editor, the manual pinning is the source
                    # of truth (the GPU carve already prefers a card on the pinned
                    # node, see prefer_cpuset). Don't overwrite it here.
                    cputune_locked = "cputune" in (
                        (get_domain(id_domain) or {})
                        .get("create_dict", {})
                        .get("xml_protected_sections", [])
                        or []
                    )
                    if cputune_locked:
                        log.info(
                            f"{id_domain}: <cputune> is admin-protected; keeping the "
                            f"manual CPU pinning (skipping engine NUMA pinning)"
                        )
                    elif target_node is not None and target_node in numa_nodes:
                        cpulist = numa_nodes[target_node].get("cpulist", "")
                        if cpulist:
                            from io import StringIO

                            from lxml import etree

                            _tree = etree.parse(StringIO(xml))
                            _vcpu_elem = _tree.xpath("/domain/vcpu")
                            _vcpus = (
                                int(_vcpu_elem[0].text)
                                if _vcpu_elem and _vcpu_elem[0].text
                                else 1
                            )
                            xml = add_numa_pinning(
                                xml,
                                int(target_node),
                                cpulist,
                                _vcpus,
                                memory_mode=mem_mode,
                                emit_numatune=(libvirt_numa_ok and _allow["numatune"]),
                                emit_cputune=_allow["cputune"],
                            )
                            if _allow["iothreads"]:
                                xml = add_iothread_pinning(xml, cpulist)
                    log.info(
                        f"{id_domain}: NUMA placement -> is_gpu={is_gpu} "
                        f"gpu_numa={extra_info.get('gpu_numa_node')} "
                        f"target_node={target_node} mem_mode={mem_mode} "
                        f"hugepages={'yes' if '<hugepages>' in xml else 'no'} "
                        f"selected_numa_node={extra_info.get('selected_numa_node')}"
                    )
                except Exception as _opt_err:
                    log.warning(
                        f"NUMA/hugepages optimizations failed for {id_domain}: "
                        f"{_opt_err}; starting without them"
                    )
                    xml = _xml_before_opts

                if LOG_LEVEL == "DEBUG":
                    print(f"%%%% DOMAIN: {id_domain} -- action: {action} %%%%")
                    print(
                        f"%%%% DOMAIN: {id_domain} -- XML TO START IN HYPERVISOR: {next_hyp} %%%%"
                    )
                    print(xml)
                    print(
                        "%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%"
                    )

                dict_action = {
                    "type": action,
                    "xml": xml,
                    "id_domain": id_domain,
                    "viewer_passwd": viewer_passwd,
                }

                if extra_info.get("nvidia", False) is True:
                    dict_action["nvidia_uid"] = extra_info.get("uid", False)
                    dict_action["profile"] = extra_info.get("profile", False)
                    dict_action["vgpu_id"] = extra_info["gpu_id"]
                    dict_action["pci_bus_id"] = extra_info.get("pci_bus_id")
                    dict_action["companion_pci_bdfs"] = (
                        extra_info.get("companion_pci_bdfs") or []
                    )

                if expects_slow_createxml:
                    dict_action["expects_slow_createxml"] = True

                priority = Q_PRIORITY_START

                if action == "start_paused_domain":
                    # start_paused only with 256 of memory
                    dict_action["xml"] = recreate_xml_if_start_paused(xml)
                    update_domain_status(
                        status="CreatingDomain",
                        id_domain=id_domain,
                        hyp_id=False,
                        detail="Waiting to try starting paused in hypervisor {} in pool {} ({} operations in queue)".format(
                            next_hyp, pool_id, self.manager.q.workers[next_hyp].qsize()
                        ),
                    )
                    priority = Q_PRIORITY_STARTPAUSED

                self.manager.q.workers[next_hyp].put(dict_action, priority)

            else:
                logs.main.error(
                    f"desktop not started: no hypervisors online in pool {pool_id} with storage pool {storage_pool_id}"
                )
                failed = True
        else:
            log.error("pool_id {} does not exists??".format(pool_id))
            failed = True

        if failed is True:
            if (
                reservables
                and reservables.get("vgpus")
                and len(reservables.get("vgpus", []))
            ):
                gpu_profiles = reservables.get("vgpus", [])
                # A GPU start can fail to place because the card it needs is
                # mid profile-change (the placement query skips a card whose
                # changing_to_profile is set). That is TRANSIENT, not a real
                # failure: leave the desktop Stopped (not Failed) with a retry
                # hint so the user / autostart / scheduler can try again once
                # the new profile is up, instead of stranding it Failed.
                from engine.services.db.domains import any_vgpu_changing_profile

                if any_vgpu_changing_profile():
                    update_domain_status(
                        status="Stopped",
                        id_domain=id_domain,
                        hyp_id=False,
                        detail=(
                            "GPU is reconfiguring (profile change in progress); "
                            "try again in a few minutes"
                        ),
                    )
                    return False
                detail = (
                    f"No GPU capacity available for profile {gpu_profiles}: all "
                    f"matching GPU cards are in use, or no GPU hypervisor is online "
                    f"in pool {pool_id}. Free a GPU desktop or add capacity, then retry."
                )
            else:
                detail = f"desktop not started: no hypervisors online in pool {pool_id}"
            update_domain_status(
                status="Failed", id_domain=id_domain, hyp_id=next_hyp, detail=detail
            )
            return False
        else:
            return next_hyp

    def destroy_domain_from_id(self, id):
        pass

    def stop_domain_from_id(self, id):
        # INFO TO DEVELOPER. puede pasar que alguna actualización en algún otro hilo del status haga que
        # durante un corto período de tiempo devuelva None,para evitarlo durante un segundo vamos a ir pidiendo cada
        # 100 ms que nos de el hypervisor
        time_wait = 0.0
        while time_wait <= 20.0:
            hyp_id = get_domain_hyp_started(id)
            if hyp_id != None:
                if len(hyp_id) > 0:
                    break
            else:
                time_wait = time_wait + 0.1
                sleep(0.1)
                log.debug(
                    "waiting {} seconds to find hypervisor started for domain {}".format(
                        time_wait, id
                    )
                )
        log.debug("stop domain id {} in {}".format(id, hyp_id))
        # hyp_id = get_domain_hyp_started(id)
        # log.debug('stop domain id {} in {}'.format(id,hyp_id))
        if hyp_id is None:
            hyp_id = ""
        if len(hyp_id) <= 0:
            log.debug("hypervisor where domain {} is started not found".format(id))
            update_domain_status(
                status="Unknown",
                id_domain=id,
                hyp_id=None,
                detail="hypervisor where domain {} is started not found".format(id),
            )
        else:
            self.stop_domain(id, hyp_id)

    def shutdown_domain(self, id_domain, hyp_id):
        action = {
            "type": "shutdown_domain",
            "id_domain": id_domain,
        }

        self.manager.q.workers[hyp_id].put(action, Q_PRIORITY_SHUTDOWN)
        logs.main.debug(
            f"desktop {id_domain} in queue to soft off with shutdown ACPI action in hyp {hyp_id}"
        )

        return True

    def stop_domain(self, id_domain, hyp_id, not_change_status=False):
        action = {
            "type": "stop_domain",
            "id_domain": id_domain,
            "not_change_status": not_change_status,
        }
        self.manager.q.workers[hyp_id].put(action, Q_PRIORITY_STOP)
        logs.main.debug(
            f"desktop {id_domain} in queue to destroy action in hyp {hyp_id}"
        )
        return True

    def reset_domain(self, id_domain, hyp_id):
        action = {
            "type": "reset_domain",
            "id_domain": id_domain,
        }
        self.manager.q.workers[hyp_id].put(action, Q_PRIORITY_STOP)
        logs.main.debug(f"desktop {id_domain} added to queue to be reset in {hyp_id}")
        return True

    def updating_from_create_dict(self, id_domain, ssl=True):
        """Transition a desktop from Updating back to Stopped after an edit.

        Ported from apiv4-and-websockets (engine/controllers/ui_actions.py
        ``updating_from_create_dict``). When a user edits a desktop from
        the old frontend / webapp, apiv4 writes the new
        create_dict/hardware and flips status to ``Updating``. The engine
        must observe the transition, validate that the new create_dict
        produces a valid XML via ``recreate_xml_to_start``, and flip the
        status back to ``Stopped`` (or ``Failed`` if validation errors).

        Without this, the desktop is stuck in ``Updating`` forever.
        """
        try:
            updating_thread_pool.submit(
                self.updating_from_create_dict_th, id_domain, ssl
            )
        except Exception as e:
            logs.exception_id.debug("0018")
            log.error("Updating domain {} failed. Exception: {}".format(id_domain, e))

    def updating_from_create_dict_th(self, id_domain, ssl=True):
        """Worker body for ``updating_from_create_dict``.

        Adapted from apiv4-and-websockets. This branch's
        ``recreate_xml_to_start`` already rolls the old two-step flow
        (populate_dict_hardware_from_create_dict +
        update_xml_from_dict_domain) into a single call, so we just
        validate here and move to Stopped — next ``start_domain_from_id``
        will regenerate the XML from create_dict on demand.
        """
        sleep(0.1)
        domain = get_table_fields(
            "domains",
            id_domain,
            [
                "kind",
                "name",
                {"create_dict": {"hardware": "memory", "reservables": True}},
                "forced_hyp",
                "favourite_hyp",
                "hypervisors_pools",
            ],
        )
        if not domain:
            log.error(f"Domain {id_domain} not found; cannot transition Updating.")
            return False

        if domain.get("kind") != "desktop":
            # Templates don't go through the XML-validation path; just
            # flip the status back to Stopped.
            update_domain_status(
                "Stopped",
                id_domain,
                detail="Updated hardware",
            )
            return True

        pool_id_var = domain.get("hypervisors_pools")
        if not pool_id_var:
            update_domain_status(
                "Failed",
                id_domain,
                detail="Updating aborted, domain missing hypervisors pool",
            )
            return False
        pool_id = pool_id_var[0] if isinstance(pool_id_var, list) else pool_id_var

        cpu_host_model = self.manager.pools[pool_id].conf.get(
            "cpu_host_model", DEFAULT_HOST_MODE
        )
        try:
            xml, _viewer_passwd = recreate_xml_to_start(id_domain, ssl, cpu_host_model)
        except Exception as e:
            logs.exception_id.debug("0018")
            log.error("recreate_xml_to_start in domain {}".format(id_domain))
            log.error("Traceback: \n .{}".format(traceback.format_exc()))
            log.error("Exception message: {}".format(e))
            xml = False

        if xml is False:
            update_domain_status(
                "Failed",
                id_domain,
                detail="DomainXML can not parse and modify xml to start",
            )
            return False

        update_domain_status(
            "Stopped",
            id_domain,
            detail="Updated hardware",
        )
        return True

    # en principio crea todo lo que se necesita en la base de datos
    # esta función sólo ha de crear el disco derivado donde le diga el campo de la base de datos
    # recrear el xml y verificar que se define o arranca ok
    # yo crearía el disco con una ruta relativa respecto a una variable de configuración
    # y el path que se guarda en el disco podría ser relativo, aunque igual no vale la pena...

    def deleting_disks_from_domain(self, id_domain):
        """Enqueue storage delete-task chains for every disk of ``id_domain``.

        Invoked only by ``force_deleting`` on the apiv4-driven
        ``ForceDeleting`` flow; domain-row removal is handled by the
        caller after this returns. Each per-storage chain runs in
        ``isard-storage`` (``task="delete"`` → ``core:update_status`` →
        ``core:storage_delete``) and removes both the qcow2 file and
        the ``storages`` row independently of the desktop row.
        """
        try:
            dict_domain = get_domain(id_domain)
            if dict_domain is None:
                log.error(
                    "DELETE_DOMAIN_DISKS: Domain {} not found in database. Not removing any disk.".format(
                        id_domain
                    )
                )
                return False

            if dict_domain["kind"] != "desktop":
                log.warning(
                    "DELETE_DOMAIN_DISKS: Domain {} is a template. Its disks will be deleted; derivatives will become unusable.".format(
                        id_domain
                    )
                )

            disks = dict_domain["create_dict"]["hardware"].get("disks", [])
            if not disks:
                log.debug(
                    "DELETE_DOMAIN_DISKS: No disks to delete in domain {}".format(
                        id_domain
                    )
                )
                return True

            user_id = dict_domain.get("user")
            for d in disks:
                storage_id = d.get("storage_id")
                if not storage_id:
                    # Pre-storages-table format with a bare ``file`` path.
                    # No storage row -> no maintenance lock, no task chain.
                    # apiv4-integration should not be producing these; if
                    # one slips through, leave the file behind and surface
                    # a warning rather than reintroducing ssh.
                    log.warning(
                        "DELETE_DOMAIN_DISKS: Domain {} has an old-format disk (no storage_id); skipping deletion. Entry: {}".format(
                            id_domain, d
                        )
                    )
                    continue
                if len(domains_with_attached_storage_id(storage_id)) > 1:
                    log.debug(
                        "DELETE_DOMAIN_DISKS: Storage {} is shared with other domains; skipping deletion for domain {}.".format(
                            storage_id, id_domain
                        )
                    )
                    continue
                if not Storage.exists(storage_id):
                    log.warning(
                        "DELETE_DOMAIN_DISKS: Storage {} not in storages table for domain {}; skipping.".format(
                            storage_id, id_domain
                        )
                    )
                    continue
                try:
                    Storage(storage_id).task_delete(user_id=user_id)
                    log.info(
                        "DELETE_DOMAIN_DISKS: Domain {} storage {} enqueued for deletion via task chain".format(
                            id_domain, storage_id
                        )
                    )
                except Exception as e:
                    logs.exception_id.debug("0011")
                    log.error(
                        "DELETE_DOMAIN_DISKS: Unable to enqueue delete-storage task for storage {} (domain {}): {}".format(
                            storage_id, id_domain, e
                        )
                    )
            return True
        except Exception as e:
            logs.exception_id.debug("0071")
            log.error(
                "DELETE_DOMAIN_DISKS: Internal error when deleting disks for domain {}: {}".format(
                    id_domain, e
                )
            )
            log.error("Traceback: \n .{}".format(traceback.format_exc()))
            return False

    def force_deleting(self, domain_id, old_status):
        if old_status in ["Started", "Shutting-down", "Stopping", "Paused"]:
            hyp_id = get_domain_hyp_started(domain_id)

            if hyp_id is not None and hyp_id is not False:
                self.stop_domain(domain_id, hyp_id, not_change_status=True)

        self.deleting_disks_from_domain(domain_id)

        result = delete_domain(domain_id)
        log.info(
            f"domain {domain_id} force deleting, launched force destroy domain if started and delete disks in threads."
        )
        if result["deleted"] == 1:
            log.info(f"domain {domain_id} deleted from table domain")
        else:
            log.error(f"domain {domain_id} does not exist in table domain")
        return result

    def creating_and_test_xml_start(
        self,
        id_domain,
        creating_from_create_dict=False,
        xml_from_virt_install=False,
        xml_string=None,
        ssl=True,
        start_paused=True,
    ):
        domain = get_domain(id_domain)
        if domain is None:
            log.error(
                "CREATING_AND_TEST_XML_START_DOMAIN: Domain {} not found in database. Not creating any xml.".format(
                    id_domain
                )
            )
            return False
        # create_dict_hw = domain['create_dict']['hardware']
        # for media in ['isos','floppies']
        #     if 'isos' in create_dict_hw.keys():
        #         for index_disk in range(len(create_dict_hw['isos'])):
        #             update_hw['hardware']['isos'][index_disk]['file'] = new_file

        if type(xml_string) is str:
            xml_from = xml_string

        elif "create_from_virt_install_xml" in domain["create_dict"]:
            xml_from = get_dict_from_item_in_table(
                "virt_install", domain["create_dict"]["create_from_virt_install_xml"]
            )["xml"]

        elif xml_from_virt_install is False:
            id_template = domain["create_dict"]["origin"]
            template = get_template_cached(id_template)
            if template is None:
                logs.main.error(
                    "##### Traceback: creating_and_test_xml_start, xml_from...\n{}\n ...template {} not found when creating domain...\n {}\n...\n{}\n...".format(
                        xml_from, id_template, domain, traceback.format_exc()
                    )
                )
                update_domain_status(
                    "Failed",
                    id_domain,
                    detail=f"Can't create domain from template {id_template}, template not found. Was deleted during domain creation?",
                )
                return False
            xml_from = decompress_xml(template.get("xml"))
            # Ancestor chain: template's chain plus the template itself
            # as the immediate parent. apiv4 already writes this at insert
            # time, so the ``update_table_field`` below is idempotent —
            # but we keep it for compatibility with other writers (apiv3,
            # downloads, upgrade migrations) that may leave the field
            # empty or stale.
            parents_chain = (template.get("parents") or []) + [id_template]
            # Self-reference safety: a domain must never list itself as
            # an ancestor (can happen during template-from-domain if the
            # two rows briefly share an id).
            parents_chain = [p for p in parents_chain if p != id_domain]

            update_table_field("domains", id_domain, "parents", parents_chain)

        elif xml_from_virt_install is True:
            xml_from = domain["xml_virt_install"]

        else:
            return False

        # Direct write so we keep ``compress_xml`` at the call site —
        # ``update_table_field`` is a generic helper used for many
        # other fields and must remain compression-agnostic.
        with rethink_conn() as _conn:
            r.table("domains").get(id_domain).update(
                {"xml": compress_xml(xml_from)}
            ).run(_conn)

        update_domain_status(
            "CreatingDomain",
            id_domain,
            detail="xml and hardware dict updated, waiting to test if domain start paused in hypervisor",
        )
        try:
            pool_id = domain.get("hypervisors_pools", ["default"])[0]
        except:
            pool_id = "default"
            log.error(
                f"Domain {id_domain} has no hypervisors_pools. Using default pool."
            )

        if "start_after_created" in domain.keys():
            if domain["start_after_created"] is True:
                update_domain_status(
                    "StartingDomainDisposable",
                    id_domain,
                    detail="xml and hardware dict updated, starting domain disposable",
                )

                # update_domain_status('Starting', id_domain,
                #                      detail='xml and hardware dict updated, starting domain disposable')

                self.start_domain_from_id(id_domain)

        else:
            # change viewer password, remove selinux options and recreate network interfaces
            try:
                cpu_host_model = self.manager.pools[pool_id].conf.get(
                    "cpu_host_model", DEFAULT_HOST_MODE
                )
                xml = recreate_xml_to_start(id_domain, ssl, cpu_host_model)
            except Exception as e:
                logs.exception_id.debug("0021")
                log.error("recreate_xml_to_start in domain {}".format(id_domain))
                log.error("Traceback: \n .{}".format(traceback.format_exc()))
                log.error("Exception message: {}".format(e))
                xml = False

            if xml is False:
                update_domain_status(
                    "Failed",
                    id_domain,
                    detail="DomainXML can't parse and modify xml to start",
                )
            else:
                # If comes from creating disk do not start paused
                if start_paused is True:
                    self.start_paused_domain_from_xml(
                        xml=xml,
                        id_domain=id_domain,
                        pool_id=pool_id,
                        forced_hyp=domain.get("forced_hyp"),
                        favourite_hyp=domain.get("favourite_hyp"),
                        reservables=domain.get("create_dict", {}).get(
                            "reservables", {}
                        ),
                    )
                else:
                    update_domain_status(
                        "Stopped",
                        id_domain,
                        detail="Template creation completed, ready to derive desktops",
                    )
