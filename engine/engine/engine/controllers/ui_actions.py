# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from time import sleep

from cachetools import TTLCache, cached
from engine.models.domain_xml import (
    BUS_TYPES,
    add_memory_backing,
    recreate_xml_if_gpu,
    recreate_xml_if_start_paused,
    recreate_xml_to_start,
)
from engine.services.db import (
    create_disk_template_created_list_in_domain,
    delete_domain,
    domains_with_attached_disk,
    domains_with_attached_storage_id,
    get_dict_from_item_in_table,
    get_domain,
    get_domain_forced_hyp,
    get_domain_hyp_started,
    get_hypers_in_pool,
    get_table_field,
    get_table_fields,
    insert_domain,
    remove_dict_new_template_from_domain,
    remove_disk_template_created_list_in_domain,
    update_domain_status,
    update_origin_and_parents_to_new_template,
    update_table_field,
    update_vgpu_info_if_stopped,
    update_vgpu_uuid_domain_action,
)
from engine.services.db.storage_pool import get_category_storage_pool_id
from engine.services.lib.qcow import (
    create_cmds_delete_disk,
    get_host_disk_operations_from_path,
    get_path_to_disk,
)
from engine.services.lib.storage import (
    create_storage,
    get_storage_id_filename,
    update_storage_deleted_domain,
)
from engine.services.log import *
from isardvdi_common.models.domain import Domain

DEFAULT_HOST_MODE = "host-passthrough"

# normal priority in PriorityQueueIsard is 100
# lower number => more priority
Q_PRIORITY_START = 50
Q_PRIORITY_STARTPAUSED = 60
Q_PRIORITY_DELETE = 150
Q_PRIORITY_STOP = 40  # Destroy
Q_PRIORITY_SHUTDOWN = 80  # Soft Shut-Down
Q_PRIORITY_PERSONAL_UNIT = 130  # Mount personal unit inside a desktop

Q_LONGOPERATIONS_PRIORITY_CREATE_TEMPLATE_DISK = 50
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
                {"create_dict": {"hardware": "memory", "reservables": True}},
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

        try:
            xml, viewer_passwd = recreate_xml_to_start(id_domain, ssl, cpu_host_model)
        except Exception as e:
            logs.exception_id.debug("0010")
            log.error("recreate_xml_to_start in domain {}".format(id_domain))
            log.error("Traceback: \n .{}".format(traceback.format_exc()))
            log.error("Exception message: {}".format(e))
            xml = False
            viewer_passwd = ""

        if xml is False:
            update_domain_status(
                "Failed",
                id_domain,
                detail="DomainXML can not parse and modify xml to start",
            )
            return False
        else:
            domain_memory_kb = (
                domain.get("create_dict", {}).get("hardware", {}).get("memory", 1048576)
            )
            domain_memory_gb = domain_memory_kb / 1048576
            # Clean up any stale vGPU reservation before starting
            update_vgpu_info_if_stopped(id_domain)
            if starting_paused is True:
                hyp = self.start_paused_domain_from_xml(
                    xml,
                    id_domain,
                    pool_id=pool_id,
                    forced_hyp=domain.get("forced_hyp"),
                    favourite_hyp=domain.get("favourite_hyp"),
                    force_gpus=domain.get("force_gpus"),
                    reservables=domain.get("create_dict", {}).get("reservables", {}),
                    storage_pool_id=domain_storage_pool_id,
                    domain_memory_gb=domain_memory_gb,
                    viewer_passwd=viewer_passwd,
                )
            else:
                hyp = self.start_domain_from_xml(
                    xml,
                    id_domain,
                    pool_id=pool_id,
                    forced_hyp=domain.get("forced_hyp"),
                    favourite_hyp=domain.get("favourite_hyp"),
                    force_gpus=domain.get("force_gpus"),
                    reservables=domain.get("create_dict", {}).get("reservables", {}),
                    storage_pool_id=domain_storage_pool_id,
                    domain_memory_gb=domain_memory_gb,
                    viewer_passwd=viewer_passwd,
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
    ):
        failed = False
        if pool_id in self.manager.pools.keys():
            # Loop selection+reservation so we can retry on a lost CAS when two
            # starters race for the same mdev UUID. Non-GPU paths exit after the
            # first iteration.
            next_hyp = False
            extra_info = {}
            is_gpu = False
            max_attempts = 5
            for attempt in range(max_attempts):
                next_hyp, extra_info = self.manager.pools[
                    pool_id
                ].balancer.get_next_hypervisor(
                    forced_hyp=forced_hyp,
                    favourite_hyp=favourite_hyp,
                    reservables=reservables,
                    force_gpus=force_gpus,
                    storage_pool_id=storage_pool_id,
                    domain_memory_gb=domain_memory_gb,
                )
                if next_hyp is False:
                    break
                if action == "start_paused_domain":
                    extra_info = {}
                is_gpu = extra_info.get("nvidia", False) is True
                if not is_gpu:
                    break
                reserved_ok = update_vgpu_uuid_domain_action(
                    extra_info["gpu_id"],
                    extra_info["uid"],
                    "domain_reserved",
                    domain_id=id_domain,
                    profile=extra_info["profile"],
                )
                if reserved_ok:
                    xml = recreate_xml_if_gpu(
                        xml,
                        extra_info["uid"],
                        pci_bus_id=extra_info.get("pci_bus_id"),
                        is_passthrough=(extra_info.get("profile") == "passthrough"),
                    )
                    if extra_info.get("profile") == "passthrough":
                        xml = add_qemu_pcie_reserve(xml)
                    break
                log.warning(
                    f"{id_domain}: vgpu reservation lost CAS on uuid "
                    f"{extra_info.get('uid')} (attempt {attempt + 1}/{max_attempts}); "
                    f"re-selecting"
                )
            else:
                update_domain_status(
                    "Failed",
                    id_domain,
                    detail="Could not reserve a free vGPU mdev after retries (concurrent starters)",
                )
                return False
            if next_hyp is not False:
                # Flag the slow-VFIO path so the worker can extend its
                # libvirt createXML timeout for this action (see
                # LIBVIRT_CREATEXML_TIMEOUT_GPU_SLOW). A GPU domain forced
                # onto 4K-page RAM routinely exceeds the 30s default.
                # Declared before the try block below so it stays visible
                # even if the optimization block bails out.
                expects_slow_createxml = False

                # --- NUMA / hugepages optimizations (best-effort) ---
                # A failure anywhere in this block (bad topology data,
                # unexpected XML shape, missing fields) must never stop the
                # domain from starting — we fall back to the pre-optimization
                # XML and log a warning.
                _xml_before_opts = xml
                try:
                    # --- NUMA node selection ---
                    # Only trust numa_topology when the hypervisor confirmed
                    # libvirt sees the same cells as sysfs. When that check
                    # failed (or the flag is missing on older images) we skip
                    # pinning — libvirt would otherwise reject <numatune>
                    # with "NUMA node X is unavailable".
                    numa_topo = extra_info.get("numa_topology", {}) or {}
                    libvirt_numa_ok = bool(numa_topo.get("libvirt_numa_ok"))
                    numa_nodes = numa_topo.get("nodes", {}) if libvirt_numa_ok else {}
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
                        else:
                            # Pick NUMA node with most free hugepages, or hash-distribute
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
                                if hugepages.get("1G", {}).get("total", 0) > 0:
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
                                if hp_free_kb >= domain_memory_kb:
                                    if hugepages.get("1G", {}).get("total", 0) > 0:
                                        xml = add_memory_backing(xml, "1", "G")
                                    elif hugepages.get("2M", {}).get("total", 0) > 0:
                                        xml = add_memory_backing(xml, "2", "M")

                    # --- NUMA CPU pinning + IO thread pinning ---
                    if target_node is not None and target_node in numa_nodes:
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
                            )
                            xml = add_iothread_pinning(xml, cpulist)
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
                detail = f"desktop not started: no hypervisors online with GPU model available and profile"
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
        """Enqueue delete_disk SSH actions for every disk of ``id_domain``.

        Invoked only by ``force_deleting`` on the apiv4-driven
        ``ForceDeleting`` flow; domain-row removal is handled by the
        caller after the dispatch. The old Deleting / DeletingDomainDisk /
        DiskDeleted status-driven path is gone (apiv4 never writes those
        statuses to desktop rows).
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
                    "DELETE_DOMAIN_DISKS: Domain {} is a template!. It's disks will be deleted. Disks who depends on this one will be unusabe and should be deleted.".format(
                        id_domain
                    )
                )

            wait_for_disks_to_be_deleted = False
            disks = dict_domain["create_dict"]["hardware"].get("disks", [])

            if len(disks) > 0:
                index_disk = 0

                for d in disks:
                    storage_id = d.get("storage_id")
                    if not storage_id:
                        # Old disks in domain
                        disk_path = d.get("file")
                        if not disk_path:
                            log.error(
                                "DELETE_DOMAIN_DISKS: Domain {} disk in old format and not found the file key in db entry. Unable to delete disk entry: \n {}".format(
                                    id_domain, d
                                )
                            )
                            index_disk += 1
                            continue
                        # Check for duplicates
                        if len(domains_with_attached_disk(disk_path)) > 1:
                            log.debug(
                                "DELETE_DOMAIN_DISKS: Others than this domain {} have this old format disk {} attached. Skipping deleting disk.".format(
                                    id_domain, disk_path
                                )
                            )
                            index_disk += 1
                            continue
                    else:
                        # New disks in storage
                        disk_path = get_storage_id_filename(storage_id)
                        if not disk_path:
                            log.error(
                                "DELETE_DOMAIN_DISKS: Domain {} storage_id {} missing disk path or not in storage table. This should not happen.".format(
                                    id_domain, storage_id
                                )
                            )
                            index_disk += 1
                            continue
                        # Check for duplicates
                        if len(domains_with_attached_storage_id(d["storage_id"])) > 1:
                            log.debug(
                                "DELETE_DOMAIN_DISKS: Others than this domain {} have this storage_id {} attached. Skipping deleting disk.".format(
                                    id_domain, storage_id
                                )
                            )
                            index_disk += 1
                            continue

                    pool_id = dict_domain["hypervisors_pools"][0]
                    if pool_id not in self.manager.pools.keys():
                        log.error(
                            "DELETE_DOMAIN_DISKS: Hypervisor pool {} not available in manager. Unable to delete domain {} disk {} in pool.".format(
                                pool_id, id_domain, disk_path
                            )
                        )
                        return False

                    # Which hypervisors are online in this pool?
                    (
                        hyps_to_start,
                        hyps_only_forced,
                        hyps_all,
                    ) = get_hypers_in_pool(pool_id, only_online=True)
                    if not len(hyps_all):
                        log.error(
                            "DELETE_DOMAIN_DISKS: No hypervisors online in pool {} to delete disk {}".format(
                                pool_id, disk_path
                            )
                        )
                        return False

                    # Choose a hypervisor to delete the disk
                    forced_hyp, favourite_hyp = get_domain_forced_hyp(id_domain)
                    if forced_hyp in hyps_all:
                        next_hyp = forced_hyp
                    elif favourite_hyp in hyps_all:
                        next_hyp = favourite_hyp
                    else:
                        next_hyp = hyps_all[0]

                    if type(next_hyp) is tuple:
                        h = next_hyp[0]
                        next_hyp = h
                    log.debug(
                        "DELETE_DOMAIN_DISKS: Preparing disk {} to be enqueued in hypervisor {}...".format(
                            disk_path, next_hyp
                        )
                    )
                    mv_to_extension_deleted = self.manager.pools[pool_id].conf.get(
                        "mv_to_extension_deleted", False
                    )
                    cmds = create_cmds_delete_disk(
                        disk_path, mv_to_extension_deleted=mv_to_extension_deleted
                    )

                    action = {
                        "id_domain": id_domain,
                        "type": "delete_disk",
                        "disk_path": disk_path,
                        "domain": id_domain,
                        "ssh_commands": cmds,
                        "index_disk": index_disk,
                        "storage_id": (
                            dict(
                                enumerate(
                                    dict_domain.get("create_dict", {})
                                    .get("hardware", {})
                                    .get("disks", [])
                                )
                            )
                            .get(index_disk, {})
                            .get("storage_id")
                        ),
                    }

                    try:
                        update_storage_deleted_domain(action["storage_id"], dict_domain)
                        log.info(
                            "DELETE_DOMAIN_DISKS: Domain {} disk {} queued in hypervisor {} to be deleted".format(
                                id_domain, disk_path, next_hyp
                            )
                        )
                        self.manager.q.workers[next_hyp].put(action, Q_PRIORITY_DELETE)
                        wait_for_disks_to_be_deleted = True
                    except Exception as e:
                        logs.exception_id.debug("0011")
                        log.error(
                            "DELETE_DOMAIN_DISKS: Unable to enqueue disk {} to be deleted in hypervisor {}. Exception: {}".format(
                                disk_path, next_hyp, e
                            )
                        )
                        return False
                    index_disk += 1
                else:
                    log.debug(
                        "DELETE_DOMAIN_DISKS: No disks to delete in domain {}".format(
                            id_domain
                        )
                    )
            else:
                log.error(
                    "DELETE_DOMAIN_DISKS: No hardware dict in domain to delete {}. This should not happen".format(
                        id_domain
                    )
                )
            if not wait_for_disks_to_be_deleted:
                delete_domain(id_domain)
            return True
        except Exception as e:
            logs.exception_id.debug("0071")
            log.error(
                "DELETE_DOMAIN_DISKS: Internal error when deleting disks for domain {}".format(
                    id_domain
                )
            )
            log.error("Traceback: \n .{}".format(traceback.format_exc()))
            log.error("Exception message: {}".format(e))
            return False

    def create_template_disks_from_domain(self, id_domain):
        dict_domain = get_domain(id_domain)
        if dict_domain is None:
            log.error(
                "CREATE_TEMPLATE_DISKS_FROM_DOMAIN: Domain {} not found in database. Not creating any disk.".format(
                    id_domain
                )
            )
            return False
        create_dict = dict_domain["create_dict"]

        pool_id = get_category_storage_pool_id(dict_domain.get("category"))
        if pool_id is None:
            log.error(
                "CREATE_TEMPLATE_DISKS_FROM_DOMAIN: No storage pool available for domain {} in category {}. Not creating any disk.".format(
                    id_domain,
                    dict_domain.get("category"),
                )
            )
            return False
        try:
            dict_new_template = create_dict["template_dict"]
        except KeyError as e:
            update_domain_status(
                status="Stopped",
                id_domain=id_domain,
                hyp_id=False,
                detail="Action Creating Template from domain failed. No template_json in domain dictionary",
            )
            log.error(
                "No template_dict in keys of domain dictionary, when creating template form domain {}. Exception: {}".format(
                    id_domain, str(e)
                )
            )
            return False

        if not Domain(id_domain).storage_ready:
            update_domain_status(
                "Stopped",
                id_domain,
                detail="Desktop storages aren't ready",
            )
            return False

        disk_index_in_bus = 0
        create_hw = dict_domain.get("create_dict", {}).get("hardware", {})
        if "disks" in create_hw and len(create_hw["disks"]):
            create_disk_template_created_list_in_domain(id_domain)
            for i in range(1):
                path_domain_disk = get_storage_id_filename(
                    dict_domain["create_dict"]["hardware"]["disks"][i]["storage_id"]
                )

                type_path_selected = "template"

                new_file, path_selected = get_path_to_disk(
                    category_id=dict_domain.get("category"),
                    type_path=type_path_selected,
                    extension=dict_new_template["create_dict"]["hardware"]["disks"][i][
                        "extension"
                    ],
                )
                path_absolute_template_disk = new_file = new_file.replace("//", "/")
                dict_new_template["create_dict"]["hardware"]["disks"][i][
                    "file"
                ] = new_file
                dict_new_template["create_dict"]["hardware"]["disks"][i][
                    "path_selected"
                ] = path_selected

                disk = dict_new_template["create_dict"]["hardware"]["disks"][i]
                create_storage(
                    disk,
                    dict_new_template.get("user"),
                    force_parent=None,
                    perms=["r"],
                )
                update_table_field("domains", id_domain, "create_dict", create_dict)

                action = {}
                action["id_domain"] = id_domain
                action["type"] = "create_template_disk_from_domain"
                action["path_template_disk"] = path_absolute_template_disk
                action["path_domain_disk"] = path_domain_disk
                action["disk_index"] = disk_index_in_bus
                action["storage_id"] = disk.get("storage_id")
                action["domain_storage_id"] = dict_domain["create_dict"]["hardware"][
                    "disks"
                ][i]["storage_id"]

                hyp_to_disk_create = get_host_disk_operations_from_path(
                    self.manager,
                    pool=pool_id,
                    type_path=type_path_selected,
                )

                # INFO TO DEVELOPER: falta terminar de ver que hacemos con el pool para crear
                # discos, debería haber un disk operations por pool
                try:
                    update_domain_status(
                        status="CreatingTemplateDisk",
                        id_domain=id_domain,
                        hyp_id=False,
                        detail="Creating template disk operation is launched in hostname {} ({} operations in queue)".format(
                            hyp_to_disk_create,
                            self.manager.q_disk_operations[hyp_to_disk_create].qsize(),
                        ),
                    )
                    self.manager.q_disk_operations[hyp_to_disk_create].put(
                        action, Q_LONGOPERATIONS_PRIORITY_CREATE_TEMPLATE_DISK
                    )
                except Exception as e:
                    logs.exception_id.debug("0012")
                    update_domain_status(
                        status="Stopped",
                        id_domain=id_domain,
                        hyp_id=False,
                        detail="Creating template operation failed when insert action in queue for disk operations",
                    )
                    log.error(
                        "Creating disk operation failed when insert action in queue for disk operations in host {}. Exception: {}".format(
                            hyp_to_disk_create, e
                        )
                    )
                    return False

                    disk_index_in_bus = disk_index_in_bus + 1

            return True

            # first: move and rename disk to templates folder

    def create_template_in_db(self, id_domain):
        domain_dict = get_domain(id_domain)
        if domain_dict is None:
            log.error(
                "CREATE_TEMPLATE_IN_DB_FROM_DOMAIN: Domain {} not found in database. Not creating any disk.".format(
                    id_domain
                )
            )
            return False
        template_dict = domain_dict["create_dict"]["template_dict"]
        template_dict["status"] = "CreatingNewTemplateInDB"
        template_id = template_dict["id"]
        for d_disk in template_dict["create_dict"]["hardware"].get("disks", {}):
            if "storage_id" in d_disk.keys():
                for k in list(d_disk.keys()):
                    if k != "storage_id":
                        d_disk.pop(k)
        if insert_domain(template_dict)["inserted"] == 1:
            update_table_field("domains", template_id, "xml", domain_dict["xml"])
            remove_disk_template_created_list_in_domain(id_domain)
            remove_dict_new_template_from_domain(id_domain)
            if "parents" in domain_dict.keys():
                domain_parents_chain_update = domain_dict["parents"].copy()
            else:
                domain_parents_chain_update = []

            domain_parents_chain_update.append(template_id)
            update_table_field(
                "domains", id_domain, "parents", domain_parents_chain_update
            )
            update_origin_and_parents_to_new_template(id_domain, template_id)
            # update_table_field('domains', template_id, 'xml', xml_parsed, merge_dict=False)
            update_domain_status(
                status="Stopped",
                id_domain=template_id,
                hyp_id=False,
                detail="Template created, ready to create domains from this template",
            )
            update_domain_status(
                status="Stopped",
                id_domain=id_domain,
                hyp_id=False,
                detail="Template created from this domain, now domain is ready to start again",
            )

        else:
            log.error(
                "template {} can not be inserted in rethink, domain_id duplicated??".format(
                    template_id
                )
            )
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
            xml_from = template["xml"]
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

        update_table_field("domains", id_domain, "xml", xml_from)

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
