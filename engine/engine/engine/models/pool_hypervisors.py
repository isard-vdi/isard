# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

import os
import pprint

from engine.services.db import update_domain_status
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
status_to_failed = ["Deleting"]
status_to_stopped = ["Starting"]


def move_actions_to_others_hypers(
    hyp_id,
    d_queues,
    remove_stopping=False,
    remove_if_no_more_hyps=False,
    balancer=None,
    storage_pool_id=None,
    keep_gpu_actions=False,
):
    for type_queue, d_q in d_queues.items():
        if hyp_id not in d_q:
            logs.main.info(
                f"no queue of type {type_queue} in hypervisor {hyp_id} to move actions to other hyper"
            )
            continue
        retain_actions_in_queue = []
        while d_q[hyp_id].empty() is False:
            action = d_q[hyp_id].get()

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
                # If keep_gpu_actions, retain GPU-bound actions in original queue
                if keep_gpu_actions and action.get("nvidia_uid"):
                    retain_actions_in_queue.append(action)
                    continue

                # Try to reassign to another hypervisor via balancer
                new_hyp = False
                if balancer and action["type"] in (
                    "start_domain",
                    "start_paused_domain",
                ):
                    try:
                        candidate, _ = balancer.get_next_hypervisor(
                            storage_pool_id=storage_pool_id or DEFAULT_STORAGE_POOL_ID,
                        )
                        if candidate and candidate != hyp_id:
                            new_hyp = candidate
                    except Exception as e:
                        logs.main.error(
                            f"Failed to get alternative hypervisor for {action.get('id_domain')}: {e}"
                        )

                if new_hyp and new_hyp in d_q.keys():
                    d_q[new_hyp].put(action)
                    logs.main.info(
                        f'action {action["type"]} moved from {hyp_id} to {new_hyp} in queue {type_queue}'
                    )
                    logs.main.debug(pprint.pformat(action))
                elif remove_if_no_more_hyps:
                    if "id_domain" in action.keys():
                        id_domain = action["id_domain"]
                        update_domain_status(
                            "Failed",
                            id_domain,
                            detail=f"Hypervisor {hyp_id} unavailable, no alternatives found",
                        )
                        logs.main.info(
                            f'action {action["type"]} for {id_domain} failed in hypervisor {hyp_id} in queue {type_queue}, no alternatives'
                        )
                        logs.main.debug(pprint.pformat(action))
                else:
                    retain_actions_in_queue.append(action)

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
