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
import time
import traceback

from changefeed_subscribers.engine import EngineSubscriber
from changefeed_subscribers.hypervisors import HypervisorsSubscriber
from isardvdi_common.redis_stream import RedisStreamConsumer
from rethinkdb import r

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
    get_hyp_thread_status,
    get_hypers_enabled_with_capabilities_status,
    remove_hyp_thread_status,
    update_hyp_status,
    update_hyp_thread_status,
)
from engine.services.lib.functions import PriorityQueueIsard, get_tid, try_socket
from engine.services.log import logs
from engine.services.threads.threads import launch_thread_worker

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
    # Timeout in seconds before considering a "Stopping" thread as stuck
    STUCK_THREAD_TIMEOUT = 60

    def __init__(
        self,
        name,
        t_workers,
        queues_object,
        t_events,
        manager=None,
        polling_interval=10,
    ):
        threading.Thread.__init__(self)
        self.polling_interval = polling_interval
        self.t_workers = t_workers
        self.t_events = t_events
        self.q_actions = PriorityQueueIsard()
        self.manager = manager
        self.name = name
        self.stop = False
        self.r_conn = False
        self.q = queues_object
        self.t_changes_hyps = False
        self.tid = False

        self.hypers_online = {}
        self.hypers_unknown = {}
        self.d_queues = {
            "workers": self.q.workers,
        }
        self.socket_tries = {}

        # Track when threads entered "Stopping" state for stuck detection
        self.stopping_timestamps = {}

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
                    self.set_hyp_thread_dead(hyp_id)

                if action["type"] == "new_hyper_in_db":
                    pass

                if action["type"] == "enable_hyper":
                    if action["status"] in ["Error", "Offline"]:
                        thread_status = get_hyp_thread_status(action["hyp_id"])
                        self.start_hyper_threads(
                            action["hyp_id"],
                            action["capabilities"],
                            action["status"],
                            thread_status,
                        )

                if action["type"] == "disable_hyper":
                    thread_status = get_hyp_thread_status(action["hyp_id"])
                    self.disable_hyper(
                        action["hyp_id"],
                        action["capabilities"],
                        action["status"],
                        thread_status,
                    )

                if action["type"] == "new_hyper_in_db":
                    pass

                if action["type"] == "hyp_degraded":
                    # Hypervisor is degraded (slow/overloaded) - migrate queued actions
                    hyp_id = action["hyp_id"]
                    reason = action.get("reason", "unknown")
                    logs.main.warning(
                        f"Hypervisor {hyp_id} marked as degraded: {reason}. "
                        f"Migrating queued actions to other hypervisors."
                    )
                    pool_obj = self.manager.pools.get("default")
                    pool_balancer = getattr(pool_obj, "balancer", None)
                    move_actions_to_others_hypers(
                        hyp_id,
                        self.d_queues,
                        remove_stopping=False,  # Keep stop actions in queue
                        remove_if_no_more_hyps=False,  # Keep if no alternatives
                        balancer=pool_balancer,
                        keep_gpu_actions=True,  # Keep GPU actions for when hyp recovers
                    )

                if action["type"] == "hyp_only_forced":
                    hyp_id = action["hyp_id"]
                    logs.main.info(
                        f"Hypervisor {hyp_id} set to only_forced/gpu_only. "
                        f"Moving non-GPU queued actions to other hypervisors."
                    )
                    pool_obj = self.manager.pools.get("default")
                    pool_balancer = getattr(pool_obj, "balancer", None)
                    move_actions_to_others_hypers(
                        hyp_id,
                        self.d_queues,
                        remove_stopping=False,
                        remove_if_no_more_hyps=False,
                        keep_gpu_actions=True,
                        balancer=pool_balancer,
                    )

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
                # Keep the orchestrator alive: a failure handling a single action must
                # not terminate the whole loop, otherwise the hypervisor stays Offline
                # forever and all desktop/deployment creation returns HTTP 428.
                continue

    def set_hyp_thread_dead(self, hyp_id):
        pool_obj = self.manager.pools.get("default")
        pool_balancer = getattr(pool_obj, "balancer", None)
        move_actions_to_others_hypers(
            hyp_id,
            self.d_queues,
            remove_stopping=True,
            remove_if_no_more_hyps=True,
            balancer=pool_balancer,
        )

        # POP FROM MANAGER DICTIONARIES
        # Defensive pop: a duplicate/late thread_hyp_worker_dead action (or a worker
        # already removed by _recover_stuck_stopping_threads) must be idempotent and
        # not raise KeyError, which would kill the whole orchestrator thread.
        q_old = self.q.workers.pop(hyp_id, None)
        t_old = self.t_workers.pop(hyp_id, None)
        del t_old
        del q_old
        update_hyp_thread_status("worker", hyp_id, "Stopped")

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

    def _recover_stuck_stopping_threads(self, hyp_id, thread_status):
        """Check for and recover threads stuck in 'Stopping' state.

        Threads that have been in 'Stopping' state for longer than
        STUCK_THREAD_TIMEOUT seconds are force-transitioned to 'Stopped'
        so they can be restarted.

        Args:
            hyp_id: The hypervisor ID
            thread_status: Dict with worker thread state

        Returns:
            Updated thread_status dict with stuck threads reset to 'Stopped'
        """
        current_time = time.time()

        thread_type = "worker"
        status = thread_status.get(thread_type, "Stopped")
        if status == "Stopping":
            # Track when we first saw this thread in Stopping state
            key = f"{hyp_id}_{thread_type}"
            if key not in self.stopping_timestamps:
                self.stopping_timestamps[key] = current_time
                logs.main.debug(
                    f"[{hyp_id}] Thread {thread_type} entered Stopping state"
                )
            else:
                elapsed = current_time - self.stopping_timestamps[key]
                if elapsed > self.STUCK_THREAD_TIMEOUT:
                    logs.main.warning(
                        f"[{hyp_id}] Thread {thread_type} stuck in 'Stopping' state "
                        f"for {elapsed:.0f}s (>{self.STUCK_THREAD_TIMEOUT}s). "
                        f"Forcing transition to 'Stopped'."
                    )
                    update_hyp_thread_status(thread_type, hyp_id, "Stopped")
                    thread_status[thread_type] = "Stopped"
                    del self.stopping_timestamps[key]

                    # Clean up thread resources if they exist
                    if hyp_id in self.t_workers:
                        try:
                            self.t_workers[hyp_id].stop = True
                            self.t_workers.pop(hyp_id, None)
                            self.q.workers.pop(hyp_id, None)
                        except Exception as e:
                            logs.main.error(
                                f"[{hyp_id}] Error cleaning up stuck worker thread: {e}"
                            )
        else:
            # Thread is not in Stopping state, clear any tracking
            key = f"{hyp_id}_{thread_type}"
            if key in self.stopping_timestamps:
                del self.stopping_timestamps[key]

        return thread_status

    def check_hyps_from_database(self):
        l_hyps = get_hypers_enabled_with_capabilities_status()
        for d_hyp in l_hyps:
            hyp_id = d_hyp["id"]
            capabilities = d_hyp["capabilities"]
            status = d_hyp["status"]
            thread_status = d_hyp.get("thread_status", {})

            # Check for and recover stuck threads first
            thread_status = self._recover_stuck_stopping_threads(hyp_id, thread_status)

            # if status in Error or Offline start threads
            if status in ["Error", "Offline"]:
                self.start_hyper_threads(hyp_id, capabilities, status, thread_status)
            else:
                if self.try_hyp_and_threads_alive(hyp_id) is False:
                    update_hyp_status(hyp_id, "Error", "Hypervisor not reachable")

            # try

    def try_hyp_and_threads_alive(self, hyp_id):
        # try dns resolution
        (
            hostname,
            port,
            user,
            nvidia_enabled,
            init_vgpu_profiles,
        ) = get_hyp_hostname_from_id(hyp_id)
        try:
            self.ip = socket.gethostbyname(hostname)
        except:
            logs.main.error(f"not resolving ip for hostname: {hyp_id}")

        timeout = float(CONFIG_DICT["TIMEOUTS"]["ssh_paramiko_hyp_test_connection"])
        logs.main.debug(f"try socket {hostname}, {port}, {timeout}")
        if try_socket(hostname, port, timeout) is False:
            tries = self.socket_tries.get(hyp_id, 0)
            if tries < 5:
                self.socket_tries[hyp_id] = tries + 1
                logs.main.error(
                    f"hypervisor {hyp_id} socket not reachable from hypervisor orchestrator thread. Try {self.socket_tries[hyp_id]}/5 "
                )
                return True
            else:
                logs.main.error(
                    f"hypervisor {hyp_id} socket not reachable from hypervisor orchestrator thread. Last try {tries}/5"
                )
                self.socket_tries.pop(hyp_id, None)
                return False
        self.socket_tries.pop(hyp_id, None)
        return True

    def start_hyper_threads(self, hyp_id, capabilities, status, thread_status):
        logs.main.debug(
            f"hypervisor finded in database as hyper enabled and ready to start: try to add hyper {hyp_id} from status {status}"
        )
        if (
            capabilities.get("hypervisor", False) is True
            and thread_status.get("worker", "Stopped") == "Stopped"
        ):
            self.activate_hyp(hyp_id)

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

    def run(self):
        self.tid = get_tid()
        logs.main.info("starting thread: {} (TID {})".format(self.name, self.tid))

        stop_event = threading.Event()
        self._stop_event = stop_event
        consumer = RedisStreamConsumer(
            streams=["stream:hypervisors", "stream:engine"],
            group="engine-hypervisors",
        )

        def handler(data):
            table = data.get("table")
            if table == "engine":
                envelope = EngineSubscriber.parse_dict(data)
                if envelope.change.new_val is not None:
                    status = (envelope.change.new_val.additional_properties or {}).get(
                        "status_all_threads"
                    )
                    if status == "Stopping":
                        self._stop_event.set()
                return

            if table == "hypervisors":
                envelope = HypervisorsSubscriber.parse_dict(data)
                self._process_change(envelope.change)

        consumer.run(handler, stop_event=stop_event)
        logs.main.info("finished thread hypervisor changes")

    def _process_change(self, change):
        try:
            new_val = change.new_val
            old_val = change.old_val

            # hypervisor deleted
            if new_val is None:
                logs.main.debug("hypervisor deleted in rethink")
                logs.main.debug(pprint.pformat(change))
                remove_hyp_thread_status(old_val.id)
                update_domains_in_deleted_hyper(old_val.id)

            # hypervisor created
            elif old_val is None:
                logs.main.debug("hypervisor created in rethink")
                logs.main.debug(pprint.pformat(change))
                if new_val.status == "Offline" and new_val.enabled is True:
                    action = {
                        "type": "enable_hyper",
                        "hyp_id": new_val.id,
                        "capabilities": new_val.capabilities,
                        "enabled": new_val.enabled,
                        "status": new_val.status,
                        "thread_status": (new_val.additional_properties or {}).get(
                            "thread_status", {}
                        ),
                        "hypervisors_pools": new_val.hypervisors_pools,
                    }
                    self.q_orchestrator.put(action)
            else:
                logs.main.debug("hypervisor fields modified in rethink")
                logs.main.debug(pprint.pformat(change))
                if old_val.enabled is False and new_val.enabled is True:
                    action = {
                        "type": "enable_hyper",
                        "hyp_id": new_val.id,
                        "capabilities": new_val.capabilities,
                        "enabled": new_val.enabled,
                        "status": new_val.status,
                        "thread_status": (new_val.additional_properties or {}).get(
                            "thread_status", {}
                        ),
                        "hypervisors_pools": new_val.hypervisors_pools,
                    }
                    self.q_orchestrator.put(action)
                if old_val.enabled is True and new_val.enabled is False:
                    action = {
                        "type": "disable_hyper",
                        "hyp_id": new_val.id,
                        "capabilities": new_val.capabilities,
                        "enabled": new_val.enabled,
                        "status": new_val.status,
                        "thread_status": (new_val.additional_properties or {}).get(
                            "thread_status", {}
                        ),
                        "hypervisors_pools": new_val.hypervisors_pools,
                    }
                    self.q_orchestrator.put(action)
                # Detect only_forced or gpu_only transition
                old_only_forced = old_val.only_forced
                new_only_forced = new_val.only_forced
                old_gpu_only = old_val.gpu_only
                new_gpu_only = new_val.gpu_only

                if (not old_only_forced and new_only_forced) or (
                    not old_gpu_only and new_gpu_only
                ):
                    action = {
                        "type": "hyp_only_forced",
                        "hyp_id": new_val.id,
                    }
                    self.q_orchestrator.put(action)

                if (
                    old_val.enabled is False
                    and new_val.status == "Deleting"
                    and old_val.status in ["Error", "Offline"]
                ):
                    hyp_id = new_val.id
                    cleanup_hypervisor_gpus(hyp_id)
                    delete_table_item("hypervisors", hyp_id)

        except Exception as e:
            logs.main.error(f"Error processing hypervisor change: {e}")
            logs.main.error(traceback.format_exc())
