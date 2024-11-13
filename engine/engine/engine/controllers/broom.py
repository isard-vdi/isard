# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3


import os
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
    update_table_dict,
    update_table_field,
    update_vgpu_info_if_stopped,
)
from engine.services.lib.functions import (
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
        disk_interval = 0
        while self.stop is not True:
            try:
                interval = 0.0
                while interval < self.polling_interval:
                    sleep(0.1)
                    interval += 0.1
                    if self.stop is True:
                        break
                if disk_interval >= 300:
                    disk_interval = 0
                disk_interval += 1
                if self.manager.check_actions_domains_enabled() is False:
                    continue

                """
                DB DOMAINS TRANSITIONAL STATES
                """
                l = get_domains_with_transitional_status(also_started=True)

                DB_DOMAINS_WITHOUT_HYP = [d for d in l if "hyp_started" not in d.keys()]
                DB_DOMAINS_STARTED_WITH_HYP = [
                    d for d in l if "hyp_started" in d.keys()
                ]
                DB_DOMAINS_ID_STARTED_WITH_HYP = [
                    a["id"] for a in DB_DOMAINS_STARTED_WITH_HYP
                ]
                # ids_domains_started_in_db_without_hypervisor = [
                #     a["id"] for a in DB_DOMAINS_WITHOUT_HYP
                # ]

                for db_domain in DB_DOMAINS_WITHOUT_HYP:
                    logs.broom.error(
                        "DOMAIN {} WITH STATUS {} without HYPERVISOR".format(
                            db_domain["id"], db_domain["status"]
                        )
                    )
                    update_domain_status(
                        "Unknown",
                        db_domain["id"],
                        detail="starting or stoping status without hypervisor",
                    )

                HYPERS_ONLINE = list(get_hyp_hostnames_online().keys())

                hyps_domain_started = {}
                for hyp_id in HYPERS_ONLINE:
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
                                "hyp {} with id has not hostname or is not in database".format(
                                    hyp_id
                                )
                            )
                        else:
                            h = hyp(hyp_id, hostname, user=user, port=port)
                            if h.connected:
                                # Update the current hypervisor storage usage in the DB
                                if disk_interval == 1:
                                    update_table_dict(
                                        "hypervisors",
                                        hyp_id,
                                        {"mountpoints": h.get_storage_used()},
                                        soft=True,
                                    )

                                hyps_domain_started[hyp_id] = {}
                                hyps_domain_started[hyp_id]["hyp"] = h
                                d_domains_status_from_hyp = h.get_domains()
                                if d_domains_status_from_hyp is None:
                                    d_domains_status_from_hyp = {}

                                # check if domain running in hypervisor is not defined in database
                                domains_destroyed = []
                                domains_debugging = []
                                for (
                                    domain_id,
                                    status_and_detail,
                                ) in d_domains_status_from_hyp.items():
                                    if domain_id not in DB_DOMAINS_ID_STARTED_WITH_HYP:
                                        db_domain = get_domain(domain_id)
                                        if db_domain is None:
                                            try:
                                                domain_handler = h.conn.lookupByName(
                                                    domain_id
                                                )
                                                domain_handler.destroy()
                                                domains_destroyed.append(domain_id)
                                                logs.broom.error(
                                                    f"broom destroyed domain not in database {domain_id} in hypervisor {hyp_id}"
                                                )
                                            except Exception as e:
                                                logs.broom.error(
                                                    f"EXCEPTION when try to destroy domain not in database {domain_id} in hypervisor {hyp_id} with exception: {e}"
                                                )
                                        if db_domain.get("status") not in [
                                            "Started",
                                            "Shutting-down",
                                            "Stopping",
                                        ]:
                                            logs.broom.warning(
                                                f"broom find domain {domain_id} with status {db_domain.get('status')} started in hypervisor {hyp_id} and updated status and hyp_started in database"
                                            )
                                            update_domain_hyp_started(
                                                domain_id,
                                                hyp_id,
                                                "hyp_started updated by broom",
                                                "Started",
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

                            else:
                                hyps_domain_started[hyp_id] = {}
                                logs.broom.error(
                                    "HYPERVISOR {} libvirt connection failed"
                                )
                                logs.broom.error(
                                    "Traceback: {}".format(traceback.format_exc())
                                )
                                continue

                            h.disconnect()

                    except Exception as e:
                        logs.exception_id.debug("0003")
                        logs.broom.error(
                            "Exception when try to hypervisor {}: {}".format(hyp_id, e)
                        )
                        logs.broom.error("Traceback: {}".format(traceback.format_exc()))

                ## DOMAINS ACTIVE EN HYPERVISOR THAT ARE STOPPED, FAILED, UNKNOWN IN DATABASE...
                for hyp_id, d in hyps_domain_started.items():
                    if d.get("active_domains"):
                        for domain_id, d_status in d["active_domains"].items():
                            domain_status = d_status["status"]
                            domain_status_detail = d_status["detail"]
                            if domain_id not in DB_DOMAINS_ID_STARTED_WITH_HYP:
                                db_domain = get_domain(domain_id)
                                if db_domain is None:
                                    logs.broom.error(
                                        "CRITICAL, if domain is not in database, must have been destroyed previously by broom, will do it next loop"
                                    )
                                    continue
                                if domain_status == "Started":
                                    logs.broom.error(
                                        f"broom find domain {domain_id} with status {domain_status} in hypervisor {hyp_id} and updated status and hyp_started in databse"
                                    )
                                    if db_domain["status"] not in ["ForceDeleting"]:
                                        update_domain_hyp_started(
                                            domain_id,
                                            hyp_id,
                                            "State and hyp_started updated by broom",
                                            domain_status,
                                        )
                                elif domain_status == "Paused":
                                    if domain_status_detail == "paused on user request":
                                        logs.broom.error(
                                            f"broom find domain {domain_id} with status {domain_status} with detail {domain_status_detail} in hypervisor {hyp_id} and updated status and hyp_started in databse"
                                        )
                                        if db_domain["status"] not in [
                                            "Stopped",
                                            "ForceDeleting",
                                        ]:
                                            update_domain_hyp_started(
                                                domain_id,
                                                hyp_id,
                                                "State and hyp_started updated by broom",
                                                domain_status,
                                            )
                                    else:
                                        logs.broom.info(
                                            f"broom find domain {domain_id} with status {domain_status} in hypervisor {hyp_id} with detail {domain_status_detail} , domain starting-paused?"
                                        )
                                else:
                                    logs.broom.error(
                                        f"CRITICAL: STATUS FROM LIBVIRT IS NOT STARTED OR PAUSED!! broom find domain {domain_id} with status {domain_status} in hypervisor {hyp_id}"
                                    )
                                    logs.broom.error(
                                        f"CRITICAL: broom not update strange status {domain_id} with status {domain_status} in hypervisor {hyp_id}"
                                    )

                for d in DB_DOMAINS_WITHOUT_HYP:
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

                for d in DB_DOMAINS_STARTED_WITH_HYP:
                    domain_id = d["id"]
                    status = d["status"]
                    hyp_started = d["hyp_started"]
                    if type(hyp_started) is bool:
                        continue
                    if len(hyp_started) == 0:
                        continue
                    # TODO bug sometimes hyp_started not in hyps_domain_started keys... why?
                    if (
                        hyp_started in hyps_domain_started.keys()
                        and len(hyp_started) > 0
                    ):
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
                                    in hyps_domain_started[hyp_started][
                                        "active_domains"
                                    ]
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
                                    status = dict_domain_libvirt_state_to_isard_state[
                                        state_str
                                    ]
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
                                    update_vgpu_info_if_stopped(domain_id)
                            elif status == "Resetting":
                                if int(time()) - int(d["accessed"]) > 60:
                                    logs.broom.debug(
                                        "DOMAIN: {} STATUS RESETTING IN HYPERVISOR: {}".format(
                                            domain_id, hyp_started
                                        )
                                    )
                                    update_domain_status(
                                        "Failed",
                                        domain_id,
                                        detail="Failed from Resetting state by broom thread",
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
                                "domain {} has an hyp_started: {} NOT IN hyps_domain_started keys:".format(
                                    domain_id, hyp_started
                                )
                            )
            except Exception as e:
                logs.broom.error(
                    "Exception in broom thread. Traceback: {}".format(
                        traceback.format_exc()
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
