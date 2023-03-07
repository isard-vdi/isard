# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

# coding=utf-8


import pprint
from random import randint
from time import sleep
from traceback import format_exc

from engine.services.db import get_table_field, get_video_model_profile
from engine.services.db.domains import (
    get_create_dict,
    get_vgpus_mdevs,
    update_vgpu_uuid_domain_action,
)
from engine.services.db.hypervisors import (
    get_hypers_gpu_online,
    get_hypers_in_pool,
    get_hypers_info,
    get_hypers_online,
    get_pool_hypers_conf,
    get_vgpu,
)
from engine.services.lib.functions import clean_intermediate_status
from engine.services.log import logs

status_to_delete = [
    "ForceDeleting",
    "Creating",
    "CreatingAndStarting",
    "CreatingDiskFromScratch",
    "CreatingFromBuilder",
]
status_to_failed = ["Updating", "Deleting"]
status_to_stopped = ["Starting"]


def move_actions_to_others_hypers(
    hyp_id, d_queues, remove_stopping=False, remove_if_no_more_hyps=False
):
    balancer = Balancer_no_stats()

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


class Balancer_no_stats:
    def __init__(self, id_pool="default"):
        self.index_round_robin = 0
        self.id_pool = id_pool

    def get_next_capabilities_virt(self, forced_hyp=None, favourite_hyp=None):
        hypers = get_hypers_online(
            self.id_pool, forced_hyp, favourite_hyp
        )  # check capabilities?
        if len(hypers) == 0:
            return False
        if len(hypers) == 1:
            return hypers[0]["id"]
        self.index_round_robin += 1
        if self.index_round_robin >= len(hypers):
            self.index_round_robin = 0
        return hypers[self.index_round_robin]["id"]

    def get_next_capabilities_diskopts(self):
        return self.get_next_capabilities_virt()

    def get_next_capabilities_virt_gpus(
        self,
        forced_hyp=None,
        favourite_hyp=None,
        gpu_profile=None,
        forced_gpus_hypervisors=None,
    ):
        gpu_hypervisors_online = get_hypers_gpu_online(
            self.id_pool,
            forced_hyp,
            favourite_hyp,
            gpu_profile,
            forced_gpus_hypervisors,
        )

        if len(gpu_hypervisors_online) == 0:
            return False, {}
        if len(gpu_hypervisors_online) == 1:
            return gpu_hypervisors_online[0]["id"], self._parse_extra_info(
                gpu_hypervisors_online[0]["gpu_selected"]
            )
        self.index_round_robin += 1
        if self.index_round_robin >= len(gpu_hypervisors_online):
            self.index_round_robin = 0
        return (
            gpu_hypervisors_online[self.index_round_robin]["id"],
            self._parse_extra_info(
                gpu_hypervisors_online[self.index_round_robin]["gpu_selected"]
            ),
        )

    def _parse_extra_info(self, gpu_selected):
        return {
            "nvidia": True,
            "uid": gpu_selected["next_available_uid"],
            "vgpu_id": gpu_selected["next_gpu_id"],
            "model": gpu_selected["gpu_profile"].split("-")[-2],
            "profile": gpu_selected["gpu_profile"].split("-")[-1],
        }


class PoolHypervisors:
    def __init__(self, id_pool):
        self.id_pool = id_pool
        try:
            self.init_balancer()
        except:
            logs.hmlog.error(format_exc())

        self.conf = get_pool_hypers_conf(id_pool)

    def init_balancer(self):
        self.balancer = Balancer_no_stats(self.id_pool)

    def get_next_diskopts(self):
        return self.balancer.get_next_capabilities_diskopts()

    def get_next_hypervisor(
        self, forced_hyp=None, favourite_hyp=None, reservables=None, force_gpus=None
    ):
        if (
            not reservables
            or not reservables.get("vgpus")
            or not len(reservables.get("vgpus", []))
        ):
            return (
                self.balancer.get_next_capabilities_virt(forced_hyp, favourite_hyp),
                {},
            )

        # Desktop has vgpu
        gpu_profile = reservables.get("vgpus")[0]

        if force_gpus and len(force_gpus):
            forced_gpus_hypervisors = [
                get_table_field("vgpus", fgh, "hyp_id") for fgh in force_gpus
            ]
        else:
            forced_gpus_hypervisors = None

        hypervisor, extra = self.balancer.get_next_capabilities_virt_gpus(
            forced_hyp, favourite_hyp, gpu_profile, forced_gpus_hypervisors
        )

        # If no hypervisor with gpu available and online, return False
        if hypervisor == False:
            logs.hmlog.error(
                f"No hypervisor with gpu {gpu_profile} available in pool {self.id_pool}"
            )
            return False, {}

        return hypervisor, extra
