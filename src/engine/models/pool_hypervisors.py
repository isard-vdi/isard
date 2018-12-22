# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

# coding=utf-8



from time import sleep
from traceback import format_exc

from engine.services.balancers.balancer_factory import BalancerFactory
from engine.services.db.hypervisors import get_hypers_in_pool,get_pool_hypers_conf
from engine.services.log import logs


class PoolHypervisors():
    def __init__(self, id_pool, manager, hyps_ready_count):
        self.id_pool = id_pool
        self.balancer_name = "round_robin"  # get from config?
        # self.balancer_name = "central_manager"  # get from config?
        try:
            self.init_balancer(manager, hyps_ready_count)
        except:
            # format_exc() -- > This is like print_exc(limit) but returns a string instead of printing to a file.
            # print_exc(limit) --> This is a shorthand for print_exception(*sys.exc_info(), limit, file, chain).
            logs.hmlog.error(format_exc())

        self.conf = get_pool_hypers_conf(id_pool)

    def init_balancer(self, manager, hyps_ready_count):
        hyps = self.get_hyps_obj(manager, hyps_ready_count)
        kwargs = {"id_pool": self.id_pool,
                  "hyps": hyps}
        self.balancer = BalancerFactory.create(self.balancer_name, **kwargs)

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

    def get_next(self, domain_id=None, to_create_disk=False, path_selected=''):
        args = {'to_create_disk': to_create_disk,
                'path_selected': path_selected,
                'domain_id':domain_id}
        return self.balancer.get_next(args)
