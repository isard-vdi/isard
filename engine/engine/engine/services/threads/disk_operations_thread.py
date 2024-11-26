import queue
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from engine.services.db.hypervisors import update_hyp_thread_status
from engine.services.lib.functions import get_tid, try_ssh_command
from engine.services.log import log, logs
from engine.services.threads.threads import (
    TIMEOUT_QUEUES,
    launch_action_create_template_disk,
    launch_action_disk,
    launch_action_update_size_storage_from_domain,
    launch_delete_disk_action,
)

# Define the global maximum number of threads
GLOBAL_MAX_THREADS = 5
global_semaphore = threading.Semaphore(GLOBAL_MAX_THREADS)


class LimitedThreadPoolExecutor(ThreadPoolExecutor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def submit(self, fn, *args, **kwargs):
        def wrapper(*wargs, **wkwargs):
            with global_semaphore:
                return fn(*wargs, **wkwargs)

        return super().submit(wrapper, *args, **kwargs)


class DiskOperationsThread(threading.Thread):
    def __init__(
        self,
        name,
        hyp_id,
        hostname,
        queue_actions,
        user="root",
        port=22,
        queue_master=None,
    ):
        threading.Thread.__init__(self)
        self.name = name
        self.hyp_id = hyp_id
        self.hostname = hostname
        self.user = user
        self.port = port
        self.stop = False
        self.queue_actions = queue_actions
        self.queue_master = queue_master
        # Warning: increasing workers from this values could cause rethinkdb to saturate
        # number of connections
        self.executors = {
            "create_disk": LimitedThreadPoolExecutor(max_workers=5),
            "create_disk_from_scratch": LimitedThreadPoolExecutor(max_workers=5),
            "delete_disk": LimitedThreadPoolExecutor(max_workers=5),
            "create_template_disk_from_domain": LimitedThreadPoolExecutor(
                max_workers=2
            ),
            "update_storage_size": LimitedThreadPoolExecutor(max_workers=5),
        }

    def run(self):
        self.tid = get_tid()
        log.info("starting thread: {} (TID {})".format(self.name, self.tid))
        self.disk_operations_thread()

    def disk_operations_thread(self):
        host = self.hostname
        self.tid = get_tid()
        log.debug(
            f"Thread to launch disk operations in host {host} with TID: {self.tid}..."
        )

        test_ssh, detail = try_ssh_command(self.hostname, self.user, self.port)
        if not test_ssh:
            log.error(
                f"test ssh in disk operations thread in hypervisor {self.hyp_id} fail. Thread stopped. Reason: {detail}"
            )
            self.stop = True
            self.error = detail

        if not self.stop:
            update_hyp_thread_status("disk_operations", self.hyp_id, "Started")
        while not self.stop:
            try:
                action = self.queue_actions.get(timeout=TIMEOUT_QUEUES)
                if action["type"] == "stop_thread":
                    self.stop = True
                else:
                    self.route_action(action)
                    time.sleep(0.1)  # Just to not saturate system in excess
            except queue.Empty:
                continue  # Timeout occurred, loop again
            except Exception as e:
                logs.exception_id.debug("0054")
                log.error(f"Exception when creating disk: {e}")
                log.error(f"Action: {action}")
                log.error(f"Traceback: {traceback.format_exc()}")
                return False

        if self.stop is True:
            update_hyp_thread_status("disk_operations", self.hyp_id, "Stopping")
            if self.queue_actions.empty() is not True:
                logs.main.error(
                    f"disk_operations_thread in hyper {self.hyp_id} is stopped with actions in queue"
                )
            action = {}
            action["type"] = "thread_disk_operations_dead"
            action["hyp_id"] = self.hyp_id
            self.queue_master.put(action)

    def route_action(self, action):
        # Determine the priority or type of action
        action_type = action["type"]
        if action_type not in self.executors.keys():
            log.error(f"Unknown action type: {action_type}")
            return
        self.executors[action_type].submit(self.handle_action, action)

    def handle_action(self, action):
        try:
            if action["type"] == "create_disk":
                launch_action_disk(action, self.hostname, self.user, self.port)
            elif action["type"] == "create_disk_from_scratch":
                launch_action_disk(
                    action, self.hostname, self.user, self.port, from_scratch=True
                )
            elif action["type"] == "delete_disk":
                launch_delete_disk_action(action, self.hostname, self.user, self.port)
            elif action["type"] == "create_template_disk_from_domain":
                log.info(
                    f"Processing create_template_disk_from_domain action for domain {action.get('id_domain')}..."
                )
                launch_action_create_template_disk(
                    action, self.hostname, self.user, self.port
                )
                log.info(
                    f"create_template_disk_from_domain action for domain {action.get('id_domain')} processed."
                )
            elif action["type"] == "update_storage_size":
                launch_action_update_size_storage_from_domain(
                    action, self.hostname, self.user, self.port
                )
        except Exception as e:
            log.error(f"Error processing action {action}: {e}")

    def stop_thread(self):
        self.stop = True
        self.executor.shutdown(wait=True)
