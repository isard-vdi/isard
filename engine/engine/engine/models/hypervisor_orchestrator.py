# Copyright 2021 the Isard-vdi project authors
# License: AGPLv3
# coding=utf-8
# Alberto Larraz Dalmases


import os
import pprint
import queue
import shlex
import socket
import threading
import traceback

from engine.config import CONFIG_DICT
from engine.models.pool_hypervisors import move_actions_to_others_hypers
from engine.services.db import (
    cleanup_hypervisor_gpus,
    close_rethink_connection,
    delete_table_item,
    get_domains_flag_autostart_to_starting,
    new_rethink_connection,
    update_domain_status,
    update_domains_in_deleted_hyper,
    update_domains_started_in_hyp_to_unknown,
)
from engine.services.db.db import new_rethink_connection
from engine.services.db.hypervisors import (
    get_hyp_hostname_from_id,
    get_hyp_hostname_user_port_from_id,
    get_hypers_enabled_with_capabilities_status,
    update_hyp_status,
    update_hyp_thread_status,
)
from engine.services.lib.functions import PriorityQueueIsard, get_tid, try_socket
from engine.services.log import logs
from engine.services.threads.threads import (
    launch_disk_operations_thread,
    launch_thread_worker,
)
from rethinkdb import r

# virtio_test_disk_relative_path = 'admin/admin/admin/virtio_testdisk.qcow2'
# ui.creating_test_disk(test_disk_relative_route=virtio_test_disk_relative_path)
#
# TEST HYPS AND START THREADS FOR HYPERVISORS
#                self.test_hyps_and_start_threads()


def test_orchestrator(
    hyp_id,
    hostname=None,
    port="2022",
    cap_disk=True,
    cap_hyper=True,
    enabled=False,
    description="Default hypervisor",
    browser_port="443",
    spice_port="80",
    isard_static_url=os.environ["DOMAIN"],
    isard_video_url=os.environ["DOMAIN"],
    isard_proxy_hyper_url="isard-hypervisor",
):
    pass


def add_hyper_to_db(
    hyp_id,
    hostname=None,
    port="2022",
    cap_disk=True,
    cap_hyper=True,
    enabled=False,
    description="Default hypervisor",
    browser_port="443",
    spice_port="80",
    isard_static_url=os.environ["DOMAIN"],
    isard_video_url=os.environ["DOMAIN"],
    isard_proxy_hyper_url="isard-hypervisor",
):
    if hostname is None:
        hostname = hyp_id

    hypervisor = {
        "capabilities": {"disk_operations": cap_disk, "hypervisor": cap_hyper},
        "description": description,
        "detail": "",
        "enabled": enabled,
        "hostname": hostname,
        "hypervisors_pools": ["default"],
        "id": hyp_id,
        "port": port,
        "status": "Offline",
        "status_time": False,
        "uri": "",
        "user": "root",
        "viewer": {
            "static": isard_static_url,  # isard-static nginx
            "proxy_video": isard_video_url,  # Video Proxy Host
            "spice_ext_port": spice_port,  # 80
            "html5_ext_port": browser_port,  # 443
            "proxy_hyper_host": isard_proxy_hyper_url,  # Viewed from isard-video
        },
    }

    r_conn = new_rethink_connection()
    if cap_disk:
        for hp in hypervisor["hypervisors_pools"]:
            paths = r.table("hypervisors_pools").get(hp).run(r_conn)["paths"]
            for p in paths:
                p = shlex.quote(p)
                for i, path_data in enumerate(paths[p]):
                    if hyp_id not in path_data["disk_operations"]:
                        path_data["disk_operations"].append(hyp_id)
                        paths[p][i]["disk_operations"] = path_data["disk_operations"]
            result = (
                r.table("hypervisors_pools")
                .get(hp)
                .update({"paths": paths, "enabled": False})
                .run(r_conn)
            )
    result = r.table("hypervisors").insert(hypervisor, conflict="update").run(r_conn)
    close_rethink_connection(r_conn)

    return result


class HypervisorsOrchestratorThread(threading.Thread):
    def __init__(
        self,
        name,
        t_workers,
        queues_object,
        t_events,
        t_disk_operations,
        q_disk_operations,
        polling_interval=10,
    ):
        threading.Thread.__init__(self)
        self.polling_interval = polling_interval
        self.t_workers = t_workers
        self.t_events = t_events
        self.q_actions = PriorityQueueIsard()
        self.t_disk_operations = t_disk_operations
        self.q_disk_operations = q_disk_operations
        self.name = name
        self.stop = False
        self.r_conn = False
        self.q = queues_object
        self.t_changes_hyps = False
        self.tid = False

        self.hypers_online = {}
        self.hypers_unknown = {}
        self.d_queues = {
            "disk_operations": self.q_disk_operations,
            "workers": self.q.workers,
        }

    def run(self):
        self.tid = get_tid()

        self.t_changes_hyps = HypervisorChangesThread("changes_hyp", self.q_actions)
        self.t_changes_hyps.daemon = True
        self.t_changes_hyps.start()

        logs.main.info("starting thread: {} (TID {})".format(self.name, self.tid))
        self.check_hyps_from_database()
        while self.stop is False:
            # ACTIONS TO DO IN MAIN THREAD WITH QUEUE

            try:
                action = self.q_actions.get(timeout=self.polling_interval)
                logs.main.info("Orchestrator Action: {}".format(action["type"]))
                if action["type"] == "thread_hyp_worker_dead":
                    hyp_id = action["hyp_id"]
                    # TRANSFER ACTIONS TO OTHER QUEUE IF AVAILABLE ELSE DELETE
                    move_actions_to_others_hypers(
                        hyp_id,
                        self.d_queues,
                        remove_stopping=True,
                        remove_if_no_more_hyps=True,
                    )

                    # POP FROM MANAGER DICTIONARIES
                    q_old = self.q.workers.pop(hyp_id)
                    t_old = self.t_workers.pop(hyp_id)
                    del t_old
                    del q_old
                    update_hyp_thread_status("worker", hyp_id, "Stopped")
                    # if hyp_id in self.t_disk_operations.keys():
                    #     self.t_disk_operations[hyp_id].stop = True
                    #     self.q_disk_operations[hyp_id].put({'type':'stop_thread'})
                    # if hyp_id in self.t_long_operations.keys():
                    #     self.t_long_operations[hyp_id].stop = True
                    #     self.q_long_operations[hyp_id].put({'type':'stop_thread'})

                if action["type"] == "thread_disk_operations_dead":
                    hyp_id = action["hyp_id"]
                    if self.q_disk_operations[hyp_id].empty() is False:
                        d = {"disk_operations": self.q_disk_operations}
                        move_actions_to_others_hypers(
                            hyp_id, d, remove_stopping=True, remove_if_no_more_hyps=True
                        )
                    q_old = self.q_disk_operations.pop(hyp_id)
                    t_old = self.t_disk_operations.pop(hyp_id)
                    del t_old
                    del q_old
                    update_hyp_thread_status("disk_operations", hyp_id, "Stopped")

                if action["type"] == "new_hyper_in_db":
                    pass

                if action["type"] == "enable_hyper":
                    if action["status"] in ["Error", "Offline"]:
                        self.start_hyper_threads(
                            action["hyp_id"],
                            action["capabilities"],
                            action["status"],
                            action["thread_status"],
                        )

                if action["type"] == "disable_hyper":
                    self.disable_hyper(
                        action["hyp_id"],
                        action["capabilities"],
                        action["status"],
                        action["thread_status"],
                    )

                if action["type"] == "new_hyper_in_db":
                    pass

            except queue.Empty:
                self.check_hyps_from_database()
                for autostart_id in get_domains_flag_autostart_to_starting():
                    logs.main.info(
                        f"Desktop with flag autostart with id {autostart_id} go to Starting status"
                    )
                    update_domain_status("Starting", autostart_id)
                pass

            except Exception as e:
                logs.exception_id.debug("0036")
                logs.main.error("ERROR MAIN LOOP IN HYPERVISOR ORCHESTRATOR")
                logs.main.error(f"Exception: {e}")
                logs.main.error("-- More info about exception -----")
                logs.main.error("Action: {}".format(pprint.pformat(action)))
                logs.main.error("Traceback: {}".format(traceback.format_exc()))
                logs.main.error("----------------------------------")
                return False

    def disable_hyper(self, hyp_id, capabilities, status, thread_status):
        # status = get_hyp_status(hyp_id)
        if status == "Online":
            update_hyp_status(hyp_id, "Offline")

        update_domains_started_in_hyp_to_unknown(hyp_id)

        if hyp_id in self.t_workers.keys():
            if thread_status["worker"] == "Started":
                update_hyp_thread_status("worker", hyp_id, "Stopping")
                self.t_workers[hyp_id].stop = True
                action = {"type": "stop_thread"}
                self.q.workers[hyp_id].put(action)

        if hyp_id in self.t_disk_operations.keys():
            if thread_status["disk_operations"] == "Started":
                update_hyp_thread_status("disk_operations", hyp_id, "Stopping")
                self.t_disk_operations[hyp_id].stop = True
                action = {"type": "stop_thread"}
                self.q_disk_operations[hyp_id].put(action)

    def check_hyps_from_database(self):
        l_hyps = get_hypers_enabled_with_capabilities_status()
        for d_hyp in l_hyps:
            hyp_id = d_hyp["id"]
            capabilities = d_hyp["capabilities"]
            status = d_hyp["status"]
            thread_status = d_hyp.get("thread_status", {})
            # if status in Error or Offline start threads
            if status in ["Error", "Offline"]:
                self.start_hyper_threads(hyp_id, capabilities, status, thread_status)
            else:
                self.try_hyp_and_threads_alive(hyp_id)
            # try

    def try_hyp_and_threads_alive(self, hyp_id):
        # try dns resolution
        (
            hostname,
            port,
            user,
            nvidia_enabled,
            force_get_hyp_info,
            init_vgpu_profiles,
        ) = get_hyp_hostname_from_id(hyp_id)
        try:
            self.ip = socket.gethostbyname(hostname)
        except:
            logs.main.error(f"not resolving ip for hostname: {hyp_id}")

        timeout = float(CONFIG_DICT["TIMEOUTS"]["ssh_paramiko_hyp_test_connection"])
        logs.main.debug(f"try socket {hostname}, {port}, {timeout}")
        socket_ok = try_socket(hostname, port, timeout)

    def start_hyper_threads(self, hyp_id, capabilities, status, thread_status):
        logs.main.debug(
            f"hypervisor finded in database as hyper enabled and ready to start: try to add hyper {hyp_id} from status {status}"
        )
        if (
            capabilities.get("hypervisor", False) is True
            and thread_status.get("worker", "Stopped") == "Stopped"
        ):
            self.activate_hyp(hyp_id)
        if (
            capabilities.get("disk_operations", False) is True
            and thread_status.get("disk_operations", "Stopped") == "Stopped"
        ):
            self.activate_disk_operations(hyp_id)

    def activate_disk_operations(self, hyp_id, timeout=10):
        d = get_hyp_hostname_user_port_from_id(hyp_id)

        launch_disk_operations = True
        if hyp_id in self.t_disk_operations.keys():
            if self.t_disk_operations[hyp_id].is_alive():
                launch_disk_operations = False
            else:
                self.t_disk_operations.pop(hyp_id)
                self.q_disk_operations.pop(hyp_id)
        if launch_disk_operations is True:
            (
                self.t_disk_operations[hyp_id],
                self.q_disk_operations[hyp_id],
            ) = launch_disk_operations_thread(
                hyp_id, d["hostname"], d["user"], d["port"], self.q_actions
            )

        return True

    def activate_hyp(self, hyp_id, timeout=10):
        t_worker, q_worker = launch_thread_worker(
            hyp_id, self.t_events.q_event_register, self.q_actions
        )

        self.t_workers[hyp_id] = t_worker
        self.q.workers[hyp_id] = q_worker


class HypervisorChangesThread(threading.Thread):
    def __init__(self, name, q_orchestrator):
        threading.Thread.__init__(self)
        self.name = name
        self.q_orchestrator = q_orchestrator
        self.stop = False
        self.r_conn = False

    def run(self):
        self.tid = get_tid()
        logs.main.info("starting thread: {} (TID {})".format(self.name, self.tid))
        self.r_conn = new_rethink_connection()
        # rtable=r.table('disk_operations')
        # for c in r.table('hypervisors').changes(include_initial=True, include_states=True).run(r_conn):
        for c in (
            r.table("hypervisors")
            .pluck(
                "id",
                "capabilities",
                "enabled",
                "status",
                "thread_status",
                "hypervisors_pools",
            )
            .merge({"table": "hypervisors"})
            .changes()
            .union(
                r.table("engine")
                .pluck("status_all_threads")
                .merge({"table": "engine"})
                .changes()
            )
            .run(self.r_conn)
        ):
            # stop thread
            if self.stop is True:
                break

            if c["new_val"] != None:
                if c["new_val"]["table"] == "engine":
                    if c["new_val"]["status_all_threads"] == "Stopping":
                        break

            # hypervisor deleted
            if c["new_val"] is None:
                if c["old_val"].get("table", False) == "hypervisors":
                    logs.main.debug("hypervisor deleted in rethink")
                    logs.main.debug(pprint.pformat(c))
                    update_domains_in_deleted_hyper(c["old_val"]["id"])

            # hypervisor created
            elif c["old_val"] is None:
                if c["new_val"].get("table", False) == "hypervisors":
                    logs.main.debug("hypervisor created in rethink")
                    logs.main.debug(pprint.pformat(c))
                    if (
                        c["new_val"]["status"] == "Offline"
                        and c["new_val"]["enabled"] == True
                    ):
                        action = {}
                        action["type"] = "enable_hyper"
                        action["hyp_id"] = c["new_val"].get("id")
                        action["capabilities"] = c["new_val"].get("capabilities")
                        action["enabled"] = c["new_val"].get("enabled")
                        action["status"] = c["new_val"].get("status")
                        action["thread_status"] = c["new_val"].get("thread_status", {})
                        action["hypervisors_pools"] = c["new_val"].get(
                            "hypervisors_pools"
                        )
                        self.q_orchestrator.put(action)
            else:
                if c["new_val"].get("table", False) == "hypervisors":
                    logs.main.debug("hypervisor fields modified in rethink")
                    logs.main.debug(pprint.pformat(c))
                    if (
                        c["old_val"]["enabled"] == False
                        and c["new_val"]["enabled"] == True
                    ):
                        action = {}
                        action["type"] = "enable_hyper"
                        action["hyp_id"] = c["new_val"].get("id")
                        action["capabilities"] = c["new_val"].get("capabilities")
                        action["enabled"] = c["new_val"].get("enabled")
                        action["status"] = c["new_val"].get("status")
                        action["thread_status"] = c["new_val"].get("thread_status", {})
                        action["hypervisors_pools"] = c["new_val"].get(
                            "hypervisors_pools"
                        )
                        self.q_orchestrator.put(action)
                    if (
                        c["old_val"]["enabled"] == True
                        and c["new_val"]["enabled"] == False
                    ):
                        action = {}
                        action["type"] = "disable_hyper"
                        action["hyp_id"] = c["new_val"].get("id")
                        action["capabilities"] = c["new_val"].get("capabilities")
                        action["enabled"] = c["new_val"].get("enabled")
                        action["status"] = c["new_val"].get("status")
                        action["thread_status"] = c["new_val"].get("thread_status", {})
                        action["hypervisors_pools"] = c["new_val"].get(
                            "hypervisors_pools"
                        )
                        self.q_orchestrator.put(action)
                    if (
                        c["old_val"]["enabled"] == False
                        and c["new_val"]["status"] == "Deleting"
                        and c["old_val"]["status"] in ["Error", "Offline"]
                    ):
                        hyp_id = c["new_val"].get("id")

                        # Remove all the GPUs of the said hypervisor
                        cleanup_hypervisor_gpus(hyp_id)
                        delete_table_item("hypervisors", hyp_id)

        self.r_conn.close()
