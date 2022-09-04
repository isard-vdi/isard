import pprint
import queue
import threading
import traceback

from engine.services.db import update_domain_status
from engine.services.db.hypervisors import update_hyp_thread_status
from engine.services.lib.functions import PriorityQueueIsard, get_tid, try_ssh_command
from engine.services.log import log, logs
from engine.services.threads.threads import (
    TIMEOUT_QUEUES,
    launch_action_create_template_disk,
    launch_action_disk,
    launch_action_update_size_storage_from_domain,
    launch_delete_disk_action,
)


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

    def run(self):
        self.tid = get_tid()
        log.info("starting thread: {} (TID {})".format(self.name, self.tid))
        self.disk_operations_thread()

    def disk_operations_thread(self):
        host = self.hostname
        self.tid = get_tid()
        log.debug(
            "Thread to launchdisks operations in host {} with TID: {}...".format(
                host, self.tid
            )
        )

        test_ssh, detail = try_ssh_command(self.hostname, self.user, self.port)
        if test_ssh is False:
            log.error(
                f"test ssh in disk operations thread in hypervisor {self.hyp_id} fail. Thread stopped. Reason: {detail}"
            )
            self.stop = True
            self.error = detail

        if self.stop is False:
            update_hyp_thread_status("disk_operations", self.hyp_id, "Started")
        while self.stop is not True:
            try:
                action = self.queue_actions.get(timeout=TIMEOUT_QUEUES)
                # for ssh commands
                if action["type"] in ["create_disk"]:
                    launch_action_disk(action, self.hostname, self.user, self.port)
                elif action["type"] in ["create_disk_from_scratch"]:
                    launch_action_disk(
                        action, self.hostname, self.user, self.port, from_scratch=True
                    )
                elif action["type"] in ["delete_disk"]:
                    launch_delete_disk_action(
                        action, self.hostname, self.user, self.port
                    )

                elif action["type"] in ["create_template_disk_from_domain"]:
                    launch_action_create_template_disk(
                        action, self.hostname, self.user, self.port
                    )

                elif action["type"] in ["update_storage_size"]:
                    launch_action_update_size_storage_from_domain(
                        action, self.hostname, self.user, self.port
                    )

                elif action["type"] == "stop_thread":
                    self.stop = True
                else:
                    log.error("type action {} not supported".format(action["type"]))
            except queue.Empty:
                pass
            except Exception as e:
                logs.exception_id.debug("0054")
                log.error("Exception when creating disk: {}".format(e))
                log.error("Action: {}".format(pprint.pformat(action)))
                log.error("Traceback: {}".format(traceback.format_exc()))
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
