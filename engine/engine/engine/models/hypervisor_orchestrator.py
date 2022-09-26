# Copyright 2021 the Isard-vdi project authors
# License: AGPLv3
# coding=utf-8
# Alberto Larraz Dalmases


import os
import pprint
import queue
import socket
import threading
import time
import traceback
from datetime import datetime
from time import sleep

from engine.config import CONFIG_DICT
from engine.controllers.events_recolector import launch_thread_hyps_event
from engine.controllers.status import launch_thread_status
from engine.models.pool_hypervisors import (
    PoolHypervisors,
    move_actions_to_others_hypers,
)
from engine.services.db import (
    close_rethink_connection,
    delete_table_item,
    get_domain,
    get_domain_hyp_started,
    get_domains_flag_server_to_starting,
    get_if_all_disk_template_created,
    new_rethink_connection,
    remove_domain,
    set_unknown_domains_not_in_hyps,
    update_domain_history_from_id_domain,
    update_domain_status,
    update_domains_started_in_hyp_to_unknown,
)
from engine.services.db.db import (
    get_pools_from_hyp,
    new_rethink_connection,
    update_table_field,
)
from engine.services.db.hypervisors import (
    get_hyp_hostname_from_id,
    get_hyp_hostname_user_port_from_id,
    get_hypers_disk_operations,
    get_hypers_enabled_with_capabilities_status,
    get_hypers_ids_with_status,
    get_hyps_ready_to_start,
    get_hyps_with_status,
    update_all_hyps_status,
    update_hyp_status,
    update_hyp_thread_status,
)
from engine.services.lib.functions import (
    PriorityQueueIsard,
    engine_restart,
    exec_remote_list_of_cmds_dict,
    get_threads_running,
    get_tid,
    try_socket,
)
from engine.services.lib.qcow import test_hypers_disk_operations
from engine.services.log import logs
from engine.services.threads.threads import (
    launch_disk_operations_thread,
    launch_long_operations_thread,
    launch_thread_worker,
    set_domains_coherence,
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
        t_long_operations,
        q_long_operations,
        t_disk_operations,
        q_disk_operations,
        polling_interval=10,
    ):
        threading.Thread.__init__(self)
        self.polling_interval = polling_interval
        self.t_workers = t_workers
        self.t_events = t_events
        self.q_actions = PriorityQueueIsard()
        self.t_long_operations = t_long_operations
        self.q_long_operations = q_long_operations
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
            "long_operations": self.q_long_operations,
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

                if action["type"] == "thread_long_operations_dead":
                    hyp_id = action["hyp_id"]
                    if self.q_long_operations[hyp_id].empty() is False:
                        d = {"long_operations": self.q_long_operations}
                        move_actions_to_others_hypers(
                            hyp_id, d, remove_stopping=True, remove_if_no_more_hyps=True
                        )
                    q_old = self.q_long_operations.pop(hyp_id)
                    t_old = self.t_long_operations.pop(hyp_id)
                    del t_old
                    del q_old
                    update_hyp_thread_status("long_operations", hyp_id, "Stopped")

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
                for server_id in get_domains_flag_server_to_starting():
                    logs.main.info(
                        f"Desktop with flag server with id {server_id} go to Starting status"
                    )
                    update_domain_status("Starting", server_id)
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

        if hyp_id in self.t_long_operations.keys():
            if thread_status["long_operations"] == "Started":
                update_hyp_thread_status("long_operations", hyp_id, "Stopping")
                self.t_long_operations[hyp_id].stop = True
                action = {"type": "stop_thread"}
                self.q_long_operations[hyp_id].put(action)

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
            and thread_status.get("long_operations", "Stopped") == "Stopped"
        ):
            self.activate_disk_long_operations(hyp_id)

    def activate_disk_long_operations(self, hyp_id, timeout=10):
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

        launch_long_operations = True
        if hyp_id in self.t_long_operations.keys():
            if self.t_long_operations[hyp_id].is_alive():
                launch_long_operations = False
            else:
                self.t_long_operations.pop(hyp_id)
                self.q_long_operations.pop(hyp_id)
        if launch_long_operations is True:
            (
                self.t_long_operations[hyp_id],
                self.q_long_operations[hyp_id],
            ) = launch_long_operations_thread(
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
                    # TODO: verify no domains in hypervisor running (front end and backend) and fence or unknown if
                    # domains are running and hypevisor communication have lost
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
                        delete_table_item("hypervisors", hyp_id)

        self.r_conn.close()


def launch_threads_disk_and_long_operations(self):

    self.manager.hypers_disk_operations = get_hypers_disk_operations()

    self.manager.hypers_disk_operations_tested = test_hypers_disk_operations(
        self.manager.hypers_disk_operations
    )

    for hyp_disk_operations in self.manager.hypers_disk_operations_tested:
        hyp_long_operations = hyp_disk_operations
        d = get_hyp_hostname_user_port_from_id(hyp_disk_operations)

        if hyp_disk_operations not in self.manager.t_disk_operations.keys():
            (
                self.manager.t_disk_operations[hyp_disk_operations],
                self.manager.q_disk_operations[hyp_disk_operations],
            ) = launch_disk_operations_thread(
                hyp_id=hyp_disk_operations,
                hostname=d["hostname"],
                user=d["user"],
                port=d["port"],
            )
            (
                self.manager.t_long_operations[hyp_long_operations],
                self.manager.q_long_operations[hyp_long_operations],
            ) = launch_long_operations_thread(
                hyp_id=hyp_long_operations,
                hostname=d["hostname"],
                user=d["user"],
                port=d["port"],
            )


# def test_hyps_and_start_threads(self):
#     """If status of hypervisor is Error or Offline and are enabled,
#     this function try to connect and launch threads.
#     If hypervisor pass connection test, status change to ReadyToStart,
#     then change to StartingThreads previous to launch threads, when
#     threads are running state is Online. Status sequence is:
#     (Offline,Error) => ReadyToStart => StartingThreads => (Online,Error)"""
#
#     # DISK_OPERATIONS: launch threads if test disk operations passed and is not launched
#     self.launch_threads_disk_and_long_operations()
#
#     l_hyps_to_test = get_hyps_with_status(list_status=['Error', 'Offline'], empty=True)
#
#     dict_hyps_to_test = {d['id']: {'hostname': d['hostname'],
#                                    'port': d['port'] if 'port' in d.keys() else 22,
#                                    'user': d['user'] if 'user' in d.keys() else 'root'} for d in
#                          l_hyps_to_test}
#
#     # TRY hypervisor connexion and UPDATE hypervisors status
#     # update status: ReadyToStart if all ok
#     launch_try_hyps(dict_hyps_to_test)
#
#     # hyp_hostnames of hyps ready to start
#     dict_hyps_ready = self.manager.dict_hyps_ready = get_hyps_ready_to_start()
#
#     if len(dict_hyps_ready) >  0:
#         logs.main.debug('hyps_ready_to_start: ' + pprint.pformat(dict_hyps_ready))
#
#         # launch thread events if is None
#         if self.manager.t_events is None:
#             logs.main.info('launching hypervisor events thread')
#             self.manager.t_events = launch_thread_hyps_event()
#         # else:
#         #     #if new hypervisor has added then add hypervisor to receive events
#         #     logs.main.info('hypervisors added to thread events')
#         #     logs.main.info(pprint.pformat(dict_hyps_ready))
#         #     self.manager.t_events.hyps.update(dict_hyps_ready)
#         #     for hyp_id, hostname in self.manager.t_events.hyps.items():
#         #         self.manager.t_events.add_hyp_to_receive_events(hyp_id)
#
#         set_unknown_domains_not_in_hyps(dict_hyps_ready.keys())
#         set_domains_coherence(dict_hyps_ready)
#
#         pools = set()
#         for hyp_id, hostname in dict_hyps_ready.items():
#             update_hyp_status(hyp_id, 'StartingThreads')
#
#             # launch worker thread
#             self.manager.t_workers[hyp_id], self.manager.q.workers[hyp_id] = launch_thread_worker(hyp_id)
#
#             # LAUNCH status thread
#             if self.manager.with_status_threads is True:
#                 self.manager.t_status[hyp_id] = launch_thread_status(hyp_id,
#                                                                      self.manager.STATUS_POLLING_INTERVAL)
#
#             # ADD hyp to receive_events
#             self.manager.t_events.q_event_register.put({'type': 'add_hyp_to_receive_events', 'hyp_id': hyp_id})
#
#             # self.manager.launch_threads(hyp_id)
#             # INFO TO DEVELOPER FALTA VERIFICAR QUE REALMENTE ESTÁN ARRANCADOS LOS THREADS??
#             # comprobar alguna variable a true en alguno de los threads
#             update_hyp_status(hyp_id, 'Online')
#             pools.update(get_pools_from_hyp(hyp_id))
#
#         # if hypervisor not in pools defined in manager add it
#         for id_pool in pools:
#             if id_pool not in self.manager.pools.keys():
#                 if self.manager.with_status_threads is True:
#                     self.manager.pools[id_pool] = PoolHypervisors(id_pool, self.manager, len(dict_hyps_ready))
#                 else:
#                     self.manager.pools[id_pool] = PoolHypervisors(id_pool, self.manager, len(dict_hyps_ready)
#                                                                   ,with_status_threads=False)
