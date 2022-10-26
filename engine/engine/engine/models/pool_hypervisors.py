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

from engine.services.balancers.balancer_factory import BalancerFactory
from engine.services.db import get_table_field, get_video_model_profile
from engine.services.db.domains import (
    get_create_dict,
    get_vgpus_mdevs,
    update_vgpu_uuid_domain_action,
)
from engine.services.db.hypervisors import (
    get_hypers_in_pool,
    get_hypers_info,
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

            # get next hyp
            while True:
                new_hyp = balancer.get_next()
                if hyp_id in balancer.hyps and len(balancer.hyps == 1):
                    logs.workers.info(
                        f"can't move actions to other hyps, only {hyp_id} is online"
                    )
                    new_hyp = False
                    break
                if new_hyp != hyp_id:
                    break

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
        self.hyps = []
        self.index_round_robin = 0
        self.id_pool = id_pool

    def get_next(self, **kwargs):
        self.hyps = get_hypers_in_pool(self.id_pool, exclude_hyp_only_forced=True)
        # return self.hyps[randint(0,len(self.hyps)-1)]
        self.index_round_robin += 1
        if self.index_round_robin >= len(self.hyps):
            self.index_round_robin = 0
        if len(self.hyps) > 0:
            return self.hyps[self.index_round_robin]
        else:
            return False


class PoolHypervisors:
    def __init__(self, id_pool):
        self.id_pool = id_pool
        self.balancer_name = "round_robin"  # get from config?
        # self.balancer_name = "central_manager"  # get from config?
        try:
            self.init_balancer()
        except:
            # format_exc() -- > This is like print_exc(limit) but returns a string instead of printing to a file.
            # print_exc(limit) --> This is a shorthand for print_exception(*sys.exc_info(), limit, file, chain).
            logs.hmlog.error(format_exc())

        self.conf = get_pool_hypers_conf(id_pool)

    def init_balancer(self):
        self.balancer = Balancer_no_stats(self.id_pool)

    def get_next(
        self,
        domain_id=None,
        to_create_disk=False,
        path_selected="",
        force_hyp=False,
        preferred_hyp=False,
        reservables=True,
    ):
        kwargs = {
            "to_create_disk": to_create_disk,
            "path_selected": path_selected,
            "domain_id": domain_id,
        }
        if domain_id is not None:
            # try:
            create_dict = get_create_dict(domain_id)

            if reservables is False:
                list_gpus = []
            else:
                list_gpus = create_dict.get("reservables", {}).get("vgpus", [])

            if (
                type(list_gpus) is list
                and len(list_gpus) > 0
                and list_gpus[0] != "None"
                and list_gpus[0] != None
            ):
                gpu_profile = list_gpus[0]

                next_model = gpu_profile.split("-")[-2]
                next_profile = gpu_profile.split("-")[-1]

                force_gpus = create_dict.get("reservables", {}).get("force_gpus", [])
                if type(force_gpus) is list and len(force_gpus) > 0:
                    force_gpu = force_gpus[0]
                    hyp_selected = get_table_field("vgpus", force_gpu, "hyp_id")
                    if "Online" == get_table_field(
                        "hypervisors", hyp_selected, "status"
                    ):
                        (
                            next_hyp,
                            next_available_uid,
                            next_vgpu_id,
                        ) = self.get_hyp_with_uuid_available(
                            gpu_profile, hyp_selected, False
                        )

                        extra = {
                            "nvidia": True,
                            "uid": next_available_uid,
                            "vgpu_id": next_vgpu_id,
                            "model": next_model,
                            "profile": next_profile,
                        }

                        update_vgpu_uuid_domain_action(
                            next_vgpu_id,
                            next_available_uid,
                            "domain_reserved",
                            domain_id=domain_id,
                            profile=next_profile,
                        )

                        return next_hyp, extra
                    else:
                        logs.hmlog.error(
                            f"force gpu {force_gpu} in hypervisor {hyp_selected} is not online, desktop will not start"
                        )
                        return False, {}

                (
                    next_hyp,
                    next_available_uid,
                    next_gpu_id,
                ) = self.get_hyp_with_uuid_available(
                    gpu_profile, force_hyp, preferred_hyp
                )
                extra = {
                    "nvidia": True,
                    "uid": next_available_uid,
                    "gpu_id": next_gpu_id,
                    "model": next_model,
                    "profile": next_profile,
                }
                return next_hyp, extra

            if (
                create_dict["hardware"]["videos"][0].find("nvidia") == 0
                or create_dict["hardware"]["videos"][0].find("gpu-default") == 0
            ):
                type_gpu = create_dict["hardware"]["videos"][0]
                (
                    next_hyp,
                    next_available_uid,
                    next_id_pci,
                    next_model,
                    next_profile,
                ) = self.get_next_hyp_with_gpu(type_gpu, force_hyp, preferred_hyp)

                extra = {
                    "nvidia": True,
                    "uid": next_available_uid,
                    "id_pci": next_id_pci,
                    "model": next_model,
                    "profile": next_profile,
                }
                return next_hyp, extra
            else:
                hypers_online = get_hypers_info(id_pool=self.id_pool)
                hypers_online_exclude_only_forced = get_hypers_info(
                    id_pool=self.id_pool, exclude_only_forced=True
                )

                if force_hyp != False:
                    if force_hyp in [a["id"] for a in hypers_online]:
                        return force_hyp, {}
                    else:
                        logs.hmlog.error(
                            f"force hypervisor {force_hyp} is not online, desktop will not start"
                        )
                        return False, {}

                if preferred_hyp != False:
                    if preferred_hyp in [
                        a["id"] for a in hypers_online_exclude_only_forced
                    ]:
                        return preferred_hyp, {}
                    else:
                        logs.hmlog.info(
                            f"preferred hypervisor {preferred_hyp} is no online, trying other hypervisor online in pool"
                        )
        return self.balancer.get_next(**kwargs), {}

    def get_hyp_with_uuid_available(
        self, gpu_profile, force_hyp=False, preferred_hyp=False
    ):
        if gpu_profile.rfind("NVIDIA-") == 0:
            gpu_profile = gpu_profile.split("NVIDIA-")[1]
        hypers_online = get_hypers_info(id_pool=self.id_pool)
        from pprint import pprint

        print(
            "\n\n## CHIVATO - HYPERS ONLINE #########################################################"
        )
        pprint(hypers_online)
        hypers_online_exclude_only_forced = get_hypers_info(
            id_pool=self.id_pool, exclude_only_forced=True
        )
        if len(hypers_online) == 0:
            return False, False, False
        hypers_online_with_gpu = [
            h
            for h in hypers_online
            if len(
                [
                    i
                    for i in h.get("info", {}).get("nvidia", {}).values()
                    if i == gpu_profile.split("-")[-2]
                ]
            )
            > 0
        ]
        ids_hypers_online_with_gpu = [h["id"] for h in hypers_online_with_gpu]
        hypers_online_with_gpu_excluded_only_forced = [
            h
            for h in hypers_online_exclude_only_forced
            if len(
                [
                    i
                    for i in h.get("info", {}).get("nvidia", {}).values()
                    if i == gpu_profile.split("-")[-2]
                ]
            )
            > 0
        ]
        ids_hypers_online_with_gpu_excluded_only_forced = [
            h["id"] for h in hypers_online_with_gpu_excluded_only_forced
        ]
        if force_hyp != False:
            if force_hyp in ids_hypers_online_with_gpu:
                hypers_online_with_gpu = [
                    h for h in hypers_online_with_gpu if h["id"] == force_hyp
                ]
            else:
                logs.hmlog.error(
                    f"force hypervisor {preferred_hyp} is not online, desktop will not start"
                )
                return False, False, False
        else:
            hypers_online_with_gpu = hypers_online_with_gpu_excluded_only_forced

        if preferred_hyp != False:
            if preferred_hyp in hypers_online_with_gpu:
                hypers_online_with_gpu = [
                    h for h in hypers_online_with_gpu if h["id"] == preferred_hyp
                ]
            else:
                logs.hmlog.info(
                    f"preferred hypervisor {preferred_hyp} is not online, trying other hypervisor online in pool"
                )
                pass

        if len(hypers_online_with_gpu) == 0:
            logs.hmlog.error(f"There are not hypervisors with GPU online")
            return False, False, False
        else:
            uuid_selected = False
            # now find free uuids:
            for h in hypers_online_with_gpu:
                for pci, model in h["info"]["nvidia"].items():
                    if model == gpu_profile.split("-")[-2]:
                        gpu_type = gpu_profile.split("-")[-1]
                        gpu_id = h["id"] + "-" + pci
                        gpu_type_active, mdevs = get_vgpus_mdevs(gpu_id, gpu_type)
                        if gpu_type_active == gpu_type:
                            for mdev_uuid, d in mdevs[gpu_type].items():
                                if (
                                    d["domain_reserved"] is False
                                    and d["domain_started"] is False
                                    and d["created"] is True
                                ):
                                    uuid_selected = mdev_uuid
                                    next_hyp = h["id"]
                                    next_available_uid = uuid_selected
                                    next_gpu_id = gpu_id
                                    return next_hyp, next_available_uid, next_gpu_id
                if uuid_selected != False:
                    break
        return False, False, False

    def get_next_hyp_with_gpu(self, video_id, force_hyp=False, preferred_hyp=False):
        hypers_online = get_hypers_info(id_pool=self.id_pool)
        hypers_online_exclude_only_forced = get_hypers_info(
            id_pool=self.id_pool, exclude_only_forced=True
        )
        if len(hypers_online) == 0:
            return False
        hypers_online_with_gpu = [
            h for h in hypers_online if len(h.get("info", {}).get("nvidia", {})) > 0
        ]
        ids_hypers_online_with_gpu = [h["id"] for h in hypers_online_with_gpu]
        hypers_online_with_gpu_excluded_only_forced = [
            h
            for h in hypers_online_exclude_only_forced
            if len(h.get("info", {}).get("nvidia", {})) > 0
        ]
        ids_hypers_online_with_gpu_excluded_only_forced = [
            h["id"] for h in hypers_online_with_gpu_excluded_only_forced
        ]
        if force_hyp != False:
            if force_hyp in ids_hypers_online_with_gpu:
                hypers_online_with_gpu = [
                    h for h in hypers_online_with_gpu if h["id"] == force_hyp
                ]
            else:
                logs.hmlog.error(
                    f"force hypervisor {preferred_hyp} is not online, desktop will not start"
                )
                return False, False, False, False, False
        else:
            hypers_online_with_gpu = hypers_online_with_gpu_excluded_only_forced

        if preferred_hyp != False:
            if preferred_hyp in hypers_online_with_gpu:
                hypers_online_with_gpu = [
                    h for h in hypers_online_with_gpu if h["id"] == preferred_hyp
                ]
            else:
                logs.hmlog.info(
                    f"preferred hypervisor {preferred_hyp} is not online, trying other hypervisor online in pool"
                )
                pass

        if len(hypers_online_with_gpu) == 0:
            logs.hmlog.error(f"There are not hypervisors with GPU online")
            return False, False, False, False, False

        available_uids = {}
        max_available = 0
        next_hyp = False
        next_available_uid = False
        next_id_pci = False
        next_model = False
        vgpus = {}

        model, profile = get_video_model_profile(video_id)
        # if model == "nvidia" gpu-default, generic gpu, else restricted to model (example: A40)
        if model != "nvidia":
            tmp = [
                h
                for h in hypers_online_with_gpu
                if model in h["info"]["nvidia"].values()
            ]
            if len(tmp) == 0:
                logs.hmlog.error(
                    f"There are not hypervisors with GPU model {model}online"
                )
                return False, False, False, False, False
            else:
                hypers_online_with_gpu = tmp

        l_vgpus_ids = []

        for d_hyper in hypers_online_with_gpu:
            hyp_id = d_hyper["id"]
            for pci_bus, model_pci in d_hyper["info"]["nvidia"].items():
                vgpu_id = "-".join([hyp_id, pci_bus])
                if model == "nvidia" or model == model_pci:
                    l_vgpus_ids.append(vgpu_id)
                    vgpus[vgpu_id] = get_vgpu(vgpu_id)
                    vgpu_profile = vgpus[vgpu_id]["vgpu_profile"]
                    uuids_available = {
                        uid: d_uid
                        for uid, d_uid in vgpus[vgpu_id]["mdevs"][vgpu_profile].items()
                        if d_uid["created"] == True
                        and d_uid["domain_started"] == False
                        and d_uid["domain_reserved"] == False
                    }
                    if len(uuids_available) > 0:
                        next_available_uid = list(uuids_available.keys())[0]
                        break
                    else:
                        logs.hmlog.debug(
                            f"There are not uuids availables in hypervisors {hyp_id} and profile {vgpu_profile}"
                        )

        if next_available_uid == False:
            logs.hmlog.info(f"There are not uuids availables in hypervisors with GPUs")
            return False, False, False, False, False

        next_hyp = hyp_id
        next_model = model_pci
        next_profile = vgpu_profile

        return next_hyp, next_available_uid, pci_bus, next_model, next_profile
