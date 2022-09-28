import pprint
import queue
import threading
import traceback

from engine.services.db import update_domain_status, update_table_field
from engine.services.db.hypervisors import update_hyp_thread_status
from engine.services.lib.functions import (
    PriorityQueueIsard,
    execute_commands,
    get_tid,
    try_ssh_command,
)
from engine.services.log import log, logs
from engine.services.threads.threads import TIMEOUT_QUEUES


class LongOperationsThread(threading.Thread):
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
        self.long_operations_thread()

    def long_operations_thread(self):
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
                f"test ssh in long operations thread in hypervisor {self.hyp_id} fail. Thread stopped. Reason: {detail}"
            )
            self.stop = True
            self.error = detail

        if self.stop is False:
            update_hyp_thread_status("long_operations", self.hyp_id, "Started")
        while self.stop is not True:
            try:
                action = self.queue_actions.get(timeout=TIMEOUT_QUEUES)
                if action["type"] == "stop_thread":
                    self.stop = True
                # for ssh commands

                elif action["type"] in ["create_disk_virt_builder"]:
                    id_domain = action["domain"]
                    cmds_done = execute_commands(
                        host=self.hostname,
                        ssh_commands=action["ssh_commands"],
                        dict_mode=True,
                        user=self.user,
                        port=self.port,
                    )

                    if len([d for d in cmds_done if len(d["err"]) > 0]) > 1:
                        log.error("some error in virt builder operations")
                        log.error(
                            "Virt Builder Failed creating disk file {} in domain {} in hypervisor {}".format(
                                action["disk_path"], action["domain"], self.hyp_id
                            )
                        )
                        log.debug("print cmds_done:")
                        log.debug(pprint.pformat(cmds_done))
                        log.debug("print ssh_commands:")
                        log.debug(pprint.pformat(action["ssh_commands"]))
                        update_domain_status(
                            "Failed",
                            id_domain,
                            detail="Virt Builder Failed creating disk file",
                        )
                    else:
                        log.info(
                            "Disk created from virt-builder. Domain: {} , disk: {}".format(
                                action["domain"], action["disk_path"]
                            )
                        )
                        xml_virt_install = cmds_done[-1]["out"]
                        update_table_field(
                            "domains", id_domain, "xml_virt_install", xml_virt_install
                        )

                        update_domain_status(
                            "CreatingDomainFromBuilder",
                            id_domain,
                            detail="disk created from virt-builder",
                        )

                elif action["type"] in ["calculate_disk_usage"]:
                    id_domain = action["id_domain"]
                    path_disk = action["path_disk"]
                    hyp = action["hyp"]
                    # update_disk_usage(id_domain,path_disk,hyp)
                    pass
                else:
                    log.error("type action {} not supported".format(action["type"]))
            except queue.Empty:
                pass
            except Exception as e:
                logs.exception_id.debug("0067")
                log.error(
                    "Exception in main loop in long operations therad: {}".format(e)
                )
                log.error("Action: {}".format(pprint.pformat(action)))
                log.error("Traceback: {}".format(traceback.format_exc()))
                return False

        if self.stop is True:
            update_hyp_thread_status("long_operations", self.hyp_id, "Stopping")
            if self.queue_actions.empty() is not True:
                logs.main.error(
                    f"long_operations_thread in hyper {self.hyp_id} is stopped with actions in queue"
                )

            action = {}
            action["type"] = "thread_long_operations_dead"
            action["hyp_id"] = self.hyp_id
            self.queue_master.put(action)
