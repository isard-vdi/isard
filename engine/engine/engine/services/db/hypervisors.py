import time
from datetime import datetime

import pytz
from engine.services.db import (
    MAX_LEN_PREV_STATUS_HYP,
    cleanup_hypervisor_gpus,
    close_rethink_connection,
    new_rethink_connection,
    rethink_conn,
)
from engine.services.db.domains import get_vgpus_mdevs
from engine.services.log import log, logs
from rethinkdb import r
from rethinkdb.errors import ReqlNonExistenceError


def get_hypervisor(hyp_id):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")
    try:
        out = rtable.get(hyp_id).run(r_conn)
    except:
        close_rethink_connection(r_conn)
        return None

    close_rethink_connection(r_conn)
    return out


def get_cluster_guest_mtu():
    """Tenant-overlay guest MTU ceiling published by the API per hypervisor.

    The cluster is homogeneous (same INFRASTRUCTURE_MTU / GENEVE_ONLY_INFRA
    across nodes), so any Online hypervisor's ``vpn.guest_mtu`` is the
    cluster value. Returns the int ceiling, or ``None`` when no Online
    hypervisor publishes it (older/mixed-version cluster, fresh install,
    or DB error) — callers must then emit unchanged XML (no regression).
    """
    r_conn = new_rethink_connection()
    try:
        out = list(
            r.table("hypervisors")
            .filter({"status": "Online"})
            .filter(lambda h: h["vpn"]["guest_mtu"].default(False).ne(False))
            .pluck({"vpn": "guest_mtu"})
            .limit(1)
            .run(r_conn)
        )
    except Exception:
        close_rethink_connection(r_conn)
        return None
    close_rethink_connection(r_conn)
    try:
        return int(out[0]["vpn"]["guest_mtu"])
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def update_hyp_thread_status(thread_type, hyp_id, status):
    if thread_type in ["worker", "disk_operations"] and status in [
        "Started",
        "Stopped",
        "Starting",
        "Stopping",
        "Deleting",
    ]:
        with rethink_conn() as conn:
            result = (
                r.table("hypervisors")
                .get(hyp_id)
                .update({"thread_status": {thread_type: status}})
                .run(conn)
            )

        if status != "Started":
            try:
                with rethink_conn() as conn:
                    d = (
                        r.table("hypervisors")
                        .get(hyp_id)
                        .pluck("thread_status", "status", "capabilities")
                        .run(conn)
                    )
            except:
                # hypervisor not found. It is weird that it happens.
                return False
            status_hyp = d["status"]
            if status_hyp == "Online":
                update_hyp_status(
                    hyp_id,
                    "Offline",
                    f"thread {thread_type} is not Started. Status of thread: {status}",
                )
            elif status_hyp == "Deleting":
                ko_disk_operations = False
                if d["capabilities"].get("disk_operations", False) is True:
                    if d["thread_status"].get("disk_operations", "") == "Stopped":
                        ko_disk_operations = True
                elif d["capabilities"].get("disk_operations", True) is False:
                    ko_disk_operations = True

                ko_worker = False
                if d["capabilities"].get("hypervisor", False) is True:
                    if d["thread_status"].get("worker", "") == "Stopped":
                        ko_worker = True
                elif d["capabilities"].get("hypervisor", True) is False:
                    ko_worker = True

                if ko_worker is True and ko_disk_operations is True:
                    cleanup_hypervisor_gpus(hyp_id)
                    with rethink_conn() as conn:
                        return r.table("hypervisors").get(hyp_id).delete().run(conn)

        elif status == "Started":
            with rethink_conn() as conn:
                d = (
                    r.table("hypervisors")
                    .get(hyp_id)
                    .pluck("thread_status", "status", "capabilities")
                    .run(conn)
                )

            ok_disk_operations = False
            if d["capabilities"].get("disk_operations", False) is True:
                if d["thread_status"].get("disk_operations", "") == "Started":
                    ok_disk_operations = True
            elif d["capabilities"].get("disk_operations", True) is False:
                ok_disk_operations = True

            ok_worker = False
            if d["capabilities"].get("hypervisor", False) is True:
                if d["thread_status"].get("worker", "") == "Started":
                    ok_worker = True
            elif d["capabilities"].get("hypervisor", True) is False:
                ok_worker = True

            if ok_worker is True and ok_disk_operations is True:
                logs.workers.info(
                    f"All threads for hyp are started in hypervisor: {hyp_id}"
                )
        return result
    else:
        return False


def update_hyp_status(id, status, detail="", uri=""):
    # INFO TO DEVELOPER: TODO debería pillar el estado anterior del hypervisor y ponerlo en un campo,
    # o mejor aún, guardar un histórico con los tiempos de cambios en un diccionario que
    # en python puede ser internamente una cola de X elementos (número de elementos de configuración)
    # como una especie de log de cuando cambio de estado

    # INFO TO DEVELOPER: pasarlo a una función en functions
    defined_status = [
        "Offline",
        #'TryConnection',
        #'ReadyToStart',
        #'StartingThreads',
        "Error",
        "Deleting",
        "Online",
    ]
    #'Blocked',
    #'DestroyingDomains',
    #'StoppingThreads']
    if status == "Error":
        pass
    if status in defined_status:
        if len(uri) > 0:
            dict_update = {"status": status, "uri": uri}
        else:
            dict_update = {"status": status}
        with rethink_conn() as conn:
            d = (
                r.table("hypervisors")
                .get(id)
                .pluck("status", "status_time", "prev_status", "detail", "capabilities")
                .run(conn)
            )

        if status == "Online":
            dict_update["cap_status"] = {
                "hypervisor": d.get("capabilities", {}).get("hypervisor", False),
                "disk_operations": d.get("capabilities", {}).get(
                    "disk_operations", False
                ),
            }
        else:
            dict_update["cap_status"] = {
                "hypervisor": False,
                "disk_operations": False,
            }
        if "status" in d.keys():
            if "prev_status" not in d.keys():
                dict_update["prev_status"] = []

            else:
                if type(d["prev_status"]) is list:
                    dict_update["prev_status"] = d["prev_status"]
                else:
                    dict_update["prev_status"] = []

            d_old_status = {}
            d_old_status["status"] = d["status"]
            if "detail" in d.keys():
                d_old_status["detail"] = d["detail"]
            else:
                d_old_status["detail"] = ""
            if "status_time" in d.keys():
                d_old_status["status_time"] = d["status_time"]

            dict_update["prev_status"].insert(0, d_old_status)
            dict_update["prev_status"] = dict_update["prev_status"][
                :MAX_LEN_PREV_STATUS_HYP
            ]

        now = int(time.time())
        dict_update["status_time"] = now

        # if len(detail) == 0:
        #     rtable.filter({'id':id}).\
        #           update(dict_update).\
        #           run(r_conn)
        #     # rtable.filter({'id':id}).\
        #     #       replace(r.row.without('detail')).\
        #     #       run(r_conn)
        #     close_rethink_connection(r_conn)
        #
        # else:
        dict_update["detail"] = str(detail)
        with rethink_conn() as conn:
            r.table("hypervisors").get(id).update(dict_update).run(conn)

    else:
        log.error("hypervisor status {} is not defined".format(status))
        return False


def update_hyp_degraded_status(hyp_id, is_degraded, reason=None):
    """Update hypervisor degraded state.

    When degraded:
        - Set cap_status = {hypervisor: False, disk_operations: False}
        - Keep status = "Online" (still connected, just slow)
        - Set degraded = {is_degraded: True, reason: "...", since: timestamp}

    When recovered:
        - Restore cap_status from capabilities
        - Clear degraded field

    Args:
        hyp_id: Hypervisor ID
        is_degraded: True to mark as degraded, False to recover
        reason: Reason for degradation (e.g., "slow_response", "timeout")
    """
    with rethink_conn() as conn:
        if is_degraded:
            # Mark as degraded - exclude from balancer
            update_data = {
                "cap_status": {
                    "hypervisor": False,
                    "disk_operations": False,
                },
                "degraded": {
                    "is_degraded": True,
                    "reason": reason or "unknown",
                    "since": int(time.time()),
                },
            }
            logs.workers.warning(f"[{hyp_id}] Hypervisor marked as DEGRADED: {reason}")
        else:
            # Recover - restore cap_status from capabilities
            hyp = r.table("hypervisors").get(hyp_id).pluck("capabilities").run(conn)
            capabilities = hyp.get("capabilities", {})

            update_data = {
                "cap_status": {
                    "hypervisor": capabilities.get("hypervisor", False),
                    "disk_operations": capabilities.get("disk_operations", False),
                },
                "degraded": {
                    "is_degraded": False,
                    "reason": None,
                    "since": None,
                },
            }
            logs.workers.info(f"[{hyp_id}] Hypervisor recovered from degraded state")

        r.table("hypervisors").get(hyp_id).update(update_data).run(conn)


def get_degraded_hyp_ids():
    """Return the set of hypervisor IDs currently marked as degraded in DB."""
    with rethink_conn() as conn:
        return set(
            r.table("hypervisors")
            .filter({"degraded": {"is_degraded": True}})
            .get_field("id")
            .run(conn)
        )


def update_hyp_libvirt_warning(hyp_id, slow_count=None, avg_ms=None, clear=False):
    """Update hypervisor libvirt_warning field for webapp display.

    This shows the warning state (slow but still usable) in the webapp.

    Args:
        hyp_id: Hypervisor ID
        slow_count: Number of slow responses in detection window
        avg_ms: Average response time in milliseconds
        clear: If True, clear the warning field
    """
    with rethink_conn() as conn:
        if clear:
            update_data = {
                "libvirt_warning": None,
            }
        else:
            update_data = {
                "libvirt_warning": {
                    "slow_count": slow_count or 0,
                    "avg_ms": avg_ms or 0,
                    "last_slow": int(time.time()),
                },
            }
        r.table("hypervisors").get(hyp_id).update(update_data).run(conn)


def get_id_hyp_from_uri(uri):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")
    l = list(rtable.filter({"uri": uri}).pluck("id").run(r_conn))
    close_rethink_connection(r_conn)
    if len(l) > 0:
        return l[0]["id"]
    else:
        log.error(
            "function: {} uri {} not defined in hypervisors table".format(
                str(__name__), uri
            )
        )


def get_hyp_hostnames_online():
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")
    l = list(
        rtable.filter({"enabled": True, "status": "Online"})
        .pluck("id", "hostname")
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    log.debug(l)
    if len(l) > 0:
        hyps_hostnames = {d["id"]: d["hostname"] for d in l}

        return hyps_hostnames
    else:
        return dict()


def update_uri_hyp(hyp_id, uri):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")
    out = rtable.get(hyp_id).update({"uri": uri}).run(r_conn)
    close_rethink_connection(r_conn)
    return out


def get_hyp_info(hyp_id):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")
    try:
        out = rtable.get(hyp_id).pluck("info", "min_free_mem_gb").run(r_conn)
    except ReqlNonExistenceError:
        close_rethink_connection(r_conn)
        return False

    close_rethink_connection(r_conn)
    min_free_mem_gb = out.get("min_free_mem_gb", 0)
    if min_free_mem_gb is None or min_free_mem_gb is False:
        min_free_mem_gb = 0
    if "info" in out.keys():
        if type(out["info"]) is dict and len(out["info"]) > 0:
            out["info"]["min_free_mem_gb"] = min_free_mem_gb
            return out["info"]

    return out.get("info", False)


def get_hyp_status(hyp_id):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")
    try:
        out = rtable.get(hyp_id).pluck("status").run(r_conn)
    except ReqlNonExistenceError:
        close_rethink_connection(r_conn)
        return False

    close_rethink_connection(r_conn)
    return out["status"]


def get_hyp_system_info():
    r_conn = new_rethink_connection()
    try:
        hypers = list(
            r.table("hypervisors")
            .pluck(
                "id",
                "status",
                "capabilities",
                "only_forced",
                "stats",
                "min_free_mem_gb",
                "gpu_only",
            )
            .run(r_conn)
        )
    except:
        close_rethink_connection(r_conn)
        return []

    close_rethink_connection(r_conn)
    return hypers


def get_hyp_hostname_from_id(id):
    """Get hypervisor connection info by ID.

    Returns:
        Tuple of (hostname, port, user, nvidia_enabled, init_vgpu_profiles)
    """
    try:
        with rethink_conn() as conn:
            l = (
                r.table("hypervisors")
                .get(id)
                .pluck(
                    "hostname",
                    "port",
                    "user",
                    "nvidia_enabled",
                    "init_vgpu_profiles",
                )
                .run(conn)
            )
    except ReqlNonExistenceError:
        return False, False, False, False, False
    if len(l) > 0:
        if l.__contains__("user") and l.__contains__("port"):
            return (
                l["hostname"],
                l["port"],
                l["user"],
                l.get("nvidia_enabled", False),
                l.get("init_vgpu_profiles", False),
            )

        else:
            log.error(
                "hypervisor {} does not contain user or port in database".format(id)
            )
            return False, False, False, False, False
    else:
        return False, False, False, False, False


def get_hypers_ids_with_status(status):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")
    l = list(rtable.filter({"status": status}).pluck("id").run(r_conn))
    close_rethink_connection(r_conn)
    if len(l) > 0:
        hypers = [d["id"] for d in l]
    else:
        hypers = []

    return hypers


def get_hypers_enabled_with_capabilities_status():
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")

    hypers = list(
        rtable.filter({"enabled": True})
        .pluck("capabilities", "status", "id", "thread_status")
        .run(r_conn)
    )

    close_rethink_connection(r_conn)
    return hypers


def get_hyp_hostname_user_port_from_id(id):
    r_conn = new_rethink_connection()
    l = r.table("hypervisors").get(id).pluck("hostname", "user", "port").run(r_conn)
    close_rethink_connection(r_conn)

    if len(l) > 0:
        if l.__contains__("user") and l.__contains__("port"):
            return l
        else:
            log.error(
                "hypervisor {} does not contain user or port in database".format(id)
            )
            return False
    else:
        return False


def update_all_hyps_status(reset_status="Offline", reset_thread_status="Stopped"):
    r_conn = new_rethink_connection()
    d_reset_thread_status = {
        "worker": reset_thread_status,
        "disk_operations": reset_thread_status,
    }
    results = (
        r.table("hypervisors")
        .update(
            {
                "status": reset_status,
                "thread_status": d_reset_thread_status,
                "degraded": {"is_degraded": False, "reason": None, "since": None},
                "libvirt_warning": None,
            }
        )
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return results


def get_pool_hypers_conf(id_pool="default"):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors_pools")

    result = rtable.get(id_pool).run(r_conn)

    close_rethink_connection(r_conn)
    return result


def get_diskopts_online(
    id_pool="default",
    forced_hyp=None,
    favourite_hyp=None,
):
    r_conn = new_rethink_connection()
    disk_opts_online = list(
        r.table("hypervisors")
        .filter({"status": "Online", "capabilities": {"disk_operations": True}})
        .filter(r.row["storage_pools"].contains(id_pool))
        .pluck("id", "only_forced", "gpu_only", "stats", "mountpoints")
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return filter_available_hypers(
        disk_opts_online,
        forced_hyp=forced_hyp,
        favourite_hyp=favourite_hyp,
        exclude_outofmem=False,
    )


def get_hypers_online(
    id_pool="default",
    forced_hyp=None,
    favourite_hyp=None,
    storage_pool_id=None,
):
    r_conn = new_rethink_connection()
    hypers_online = list(
        r.table("hypervisors")
        .filter({"status": "Online", "capabilities": {"hypervisor": True}})
        .filter(r.row["hypervisors_pools"].contains(id_pool))
        .pluck(
            "id",
            "only_forced",
            "gpu_only",
            "storage_pools",
            "enabled_storage_pools",
            "virt_pools",
            "enabled_virt_pools",
            "info",
            "stats",
            "mountpoints",
            "min_free_mem_gb",
            "min_free_gpu_mem_gb",
            "hugepages_info",
            "numa_topology",
            "libvirt_warning",  # Include warning state for balancer
            "degraded",  # Include degraded state for webapp display
            "cap_status",  # Include cap_status for balancer operation
            "gpu_warnings",  # GPU configuration issues for admin display
        )
        .run(r_conn)
    )
    close_rethink_connection(r_conn)

    # exclude gpu_only as this function is for non gpu desktops
    hypers_online = [h for h in hypers_online if not h.get("gpu_only")]

    hypers_online = [
        hyp
        for hyp in hypers_online
        if storage_pool_id
        in hyp.get(
            "enabled_virt_pools",
            hyp.get("virt_pools", hyp.get("storage_pools", []))
            and storage_pool_id
            in hyp.get("enabled_storage_pools", hyp.get("storage_pools", [])),
        )
    ]

    return filter_available_hypers(
        hypers_online,
        forced_hyp=forced_hyp,
        favourite_hyp=favourite_hyp,
        exclude_gpu=True,
        exclude_outofmem=True,
    )


def filter_available_hypers(
    hypers_online,
    forced_hyp=None,
    favourite_hyp=None,
    exclude_gpu=False,
    exclude_outofmem=True,
):
    # exclude hypers with low memory (HYPER_FREE_MEM)
    if exclude_outofmem:
        hypers_online = filter_outofmem_hypers(hypers_online)

    # exclude hypers with gpu
    # NOTE: we are not excluding gpu when we are looking for disk operations,
    #       we are only excluding gpu when we are looking for hypervisors
    if exclude_gpu:
        # Hypers with mem ram reserved for gpu guests should be dynamic
        hypers_online = [
            h
            for h in hypers_online
            if int(h.get("min_free_gpu_mem_gb", 0)) == 0
            and not h.get("gpu_only", False)
        ] + [h for h in hypers_online if int(h.get("min_free_gpu_mem_gb", 0)) != 0]

    # check if forced_hyp is online - return it regardless of warning state
    if forced_hyp:
        forced_hyp_found = [h for h in hypers_online if h["id"] in forced_hyp]
        if len(forced_hyp_found):
            return forced_hyp_found
        return []

    # exclude hypers with min_free_gpu_mem_gb > 0 if there is more than one online
    hypers_online = filter_outofGPUmem_hypers(hypers_online)

    # exclude now hypers only_forced
    hypers_online = [h for h in hypers_online if not h.get("only_forced")]

    if favourite_hyp:
        favourite_hyp_found = [h for h in hypers_online if h["id"] in favourite_hyp]
        if len(favourite_hyp_found):
            return favourite_hyp_found

    # Prefer hypervisors without libvirt_warning (healthy over warned)
    # Fall back to warned hypervisors if no healthy ones available
    hypers_online = filter_warned_hypers(hypers_online)

    return hypers_online


def filter_warned_hypers(hypers_online):
    """Filter hypervisors to prefer healthy ones over warned ones.

    Hypervisors with libvirt_warning are still usable but are experiencing
    slow responses. We prefer healthy hypervisors but use warned ones if
    no alternatives are available.

    Args:
        hypers_online: List of hypervisor dicts

    Returns:
        List of hypervisors, preferring healthy ones
    """
    if not hypers_online:
        return []

    # Separate healthy and warned hypervisors
    healthy = [h for h in hypers_online if not h.get("libvirt_warning")]
    warned = [h for h in hypers_online if h.get("libvirt_warning")]

    # If healthy hypervisors available, use only those
    if healthy:
        if warned:
            logs.workers.debug(
                f"Preferring {len(healthy)} healthy hypervisors over "
                f"{len(warned)} warned hypervisors"
            )
        return healthy

    # No healthy hypervisors, fall back to warned
    if warned:
        logs.workers.warning(
            f"No healthy hypervisors available, using {len(warned)} warned hypervisors"
        )
        return warned

    return hypers_online


def filter_outofGPUmem_hypers(hypers_online):
    # At least one hyper will be kept for everything if there is only one
    # Here we've got also the only forceds
    if len(hypers_online) == 1:
        hyper = hypers_online[0]
        if int(hyper.get("min_free_gpu_mem_gb", 0)) != 0 and hyper.get(
            "gpu_only", False
        ):
            r_conn = new_rethink_connection()
            rtable = r.table("hypervisors")
            rtable.get(hyper["id"]).update({"gpu_only": False}).run(r_conn)
            close_rethink_connection(r_conn)
        return hypers_online

    # Now we are sure that there are at least two hypers
    hypers_with_ram = []
    for hyper in hypers_online:
        # Not reserved memory for gpu guests
        if int(hyper.get("min_free_gpu_mem_gb", 0)) == 0:
            hypers_with_ram.append(hyper)
            continue
        if (
            int(hyper.get("stats", {}).get("mem_stats", {}).get("available", 0))
            > int(hyper.get("min_free_gpu_mem_gb", 0)) * 1048576
            + int(hyper.get("min_free_mem_gb", 0)) * 1048576
        ):
            # Hypervisor has enough memory for gpu guests and normal guests. only_gpu = False
            hypers_with_ram.append(hyper)
            if hyper.get("gpu_only", False):
                r_conn = new_rethink_connection()
                rtable = r.table("hypervisors")
                rtable.get(hyper["id"]).update({"gpu_only": False}).run(r_conn)
                close_rethink_connection(r_conn)
        else:
            # Hypervisor has not enough memory for gpu guests. only_gpu = True
            if not hyper.get("gpu_only", False):
                r_conn = new_rethink_connection()
                rtable = r.table("hypervisors")
                rtable.get(hyper["id"]).update({"gpu_only": True}).run(r_conn)
                close_rethink_connection(r_conn)
    return hypers_with_ram


def filter_outofmem_hypers(hypers_online):
    hypers_with_ram = []
    for hyper in hypers_online:
        if (
            int(hyper.get("stats", {}).get("mem_stats", {}).get("available", 0))
            >= int(hyper.get("min_free_mem_gb", 0)) * 1048576
        ):
            hypers_with_ram.append(hyper)
        else:
            logs.workers.error(
                "Hyper %s removed from start desktops pool because low available ram. %s"
                % (
                    hyper["id"],
                    hyper,
                )
            )
    if not len(hypers_with_ram):
        logs.workers.error(
            "No hypers left with ram available to start desktops from %s active."
            % len(hypers_online)
        )
        return []
    logs.workers.debug("--------------------------------------")
    logs.workers.debug(
        "hypers_with_ram: %s"
        % int(hyper.get("stats", {}).get("mem_stats", {}).get("available", 0))
    )
    logs.workers.debug("--------------------------------------")
    return hypers_with_ram


def _expand_cpu_ranges(cpulist):
    """Expand a Linux cpulist string ("0-47,96-143") into a set of CPU ids.

    Tolerant of empties / spaces / malformed parts (skipped). Used to map a
    desktop's pinned cpuset onto a host NUMA node whose cpulist may be
    non-contiguous (e.g. SMT siblings live in a second range).
    """
    out = set()
    if not cpulist:
        return out
    for part in str(cpulist).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                out.update(range(int(lo), int(hi) + 1))
            except ValueError:
                continue
        else:
            try:
                out.add(int(part))
            except ValueError:
                continue
    return out


def _resolve_numa_node_for_cpuset(numa_nodes, cpuset):
    """Return the NUMA node id (int) whose cpulist best covers ``cpuset``.

    ``numa_nodes`` is ``numa_topology["nodes"]`` ({node_id: {"cpulist": ...}}).
    Picks the node with the largest overlap with the desktop's pinned cpuset.
    Returns None when nothing is resolvable (no cpuset, no topology, no overlap)
    so the caller falls back to its default placement.
    """
    want = _expand_cpu_ranges(cpuset)
    if not want or not numa_nodes:
        return None
    best, best_overlap = None, 0
    for nid, nd in numa_nodes.items():
        overlap = len(want & _expand_cpu_ranges((nd or {}).get("cpulist")))
        if overlap > best_overlap:
            best_overlap, best = overlap, nid
    if best is None:
        return None
    try:
        return int(best)
    except (TypeError, ValueError):
        return None


def get_hypers_gpu_online(
    id_pool="default",
    forced_hyp=None,
    favourite_hyp=None,
    gpu_brand_model_profile=None,
    forced_gpus_hypervisors=None,
    exclude_outofmem=True,
    storage_pool_id=None,
    prefer_cpuset=None,
    prefer_numa_node=None,
):
    r_conn = new_rethink_connection()
    hypers_online = list(
        r.table("hypervisors")
        .filter({"status": "Online"})
        .filter(r.row["hypervisors_pools"].contains(id_pool))
        .pluck(
            "id",
            "only_forced",
            "gpu_only",
            "storage_pools",
            "enabled_storage_pools",
            "virt_pools",
            "enabled_virt_pools",
            "info",
            "stats",
            "mountpoints",
            "min_free_mem_gb",
            "min_free_gpu_mem_gb",
            "hugepages_info",
            "numa_topology",
            "pci_devices",
        )
        .run(r_conn)
    )
    close_rethink_connection(r_conn)

    hypers_online = [
        hyp
        for hyp in hypers_online
        if storage_pool_id
        in hyp.get(
            "enabled_virt_pools",
            hyp.get("virt_pools", hyp.get("storage_pools", []))
            and storage_pool_id
            in hyp.get("enabled_storage_pools", hyp.get("storage_pools", [])),
        )
    ]

    # exclude hypers with low memory (HYPER_FREE_MEM)
    if exclude_outofmem:
        hypers_online = filter_outofmem_hypers(hypers_online)

    # Check profile format: "NVIDIA-A10-2Q" or "NVIDIA-RTXPro6000BlackwellDC-1-12Q"
    # Use split with maxsplit=2 to handle profiles with dashes (e.g., "1-12Q")
    try:
        parts = gpu_brand_model_profile.split("-", 2)
        if len(parts) != 3:
            raise ValueError("Expected 3 parts")
        gpu_brand, gpu_model, gpu_profile = parts
    except:
        logs.workers.error(
            f"Error parsing gpu_profile: {gpu_brand_model_profile}. Not in format BRAND-MODEL-PROFILE"
        )
        return []

    hypers_online_with_gpu = [
        h
        for h in hypers_online
        if len(
            [i for i in h.get("info", {}).get("nvidia", {}).values() if i == gpu_model]
        )
        > 0
    ]

    if forced_hyp:
        forced_hyp_found = [h for h in hypers_online_with_gpu if h["id"] in forced_hyp]
        if len(forced_hyp_found) > 0:
            hypers_online_with_gpu = forced_hyp_found
        else:
            return []

    if favourite_hyp:
        favourite_hyp_found = [
            h for h in hypers_online_with_gpu if h["id"] in favourite_hyp
        ]
        if len(favourite_hyp_found) > 0:
            hypers_online_with_gpu = favourite_hyp_found

    if forced_gpus_hypervisors:
        hypers_online_with_gpu = [
            h for h in hypers_online_with_gpu if h["id"] in forced_gpus_hypervisors
        ]
        if not len(hypers_online_with_gpu):
            return []

    hypervisors_with_available_profile = []
    # now find hypervisors with free uuids:
    for h in hypers_online_with_gpu:
        hyper_with_free_uuid = False
        selected_mig = False
        numa_nodes = (h.get("numa_topology", {}) or {}).get("nodes", {}) or {}
        host_multinode = len(numa_nodes) > 1
        # Preferred NUMA node on this host: an explicit node hint wins (used to
        # group the 2nd..Nth card of a multi-GPU desktop on the 1st card's
        # node), else derive it from the desktop's pinned cpuset against this
        # host's topology. Only meaningful on multi-node hosts.
        target_node = None
        if host_multinode:
            if prefer_numa_node is not None:
                try:
                    target_node = int(prefer_numa_node)
                except (TypeError, ValueError):
                    target_node = None
            elif prefer_cpuset:
                target_node = _resolve_numa_node_for_cpuset(numa_nodes, prefer_cpuset)
        pdev = h.get("pci_devices", {}) or {}
        # Collect every free card of the model on this host (with its NUMA node)
        # so the preference can pick among them; with no preference this reduces
        # to the historical "first free card".
        free_cards = []  # (pci, gpu_id, mdev_uuid, mig, numa_node)
        for pci_k, model in h["info"]["nvidia"].items():
            if model != gpu_model:
                continue
            gpu_id_k = h["id"] + "-" + pci_k
            gpu_profile_active, mdevs = get_vgpus_mdevs(gpu_id_k, gpu_profile)
            # get_vgpus_mdevs plucks {"mdevs": [gpu_profile]}, so a card whose
            # pool lacks that key (mid-transition, stale active field, pool not
            # yet rebuilt) yields an EMPTY mdevs dict - treat it as "no free
            # uuid on this card" instead of KeyError-ing the whole start action.
            # A multi-vGPU desktop probes every requested profile against every
            # card of the model, which makes this window easy to hit.
            if gpu_profile_active != gpu_profile:
                continue
            for mdev_uuid_k, d in mdevs.get(gpu_profile, {}).items():
                if (
                    d.get("domain_reserved", False) is False
                    and d.get("domain_started", False) is False
                    and d.get("created", False) is True
                ):
                    pci_sysfs_k = pci_k[4:].replace("_", ":", 2)
                    pci_sysfs_k = (
                        pci_sysfs_k[: len(pci_sysfs_k) - 2] + "." + pci_sysfs_k[-1]
                    )
                    nn = pdev.get(pci_sysfs_k, {}).get("numa_node")
                    free_cards.append(
                        (pci_k, gpu_id_k, mdev_uuid_k, bool(d.get("mig", False)), nn)
                    )
                    # one free uuid is enough to mark this card available
                    break
        if free_cards:
            # NUMA preference: prefer a free card on target_node; a card with an
            # unknown (-1/None) numa_node matches any node. Fall back to the
            # first free card so NUMA is only ever a preference, never a reason
            # to refuse a start (single-node hosts / -1 cards behave as before).
            chosen = None
            if target_node is not None:
                for fc in free_cards:
                    nn = fc[4]
                    if nn is not None and int(nn) >= 0 and int(nn) == target_node:
                        chosen = fc
                        break
            if chosen is None:
                chosen = free_cards[0]
            # MIG-backed mdevs need display='off' in the guest XML; carry the
            # per-mdev flag to the XML builder.
            pci, gpu_id, mdev_uuid, selected_mig, _chosen_nn = chosen
            hyper_with_free_uuid = True
        if hyper_with_free_uuid:
            logs.workers.info(
                f"hypervisor with available profile gpu: {h['id']}, uuid_selected: {mdev_uuid}, "
                + f"gpu_profile: {gpu_brand_model_profile}, gpu_id: {gpu_id}"
            )
            # Look up GPU NUMA node from pci_devices (sysfs format)
            # pci is in libvirt format "pci_0000_41_00_0", convert to "0000:41:00.0"
            pci_sysfs = pci[4:].replace("_", ":", 2)  # "0000:41:00_0"
            pci_sysfs = (
                pci_sysfs[: len(pci_sysfs) - 2] + "." + pci_sysfs[-1]
            )  # "0000:41:00.0"
            gpu_numa_node = h.get("pci_devices", {}).get(pci_sysfs, {}).get("numa_node")
            # Companion PCI BDFs (e.g. HD-audio .1 on display-mode NVIDIA
            # boards) live in vgpus.info — pulled here so the domain XML
            # rewrite at start time can emit both functions as a
            # multifunction pair without an extra round-trip.
            companion_pci_bdfs = []
            try:
                r_conn = new_rethink_connection()
                try:
                    vgpu_info = (
                        r.table("vgpus")
                        .get(gpu_id)
                        .pluck({"info": "companion_pci_bdfs"})
                        .run(r_conn)
                    )
                    companion_pci_bdfs = (
                        vgpu_info.get("info", {}).get("companion_pci_bdfs") or []
                    )
                finally:
                    close_rethink_connection(r_conn)
            except Exception as e:
                logs.workers.debug(
                    f"Could not fetch companion_pci_bdfs for {gpu_id}: {e}"
                )
            hypervisors_with_available_profile.append(
                {
                    **h,
                    **{
                        "gpu_selected": {
                            "uuid_selected": mdev_uuid,
                            "next_hyp": h["id"],
                            "next_available_uid": mdev_uuid,
                            "next_gpu_id": gpu_id,
                            "gpu_profile": gpu_brand_model_profile,
                            "pci_bus_id": pci,
                            "mig": selected_mig,
                            "companion_pci_bdfs": companion_pci_bdfs,
                            "hugepages_info": h.get("hugepages_info", {}),
                            "hugepages_free_kb": h.get("stats", {})
                            .get("mem_stats", {})
                            .get("hugepages_free_kb", 0),
                            "numa_hugepages_free_kb": h.get("stats", {})
                            .get("mem_stats", {})
                            .get("numa_hugepages_free_kb", {}),
                            "gpu_numa_node": gpu_numa_node,
                            "numa_topology": h.get("numa_topology", {}),
                        }
                    },
                }
            )

    if not len(hypervisors_with_available_profile):
        logs.workers.error("No free mdevs found for gpu_profile: %s" % gpu_profile)
        return []

    if forced_hyp:
        # return hypervisors_with_available_profile if it's id is in forced_hyp list
        return [h for h in hypervisors_with_available_profile if h["id"] in forced_hyp]

    if forced_gpus_hypervisors:
        # If force_gpus is set, we return the hypervisors with the
        # profiles requested. If no hypervisor is found, we return an empty
        # list.

        return [
            h["id"]
            for h in hypers_online_with_gpu
            if h["id"] in hypervisors_with_available_profile
        ]

    # exclude now hypers only_forced
    hypervisors_with_available_profile = [
        h for h in hypervisors_with_available_profile if not h.get("only_forced")
    ]

    if favourite_hyp:
        favourite_hyp_found = [
            h for h in hypervisors_with_available_profile if h["id"] in favourite_hyp
        ]
        if len(favourite_hyp_found):
            return favourite_hyp_found

    return hypervisors_with_available_profile


def get_hypers_in_pool(
    id_pool="default",
    only_online=True,
    exclude_hyp_only_forced=False,
    exclude_hyp_gpu_only=False,
):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")

    l_forced = []
    l_gpu_only = []
    d_filter = {}
    if only_online:
        d_filter["status"] = "Online"

    if exclude_hyp_only_forced is True:
        d_filter_only_forced = d_filter.copy()
        d_filter_only_forced["only_forced"] = True
        l_forced = list(
            rtable.filter(r.row["hypervisors_pools"].contains(id_pool))
            .filter(d_filter_only_forced)
            .pluck("id")
            .run(r_conn)
        )

    if exclude_hyp_gpu_only is True:
        d_filter_gpu_only = d_filter.copy()
        d_filter_gpu_only["gpu_only"] = True
        l_gpu_only = list(
            rtable.filter(r.row["hypervisors_pools"].contains(id_pool))
            .filter(d_filter_gpu_only)
            .pluck("id")
            .run(r_conn)
        )

    l = list(
        rtable.filter(r.row["hypervisors_pools"].contains(id_pool))
        .filter(d_filter)
        .pluck("id")
        .run(r_conn)
    )

    close_rethink_connection(r_conn)

    hyps_gpu_only = [a["id"] for a in l_gpu_only]
    hyps_only_forced = [a["id"] for a in l_forced]
    hyps_all = [a["id"] for a in l]
    hyps_to_start = [
        a["id"] for a in l if a["id"] not in (hyps_only_forced + hyps_gpu_only)
    ]

    return hyps_to_start, hyps_only_forced, hyps_all


def update_db_hyp_info(id, hyp_info):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")

    rtable.filter({"id": id}).update({"info": hyp_info}).run(r_conn)
    close_rethink_connection(r_conn)


def get_gpu_card_models(hyper_id):
    """Return the canonical card-bound model for each auto-discovered GPU.

    Reads ``gpus.model`` for every auto card belonging to ``hyper_id``
    (rows with ``id`` matching ``auto-{hyper_id}-pci_*``).  The model is
    bound on the card by the API at first registration and treated as
    immutable, so any caller that needs the canonical model name for a
    given PCI slot should consult this rather than the freshly-discovered
    ``nvidia_gpus`` payload.

    Returns a dict keyed by libvirt-style PCI name (``pci_0000_41_00_0``)
    mapping to the card's stored model string.  Cards without a model are
    skipped.
    """
    r_conn = new_rethink_connection()
    prefix = f"auto-{hyper_id}-"
    try:
        rows = list(
            r.table("gpus")
            .filter(lambda gpu: gpu["id"].match(f"^{prefix}"))
            .pluck("id", "model")
            .run(r_conn)
        )
    finally:
        close_rethink_connection(r_conn)

    result = {}
    for row in rows:
        model = row.get("model")
        if not model:
            continue
        pci_name = row["id"][len(prefix) :]
        result[pci_name] = model
    return result


def get_vgpu_model_profile_change(vgpu_id):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")
    try:
        d = (
            rtable.get(vgpu_id)
            .pluck("model", "vgpu_profile", "changing_to_profile")
            .run(r_conn)
        )
    except ReqlNonExistenceError:
        close_rethink_connection(r_conn)
        return False
    close_rethink_connection(r_conn)
    return d


def get_vgpu_info(vgpu_id):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")
    out = False
    try:
        out = rtable.get(vgpu_id).pluck("hyp_id", "info").run(r_conn)
    except ReqlNonExistenceError:
        close_rethink_connection(r_conn)
        return False
    close_rethink_connection(r_conn)
    return out


def get_domains_started_in_vgpu(vgpu_id):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")

    profile = rtable.get(vgpu_id).pluck("vgpu_profile").run(r_conn)["vgpu_profile"]
    mdevs = (
        rtable.get(vgpu_id)
        .pluck({"mdevs": [profile]})
        .run(r_conn)["mdevs"]
        .get(profile, {})
    )
    l_domains = [
        i["domain_started"]
        for i in mdevs.values()
        if type(i.get("domain_started", False)) is str and len(i["domain_started"]) > 0
    ]

    close_rethink_connection(r_conn)
    return l_domains


def update_vgpu_uuids(vgpu_id, d_uuids):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")

    rtable.filter({"id": vgpu_id}).update({"mdevs": d_uuids}).run(r_conn)
    close_rethink_connection(r_conn)


def replace_vgpu_profile_mdevs(vgpu_id, profile, mdevs_for_profile):
    """Replace the mdev map for a single profile wholesale.

    RethinkDB's default update deep-merges, so callers rebuilding a
    profile's UUID pool (e.g. a profile switch that right-sizes to
    driver max_instance) cannot shrink the map with a plain update.
    ``r.literal`` replaces the target sub-dict verbatim without
    touching sibling profiles.
    """
    r_conn = new_rethink_connection()
    r.table("vgpus").get(vgpu_id).update(
        {"mdevs": {profile: r.literal(mdevs_for_profile)}}
    ).run(r_conn)
    close_rethink_connection(r_conn)


def ingest_applied_state(vgpu_id, patch):
    """Apply a ``vgpu_state.build_applied_state_patch`` patch to a vgpus row,
    wrapping ``mdevs`` in ``r.literal`` so the hypervisor-reported pool REPLACES
    wholesale (RethinkDB's default update deep-merges, which would double a
    racing engine-seeded pool). Mirrors the API's gpu_applied ingest so a
    runtime apply the engine drives over SSH and the registration apply write
    byte-identical rows.
    """
    r_conn = new_rethink_connection()
    if "mdevs" in patch:
        patch = {**patch, "mdevs": r.literal(patch["mdevs"])}
    r.table("vgpus").get(vgpu_id).update(patch).run(r_conn)
    close_rethink_connection(r_conn)


def get_vgpu_full(vgpu_id):
    r_conn = new_rethink_connection()
    try:
        out = r.table("vgpus").get(vgpu_id).run(r_conn)
    except ReqlNonExistenceError:
        out = None
    close_rethink_connection(r_conn)
    return out


def get_domains_vgpu_uuids():
    """Set of mdev UUIDs referenced by ANY domain's ``vgpu_info``.

    A domain (running, reserved, or merely Stopped with a stale binding)
    points at its mdev only through ``domains.vgpu_info.uuid`` — the pool
    entry's own ``domain_started``/``domain_reserved`` flags can lag. Used
    as a belt-and-suspenders cross-check so pool self-heal never trims a
    UUID a domain still claims.
    """
    r_conn = new_rethink_connection()
    try:
        rows = r.table("domains").has_fields("vgpu_info").pluck("vgpu_info").run(r_conn)
        # vgpu_info is a list of per-mdev bindings (legacy installs: a single
        # dict). Collect every referenced uuid so pool self-heal never trims a
        # uuid any domain still claims.
        out = set()
        for d in rows:
            vi = d.get("vgpu_info")
            if isinstance(vi, list):
                out.update(e.get("uuid") for e in vi if e.get("uuid"))
            elif isinstance(vi, dict) and vi.get("uuid"):
                out.add(vi["uuid"])
    finally:
        close_rethink_connection(r_conn)
    return out


def add_vgpu_uuids(
    vgpu_id,
    additions,
    sub_paths=None,
    replace_mdevs=False,
    mdevs_last_synced_at=None,
):
    """Update a vgpu row's mdev pool.

    additions: {profile_name: {uuid: entry_dict}}. In top-up mode (default)
        these are only NEW UUIDs that get deep-merged into mdevs. In
        authoritative-rebuild mode (replace_mdevs=True) these fully replace
        mdevs — any profile/UUID not in ``additions`` is discarded.
    sub_paths: optional sub_paths list to write into info.sub_paths. Always
        replaces the existing list when provided.
    replace_mdevs: when True, replace ``mdevs`` wholesale via ``r.literal``.
        Used after the hypervisor boot wipes its sysfs mdevs so the DB pool
        becomes the single source of truth for the fresh VFs.
    mdevs_last_synced_at: when set, write this timestamp on the row so the
        next reconcile can tell whether a later hypervisor reset has happened
        since.

    Top-up mode preserves active ``domain_started`` / ``domain_reserved``
    bindings by relying on RethinkDB's deep-merge update. Replace mode does
    NOT preserve them — caller is responsible for transitioning orphaned
    domains to ``Stopped`` before (or right after) this call.
    """
    if not additions and sub_paths is None and mdevs_last_synced_at is None:
        return
    r_conn = new_rethink_connection()
    patch = {}
    if replace_mdevs:
        patch["mdevs"] = r.literal(additions or {})
    elif additions:
        patch["mdevs"] = additions
    if sub_paths is not None:
        patch["info"] = {"sub_paths": list(sub_paths)}
    if mdevs_last_synced_at is not None:
        patch["mdevs_last_synced_at"] = mdevs_last_synced_at
    r.table("vgpus").get(vgpu_id).update(patch).run(r_conn)
    close_rethink_connection(r_conn)


def update_vgpu_uuid_started_in_domain(hyp_id, pci_id, profile, mdev_uuid, domain_id):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")
    vgpu_id = "-".join([hyp_id, pci_id])
    rtable.filter({"id": vgpu_id}).update(
        {"mdevs": {profile: {mdev_uuid: {"domain_started": domain_id}}}}
    ).run(r_conn)
    close_rethink_connection(r_conn)


def update_vgpu_uuid_reserved_in_domain(hyp_id, pci_id, profile, mdev_uuid, domain_id):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")
    vgpu_id = "-".join([hyp_id, pci_id])
    rtable.filter({"id": vgpu_id}).update(
        {"mdevs": {profile: {mdev_uuid: {"domain_reserved": domain_id}}}}
    ).run(r_conn)
    close_rethink_connection(r_conn)


def reset_vgpu_created_started(hyp_id, pci_id, d_mdevs_running):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")
    vgpu_id = "-".join([hyp_id, pci_id])
    out = rtable.get(vgpu_id).run(r_conn)
    for profile, d in out["mdevs"].items():
        for uuid64, d_uid in d.items():
            d_uid["created"] = True if uuid64 in d_mdevs_running.keys() else False
            d_uid["domain_started"] = False
            d_uid["domain_reserved"] = False
    rtable.filter({"id": vgpu_id}).update({"mdevs": out["mdevs"]}).run(r_conn)
    close_rethink_connection(r_conn)


def update_vgpu_profile(vgpu_id, vgpu_profile):
    """Set the currently-active runtime vgpu_profile.

    Engine writes this after a successful driver transition; reconcile must
    never write this directly without going through change_vgpu_profile.
    """
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")

    rtable.filter({"id": vgpu_id}).update({"vgpu_profile": vgpu_profile}).run(r_conn)
    close_rethink_connection(r_conn)


def _mirror_operator_intent_to_catalog(vgpu_id, fields):
    """Persist operator GPU intent durably in the gpus CATALOG row.

    The live ``vgpus`` row is deleted+recreated on every hypervisor (re)start,
    so operator intent stored only there is lost across a reboot -- the card
    comes back un-intented and ``compute_gpu_targets`` no longer applies the
    operator's passthrough (the cards had to be re-forced by hand). The ``gpus``
    catalog row (keyed by ``physical_device == vgpu_id``) is persistent, so we
    mirror the intent there; ``compute_gpu_targets`` re-seeds from it at
    registration when the fresh vgpus row carries no intent. Best-effort: a
    catalog write failure must not break the operator force.
    """
    r_conn = new_rethink_connection()
    try:
        r.table("gpus").filter({"physical_device": vgpu_id}).update(fields).run(r_conn)
    except Exception as e:
        logs.main.warning(
            f"could not mirror operator intent {fields} to gpus catalog "
            f"for {vgpu_id}: {e}"
        )
    finally:
        close_rethink_connection(r_conn)


def update_requested_profile(vgpu_id, requested_profile):
    """Set operator-requested profile for this vgpu.

    Only writers: the set_gpu_profile API endpoint and the one-time backfill.
    Reconcile/discovery code paths must NEVER call this — that conflation is
    the bug we are fixing.
    """
    r_conn = new_rethink_connection()
    r.table("vgpus").filter({"id": vgpu_id}).update(
        {"requested_profile": requested_profile}
    ).run(r_conn)
    close_rethink_connection(r_conn)
    # Durable mirror so the intent survives a hypervisor restart (see helper).
    _mirror_operator_intent_to_catalog(
        vgpu_id, {"operator_requested_profile": requested_profile}
    )


def update_operator_passthrough(vgpu_id, flag):
    """Mark whether the operator explicitly chose passthrough for this vgpu.

    Used by the engine startup re-apply loop to know whether vfio-pci
    binding should survive across container/host restarts. A True value
    here is the *durable* form of "operator chose passthrough" and is the
    only signal that triggers the re-apply — never the transient
    ``vgpu_profile == "passthrough"`` (which could have been written by
    the legacy buggy reconcile path).
    """
    r_conn = new_rethink_connection()
    r.table("vgpus").filter({"id": vgpu_id}).update(
        {"operator_passthrough": bool(flag)}
    ).run(r_conn)
    close_rethink_connection(r_conn)
    # Durable mirror so the intent survives a hypervisor restart (see helper).
    _mirror_operator_intent_to_catalog(vgpu_id, {"operator_passthrough": bool(flag)})


def update_db_hyp_nvidia_info(hyp_id, d_info_nvidia):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")
    # Per-card map vgpu_id -> applied_by_hypervisor, returned so the caller can
    # skip its own UUID/profile seeding for cards the hypervisor already applied.
    applied_flags = {}
    for pci_bus, d_vgpu in d_info_nvidia.items():
        vgpu_id = "-".join([hyp_id, pci_bus])
        # Read existing operator-intent fields BEFORE delete so they survive
        # the re-insert. The delete+insert pattern wipes the row entirely;
        # without this preservation step, every fresh discovery erases the
        # operator's profile choice — which is one of the defects this
        # redesign fixes.
        preserved = {
            "requested_profile": None,
            "operator_passthrough": False,
            "force_selected_profile": False,
            # Hypervisor-applied state. When the hypervisor applies the profile
            # itself at registration (gpu_apply_capable) the API records the
            # applied profile + mdev pool here. The engine relies on what the
            # hypervisor set at boot, so this delete+insert must NOT wipe it —
            # otherwise the next reconcile re-derives passthrough and re-applies
            # over SSH, defeating the hypervisor-owns-GPU handoff.
            "vgpu_profile": None,
            "mdevs": {},
            "mdevs_reset_at": None,
            "mdevs_last_synced_at": None,
            "applied_by_hypervisor": False,
        }
        try:
            existing = rtable.get(vgpu_id).run(r_conn)
        except ReqlNonExistenceError:
            existing = None
        if existing:
            preserved["requested_profile"] = existing.get("requested_profile")
            preserved["operator_passthrough"] = bool(
                existing.get("operator_passthrough", False)
            )
            preserved["force_selected_profile"] = bool(
                existing.get("force_selected_profile", False)
            )
            preserved["vgpu_profile"] = existing.get("vgpu_profile")
            preserved["mdevs"] = existing.get("mdevs") or {}
            preserved["mdevs_reset_at"] = existing.get("mdevs_reset_at")
            preserved["mdevs_last_synced_at"] = existing.get("mdevs_last_synced_at")
            preserved["applied_by_hypervisor"] = bool(
                existing.get("applied_by_hypervisor", False)
            )
        try:
            rtable.get(vgpu_id).delete().run(r_conn)
        except ReqlNonExistenceError:
            pass
        d = {}
        d["id"] = vgpu_id
        d["hyp_id"] = hyp_id
        d["force_selected_profile"] = preserved["force_selected_profile"]
        d["changing_to_profile"] = False
        d["requested_profile"] = preserved["requested_profile"]
        d["operator_passthrough"] = preserved["operator_passthrough"]
        d["nvidia_uids"] = {}
        d["info"] = d_vgpu
        d["model"] = d_vgpu["model"]
        d["brand"] = "NVIDIA"
        # Carry the hypervisor-applied state across the re-insert (see preserve
        # comment above). Only emit keys we actually have, so a never-applied
        # card stays clean for the engine's own seeding below.
        d["applied_by_hypervisor"] = preserved["applied_by_hypervisor"]
        if preserved["applied_by_hypervisor"]:
            d["vgpu_profile"] = preserved["vgpu_profile"]
            d["mdevs"] = preserved["mdevs"]
            if preserved["mdevs_reset_at"] is not None:
                d["mdevs_reset_at"] = preserved["mdevs_reset_at"]
            if preserved["mdevs_last_synced_at"] is not None:
                d["mdevs_last_synced_at"] = preserved["mdevs_last_synced_at"]
        rtable.insert(d).run(r_conn)
        applied_flags[vgpu_id] = preserved["applied_by_hypervisor"]

        # Check if a GPU card already has this physical_device assigned
        already_assigned = list(
            r.table("gpus")
            .filter({"physical_device": vgpu_id})
            .pluck("id", "model")
            .run(r_conn)
        )
        if len(already_assigned) > 0:
            # Card already bound to this device — leave it alone.  The
            # card's model is immutable once set by the API at first
            # registration; never overwrite from engine-side fresh
            # discovery, otherwise gpu_profiles and reservables_vgpus
            # drift away from existing desktops on driver updates.
            pass
        else:
            # No card has this device yet — find an unassigned one
            gpus = list(
                r.table("gpus")
                .filter(
                    {
                        "brand": d["brand"],
                        "model": d["model"],
                        "physical_device": None,
                    }
                )
                .pluck("id", "profiles_enabled")
                .run(r_conn)
            )
            if len(gpus) == 0:
                logs.workers.error(
                    "A new GPU has been added to Isard, but there are no GPUs defined to accomodate it! Manual PCI assignation required for "
                    + vgpu_id
                )
            else:
                r.table("gpus").get(gpus[0]["id"]).update(
                    {"physical_device": vgpu_id}
                ).run(r_conn)
                # Capacity restore: the card was detached (physical_device None)
                # and is now re-bound, so recompute total_units for its enabled
                # profiles -- symmetric to cleanup_hypervisor_gpus' detach drop,
                # else a detach+reattach permanently zeroes vGPU capacity. Count
                # only cards that still have a physical_device.
                for reservable_id in gpus[0].get("profiles_enabled") or []:
                    surv = r.table("reservables_vgpus").get(reservable_id).run(r_conn)
                    if not surv:
                        continue
                    cards = (
                        r.table("gpus")
                        .filter(
                            lambda g: g["profiles_enabled"].contains(reservable_id)
                            & g["physical_device"].default(None).ne(None)
                        )
                        .count()
                        .run(r_conn)
                    )
                    r.table("reservables_vgpus").get(reservable_id).update(
                        {"total_units": cards * (surv.get("units") or 0)}
                    ).run(r_conn)

    close_rethink_connection(r_conn)
    return applied_flags


def update_vgpu_created(vgpu_id, profile, uuid64, created=True):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")
    result = (
        rtable.get(vgpu_id)
        .update({"mdevs": {profile: {uuid64: {"created": created}}}})
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return result


def get_vgpu(vgpu_id):
    r_conn = new_rethink_connection()
    rtable = r.table("vgpus")

    try:
        out = rtable.get(vgpu_id).run(r_conn)
    except ReqlNonExistenceError:
        close_rethink_connection(r_conn)
        return False
    close_rethink_connection(r_conn)
    return out


def get_vgpu_actual_profile(vgpu_id):
    start = datetime.now(pytz.utc).strftime("%Y-%m-%dT%H:%M%z")

    r_conn = new_rethink_connection()

    try:
        gpu = list(r.table("gpus").filter({"physical_device": vgpu_id}).run(r_conn))[0]
    except:
        logs.workers.error(
            "The gpu " + vgpu_id + " has no entry in gpus table right now!"
        )
        close_rethink_connection(r_conn)
        return None

    try:
        data = list(
            r.table("resource_planner")
            .get_all(gpu["id"], index="item_id")
            .filter(
                r.row["start"]
                <= datetime.strptime(start, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
            )
            .filter(
                r.row["end"]
                >= datetime.strptime(start, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
            )
            .run(r_conn)
        )[0]
        logs.workers.info("==================================")
        logs.workers.info(
            "GPU "
            + vgpu_id
            + " has a planning for profile "
            + data["subitem_id"]
            + " now!",
        )
        logs.workers.info("==================================")
    except:
        data = []
        logs.workers.info("==================================")
        logs.workers.error(
            "FAIL AT GETTING GPU PLAN: GPU "
            + vgpu_id
            + " has no running plan for any profile now!",
        )
        logs.workers.info("==================================")
    close_rethink_connection(r_conn)
    if len(data):
        return data["subitem_id"].split("-")[-1]
    return None
