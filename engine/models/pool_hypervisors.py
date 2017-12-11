# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8

# from ui_actions import UiActions
# from threads import launch_threads_status_hyp, launch_thread_worker, launch_disk_operations_thread
# from threads import dict_threads_active


# from ..hyp_threads import launch_all_hyps_threads
from time import sleep

from engine.services.balancers.round_robin import RoundRobin
from engine.services.db.hypervisors import get_hypers_in_pool, get_hypers_info
from engine.config import CONFIG_DICT
from engine.services.log import hypman_log as hmlog

TIMEOUT_TRYING_SSH = float(CONFIG_DICT["TIMEOUTS"]["timeout_trying_ssh"])


class PoolHypervisors():
    def __init__(self, id_pool, manager, hyps_ready_count):
        self.id_pool = id_pool
        self.balancer_name = "round_robin"  # get from config?
        try:
            self._init_hyps(manager, hyps_ready_count)
            self.init_balancer()
        except Exception as e:
            hmlog.error(e)


    def _init_hyps(self, manager, hyps_ready_count):
        self.hyps_obj = {}
        hyps_id = get_hypers_in_pool(self.id_pool)
        while (len(hyps_id) < hyps_ready_count):
            sleep(2)
            hyps_id = get_hypers_in_pool(self.id_pool)
        for hyp_id in hyps_id:
            while (not getattr(manager.t_status[hyp_id], "status_obj", None)):
                sleep(2)
            while (not getattr(manager.t_status[hyp_id].status_obj, "hyp_obj", None)):
                sleep(2)
            self.hyps_obj[hyp_id] = manager.t_status[hyp_id].status_obj.hyp_obj
            hmlog.debug(self.hyps_obj[hyp_id].load)

    def init_balancer(self):
        if self.balancer_name == "round_robin":
            self.balancer = RoundRobin(self.id_pool)

    def get_next(self, to_create_disk=False, path_selected=''):
        args = {'to_create_disk': to_create_disk,
                'path_selected': path_selected}
        return self.balancer.get_next(args)
