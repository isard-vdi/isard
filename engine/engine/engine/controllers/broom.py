# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8

import threading
import traceback
from time import sleep, time

from engine.config import POLLING_INTERVAL_TRANSITIONAL_STATES
from engine.models.hyp import hyp
from engine.services.db import (
    get_domain,
    get_domains_with_transitional_status,
    get_hyp_hostname_from_id,
    get_hyp_hostnames_online,
    update_domain_hyp_started,
    update_domain_status,
    update_table_field,
)
from engine.services.db.domains_status import (
    get_last_domain_status,
    insert_db_domain_status,
)
from engine.services.db.hypervisors_status import (
    get_last_hyp_status,
    insert_db_hyp_status,
)
from engine.services.lib.functions import (
    calcule_cpu_hyp_stats,
    calcule_disk_net_domain_load,
    dict_domain_libvirt_state_to_isard_state,
    get_tid,
    state_and_cause_to_str,
)
from engine.services.log import logs


class ThreadBroom(threading.Thread):
    def __init__(self, name, polling_interval, manager):
        threading.Thread.__init__(self)
        self.manager = manager
        self.name = name
        self.polling_interval = polling_interval
        self.stop = False

    def polling(self):
        cpu_stats_previous = {}
        cpu_stats_5min_previous = {}
        while self.stop is not True:

            interval = 0.0
            while interval < self.polling_interval:
                sleep(0.1)
                interval += 0.1
                if self.stop is True:
                    break
            if self.manager.check_actions_domains_enabled() is False:
                continue

            l = get_domains_with_transitional_status(also_started=True)

            list_domains_without_hyp = [d for d in l if "hyp_started" not in d.keys()]
            list_domains = [d for d in l if "hyp_started" in d.keys()]
            ids_domains_started_in_db_with_hypervisor = [a["id"] for a in list_domains]
            ids_domains_started_in_db_without_hypervisor = [
                a["id"] for a in list_domains_without_hyp
            ]

            for d in list_domains_without_hyp:
                logs.broom.error(
                    "DOMAIN {} WITH STATUS {} without HYPERVISOR".format(
                        d["id"], d["status"]
                    )
                )
                update_domain_status(
                    "Unknown",
                    d["id"],
                    detail="starting or stoping status witouth hypervisor",
                )

            hyps_with_hyp_started = set(
                [
                    d["hyp_started"]
                    for d in list_domains
                    if type(d["hyp_started"]) is str
                ]
            )
            hyps_to_try = list(get_hyp_hostnames_online().keys())

            hyps_domain_started = {}
            for hyp_id in hyps_to_try:
                try:
                    (
                        hostname,
                        port,
                        user,
                        nvidia_enabled,
                        force_get_hyp_info,
                        init_vgpu_profiles,
                    ) = get_hyp_hostname_from_id(hyp_id)
                    if hostname is False:
                        logs.broom.error(
                            "hyp {} with id has not hostname or is nos in database".format(
                                hyp_id
                            )
                        )
                    else:
                        previous = time()

                        h = hyp(hostname, user=user, port=port)
                        if h.connected:
                            hyps_domain_started[hyp_id] = {}
                            hyps_domain_started[hyp_id]["hyp"] = h
                            d_domains_status_from_hyp = h.get_domains()
                            if d_domains_status_from_hyp is None:
                                d_domains_status_from_hyp = {}

                            # check if domain running in hypervisor is not defined in database
                            domains_destroyed = []
                            domains_debugging = []
                            for id_domain, status in d_domains_status_from_hyp.items():
                                if (
                                    id_domain
                                    not in ids_domains_started_in_db_with_hypervisor
                                ):
                                    if (
                                        id_domain
                                        not in ids_domains_started_in_db_with_hypervisor
                                    ):
                                        # starting with _debug_ not destroyed by broom
                                        if id_domain.find("_debug_") != 0:
                                            d_domain = get_domain(id_domain)
                                            if d_domain is None:
                                                try:
                                                    domain_handler = (
                                                        h.conn.lookupByName(id_domain)
                                                    )
                                                    domain_handler.destroy()
                                                    domains_destroyed.append(id_domain)
                                                    logs.broom.error(
                                                        f"broom destroyed domain not in database {id_domain} in hypervisor {hyp_id}"
                                                    )
                                                except Exception as e:
                                                    logs.broom.error(
                                                        f"EXCEPTION when try to destroy domain not in database {id_domain} in hypervisor {hyp_id} with exception: {e}"
                                                    )
                                        else:
                                            logs.broom.info(
                                                f"domain debugging: id_domain"
                                            )
                                            domains_debugging.append(id_domain)
                                    else:
                                        status_domain = [
                                            d["status"]
                                            for d in list_domains_without_hyp
                                            if d["id"] == id_domain
                                        ][0]
                                        update_domain_hyp_started(
                                            id_domain,
                                            hyp_id,
                                            "hyp_started updated by broom",
                                            status_domain,
                                        )

                            # remove domains destroyed by broom
                            [
                                d_domains_status_from_hyp.pop(k)
                                for k in domains_destroyed
                            ]
                            # remove domains debugging by broom
                            [
                                d_domains_status_from_hyp.pop(k)
                                for k in domains_debugging
                            ]

                            hyps_domain_started[hyp_id][
                                "active_domains"
                            ] = d_domains_status_from_hyp

                            # Update the current hypervisor memory and CPU usage in the DB
                            try:
                                mem_stats = h.conn.getMemoryStats(-1)
                                mem_stats["available"] = (
                                    mem_stats["free"] + mem_stats["cached"]
                                )
                                cpu_stats_timestamp = time()
                                cpu_stats = h.conn.getCPUStats(-1)

                                if cpu_stats_previous.get(hyp_id, False) == False:
                                    cpu_stats_previous[hyp_id] = cpu_stats
                                    cpu_stats_5min_previous[hyp_id] = []
                                    cpu_stats_5min_previous[hyp_id].append(
                                        (cpu_stats_timestamp, cpu_stats)
                                    )
                                    sleep(2)
                                    cpu_stats_timestamp = time()
                                    cpu_stats = h.conn.getCPUStats(-1)

                                (
                                    percent,
                                    diff_time,
                                    total_diff_time,
                                ) = calcule_cpu_hyp_stats(
                                    cpu_stats_previous[hyp_id],
                                    cpu_stats,
                                    round_digits=3,
                                )
                                cpu_current = percent

                                cpu_stats_previous[hyp_id] = cpu_stats
                                cpu_stats_5min_previous[hyp_id].append(
                                    (cpu_stats_timestamp, cpu_stats)
                                )

                                # remove old stats > 5 min
                                pop_items = 0
                                for a in cpu_stats_5min_previous[hyp_id]:
                                    if (cpu_stats_timestamp - a[0]) > (5 * 60 + 10):
                                        pop_items += 1
                                    else:
                                        break
                                for i in range(pop_items):
                                    if len(cpu_stats_5min_previous[hyp_id]) > 2:
                                        cpu_stats_5min_previous[hyp_id].pop(0)

                                (
                                    cpu_current_5min,
                                    diff_time,
                                    total_diff_time,
                                ) = calcule_cpu_hyp_stats(
                                    cpu_stats_5min_previous[hyp_id][0][1],
                                    cpu_stats,
                                    round_digits=3,
                                )

                            except Exception as e:
                                logs.broom.error(
                                    "hyp {} with id fail in get stats from libvirt".format(
                                        hyp_id
                                    )
                                )
                                h.disconnect()
                                continue

                        else:
                            logs.broom.error("HYPERVISOR {} libvirt connection failed")
                            hyps_domain_started[hyp_id] = False
                            logs.broom.error(
                                "Traceback: {}".format(traceback.format_exc())
                            )
                            hyps_domain_started[hyp_id] = False
                            continue

                        h.disconnect()

                        after = time()
                        elapsed = round(after - previous, 3)

                        d_stats = {
                            "time_elapsed_broom_connection": elapsed,
                            "cpu_current": cpu_current,
                            "cpu_5min": cpu_current_5min,
                            "mem_stats": mem_stats,
                        }
                        update_table_field(
                            "hypervisors", hyp_id, "stats", d_stats, soft=True
                        )

                except Exception as e:
                    logs.exception_id.debug("0003")
                    logs.broom.error(
                        "Exception when try to hypervisor {}: {}".format(hyp_id, e)
                    )
                    logs.broom.error("Traceback: {}".format(traceback.format_exc()))

            ## DOMAINS ACTIVE EN HYPERVISOR THAT ARE STOPPED, FAILED, UNKNOWN IN DATABASE...
            for hyp_id, d in hyps_domain_started.items():
                for id_domain, d_status in d["active_domains"].items():
                    if (
                        id_domain not in ids_domains_started_in_db_with_hypervisor
                    ) and (id_domain not in ids_domains_started_in_db_with_hypervisor):
                        d_domain = get_domain(id_domain)
                        if d_domain is None:
                            logs.broom.error(
                                "CRITICAL, if domain is not in database, must be destroyed previously by broom"
                            )
                            continue
                        if d_status["status"] == "Started":
                            logs.broom.error(
                                f"broom find domain {id_domain} with status {d_status['status']} in hypervisor {hyp_id} and updated status and hyp_started in databse"
                            )
                            update_domain_hyp_started(
                                id_domain,
                                hyp_id,
                                "State and hyp_started updated by broom",
                                d_status["status"],
                            )
                        elif d_status["status"] == "Paused":
                            if d_status["detail"] == "paused on user request":
                                logs.broom.error(
                                    f"broom find domain {id_domain} with status {d_status['status']} with detail {d_status['detail']} in hypervisor {hyp_id} and updated status and hyp_started in databse"
                                )
                                update_domain_hyp_started(
                                    id_domain,
                                    hyp_id,
                                    "State and hyp_started updated by broom",
                                    d_status["status"],
                                )
                            else:
                                logs.broom.info(
                                    f"broom find domain {id_domain} with status {d_status['status']} in hypervisor {hyp_id} with detail {d_status['detail']} , domain starting-paused?"
                                )
                        else:
                            logs.broom.error(
                                f"CRITICAL: STATUS FROM LIBVIRT IS NOT STARTED OR PAUSED!! broom find domain {id_domain} with status {d_status['status']} in hypervisor {hyp_id}"
                            )
                            logs.broom.error(
                                f"CRITICAL: broom not update strange status {id_domain} with status {d_status['status']} in hypervisor {hyp_id}"
                            )

            for d in list_domains_without_hyp:
                domain_id = d["id"]
                status = d["status"]
                if status == "Stopping":
                    logs.broom.debug(
                        "DOMAIN: {} STATUS STOPPING WITHOUTH HYPERVISOR, UNKNOWN REASON".format(
                            domain_id
                        )
                    )
                    update_domain_status(
                        "Stopped",
                        domain_id,
                        detail="Stopped by broom thread because has not hypervisor",
                    )

            for d in list_domains:
                domain_id = d["id"]
                status = d["status"]
                hyp_started = d["hyp_started"]
                if type(hyp_started) is bool:
                    continue
                if len(hyp_started) == 0:
                    continue
                # TODO bug sometimes hyp_started not in hyps_domain_started keys... why?
                if hyp_started in hyps_domain_started.keys() and len(hyp_started) > 0:
                    if hyps_domain_started[hyp_started] is not False:
                        if status == "Started":
                            pass
                        elif status == "Starting":
                            logs.broom.debug(
                                "DOMAIN: {} STATUS STARTING TO RUN IN HYPERVISOR: {}".format(
                                    domain_id, hyp_started
                                )
                            )
                            # try:
                            #     if domain_id in hyps_domain_started[hyp_started]['active_domains']:
                            #         print(domain_id)
                            # except Exception as e:
                            #     logs.broom.error(e)
                            if (
                                domain_id
                                in hyps_domain_started[hyp_started]["active_domains"]
                            ):
                                logs.broom.debug(
                                    "DOMAIN: {} ACTIVE IN HYPERVISOR: {}".format(
                                        domain_id, hyp_started
                                    )
                                )
                                state_libvirt = (
                                    hyps_domain_started[hyp_started]["hyp"]
                                    .domains[domain_id]
                                    .state()
                                )
                                state_str, cause = state_and_cause_to_str(
                                    state_libvirt[0], state_libvirt[1]
                                )
                                status = dict_domain_libvirt_state_to_isard_state(
                                    state_str
                                )
                                logs.broom.debug(
                                    "DOMAIN: {} ACTIVE IN HYPERVISOR: {} WITH STATUS: {}".format(
                                        domain_id, hyp_started, status
                                    )
                                )
                                update_domain_hyp_started(domain_id, hyp_started)
                            else:
                                logs.broom.debug(
                                    "DOMAIN: {} NOT ACTIVE YET IN HYPERVISOR: {} ".format(
                                        domain_id, hyp_started
                                    )
                                )
                        elif status == "Stopping":
                            logs.broom.debug(
                                "DOMAIN: {} STATUS STOPPING IN HYPERVISOR: {}".format(
                                    domain_id, hyp_started
                                )
                            )
                            if (
                                domain_id
                                not in hyps_domain_started[hyp_started][
                                    "active_domains"
                                ]
                            ):
                                update_domain_status(
                                    "Stopped",
                                    domain_id,
                                    detail="Stopped by broom thread",
                                )
                        elif status == "Shutting-down":
                            logs.broom.debug(
                                "DOMAIN: {} STATUS Shutting-down IN HYPERVISOR: {}".format(
                                    domain_id, hyp_started
                                )
                            )
                            if int(time()) - int(d["accessed"]) > 5 * 60:
                                update_domain_status(
                                    "Stopping",
                                    domain_id,
                                    keep_hyp_id=True,
                                    detail="Stopping by broom thread",
                                )
                                logs.broom.info(
                                    f"domain {domain_id} updated to Stopping after 5 min in Shutting-down"
                                )
                        else:
                            logs.broom.info(
                                "DOMAIN with status {}: {} NOT ACTIVE YET IN HYPERVISOR: {} ?".format(
                                    status, domain_id, hyp_started
                                )
                            )
                else:
                    if len(hyps_domain_started) > 0:
                        logs.broom.error(
                            "hyp_started: {} NOT IN hyps_domain_started keys:".format(
                                hyp_started
                            )
                        )

    def run(self):
        self.tid = get_tid()
        logs.broom.info("starting thread: {} (TID {})".format(self.name, self.tid))
        self.polling()


def launch_thread_broom(manager):
    t = ThreadBroom(
        name="broom",
        polling_interval=POLLING_INTERVAL_TRANSITIONAL_STATES,
        manager=manager,
    )
    t.daemon = True
    t.start()
    return t
