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
from traceback import format_exc

from engine.config import CONFIG_DICT
from engine.services.balancers.central_manager import CentralManager
from engine.services.balancers.round_robin import RoundRobin
from engine.services.db.hypervisors import get_hypers_in_pool
from engine.services.log import hypman_log as hmlog

TIMEOUT_TRYING_SSH = float(CONFIG_DICT["TIMEOUTS"]["timeout_trying_ssh"])


class PoolHypervisors():
    def __init__(self, id_pool, manager, hyps_ready_count):
        self.id_pool = id_pool
        # self.balancer_name = "round_robin"  # get from config?
        self.balancer_name = "central_manager"  # get from config?
        try:
            self.init_balancer(manager, hyps_ready_count)
        except:
            # format_exc() -- > This is like print_exc(limit) but returns a string instead of printing to a file.
            # print_exc(limit) --> This is a shorthand for print_exception(*sys.exc_info(), limit, file, chain).
            hmlog.error(format_exc())

    def init_balancer(self, manager, hyps_ready_count):
        if self.balancer_name == "round_robin":
            self.balancer = RoundRobin(self.id_pool)
        elif self.balancer_name == "central_manager":
            hyps_obj = self.get_hyps_obj(manager, hyps_ready_count)
            self.balancer = CentralManager(hyps_obj)

    def get_hyps_obj(self, manager, hyps_ready_count):
        hyps_obj = {}
        hyps_id = get_hypers_in_pool(self.id_pool)
        while (len(hyps_id) < hyps_ready_count):
            sleep(2)
            hyps_id = get_hypers_in_pool(self.id_pool)
        for hyp_id in hyps_id:
            while (not getattr(manager.t_status[hyp_id], "status_obj", None)):
                sleep(2)
            while (not getattr(manager.t_status[hyp_id].status_obj, "hyp_obj", None)):
                sleep(2)
            hyps_obj[hyp_id] = manager.t_status[hyp_id].status_obj.hyp_obj
        return hyps_obj

    def get_next(self, to_create_disk=False, path_selected=''):
        args = {'to_create_disk': to_create_disk,
                'path_selected': path_selected}
        return self.balancer.get_next(args)
