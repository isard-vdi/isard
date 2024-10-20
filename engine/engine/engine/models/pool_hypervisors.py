# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

import os
import pprint

from engine.services.db.hypervisors import get_pool_hypers_conf
from engine.services.lib.functions import clean_intermediate_status
from engine.services.log import logs
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID

from .balancers import BalancerInterface

status_to_delete = [
    "ForceDeleting",
    "Creating",
    "CreatingAndStarting",
    "CreatingDiskFromScratch",
]
status_to_failed = ["Updating", "Deleting"]
status_to_stopped = ["Starting"]


def move_actions_to_others_hypers(
    hyp_id, d_queues, remove_stopping=False, remove_if_no_more_hyps=False
):
    # balancer = Balancer_no_stats()

    for type_queue, d_q in d_queues.items():
        if hyp_id not in d_q:
            logs.main.info(
                f"no queue of type {type_queue} in hypervisor {hyp_id} to move actions to other hyper"
            )
            continue
        retain_actions_in_queue = []
        while d_q[hyp_id].empty() is False:
            action = d_q[hyp_id].get()

            new_hyp = False
            # get next hyp
            # while True:
            #     new_hyp = balancer.get_next()
            #     if hyp_id in balancer.hyps and len(balancer.hyps == 1):
            #         logs.workers.info(
            #             f"can't move actions to other hyps, only {hyp_id} is online"
            #         )
            #         new_hyp = False
            #         break
            #     if new_hyp != hyp_id:
            #         break

            if action["type"] == "stop_thread":
                retain_actions_in_queue.append(action)
                continue

            elif action["type"] == "shutdown_domain" or action["type"] == "stop_domain":
                if remove_stopping is False:
                    retain_actions_in_queue.append(action)
                else:
                    id_domain = action["id_domain"]
                    clean_intermediate_status(
                        reason="delete actions from queue of hyper",
                        only_domain_id=id_domain,
                    )

            else:
                if new_hyp is False or new_hyp not in d_q.keys():
                    if new_hyp not in d_q.keys() and type(new_hyp) is str:
                        logs.main.warn(
                            f"can't move action {action['type']} to hypervisor {new_hyp} because queue {type_queue} don't exist"
                        )
                    if remove_if_no_more_hyps is False:
                        retain_actions_in_queue.append(action)
                    else:
                        if "id_domain" in action.keys():
                            id_domain = action["id_domain"]
                            clean_intermediate_status(
                                reason="delete action from queue of hyper",
                                only_domain_id=id_domain,
                            )
                            logs.main.info(
                                f'action {action["type"]} deleted in hypervisor {hyp_id} in queue {type_queue}'
                            )
                            logs.main.debug(pprint.pformat(action))
                else:
                    d_q[new_hyp].put(action)
                    logs.main.info(
                        f'action {action["type"]} moved from {hyp_id} to {new_hyp} in queue {type_queue}'
                    )
                    logs.main.debug(pprint.pformat(action))

        for action in retain_actions_in_queue:
            d_q[hyp_id].put(action)


class PoolHypervisors:
    def __init__(self, id_pool, balancer_type=None):
        self.id_pool = id_pool
        self.balancer = BalancerInterface(
            id_pool,
            balancer_type=os.environ.get(
                "ENGINE_HYPER_BALANCER", "available_ram_percent"
            ),
        )
        self.conf = get_pool_hypers_conf(id_pool)


class PoolDiskoperations:
    def __init__(
        self,
        id_pool=DEFAULT_STORAGE_POOL_ID,
        balancer_type=None,
    ):
        self.id_pool = id_pool
        self.balancer = BalancerInterface(
            id_pool, balancer_type=os.environ.get("ENGINE_DISK_BALANCER", "less_cpu")
        )
        self.conf = get_pool_hypers_conf(id_pool)
