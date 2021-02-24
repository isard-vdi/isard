# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

# coding=utf-8


from random import randint
from time import sleep
from traceback import format_exc

from engine.services.balancers.balancer_factory import BalancerFactory
from engine.services.db.hypervisors import get_hypers_in_pool,get_pool_hypers_conf,get_hypers_info
from engine.services.db.domains import get_domain_hardware_dict
from engine.services.log import logs

class Balancer_no_stats():
    def __init__(self,hyps_id):
        assert type(hyps_id) is list
        assert len(hyps_id) >= 1
        self.hyps = hyps_id
        self.index_round_robin = 0
    # args = {'to_create_disk': to_create_disk,
    #         'path_selected': path_selected,
    #         'domain_id': domain_id}

    def get_next(self, **kwargs):
        #return self.hyps[randint(0,len(self.hyps)-1)]
        self.index_round_robin += 1
        if self.index_round_robin >= len(self.hyps):
            self.index_round_robin = 0
        return self.hyps[self.index_round_robin]

class PoolHypervisors():
    def __init__(self, id_pool, manager, hyps_ready_count, with_status_threads=True):
        self.id_pool = id_pool
        self.with_status_threads = with_status_threads
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
        if self.with_status_threads is True:
            hyps = self.get_hyps_obj(manager, hyps_ready_count)
            kwargs = {"id_pool": self.id_pool,
                      "hyps": hyps}

            self.balancer = BalancerFactory.create(self.balancer_name, **kwargs)
        else:
            hyps_id = get_hypers_in_pool(self.id_pool)
            while (len(hyps_id) < hyps_ready_count):
                sleep(2)
                hyps_id = get_hypers_in_pool(self.id_pool)
            self.balancer = Balancer_no_stats(hyps_id)


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

    def get_next(self, domain_id=None, to_create_disk=False, path_selected='',
                 force_hyp=False,
                 preferred_hyp=False):
        kwargs = {'to_create_disk': to_create_disk,
                'path_selected': path_selected,
                'domain_id':domain_id}
        if domain_id is not None:
            # try:
                hw_dict = get_domain_hardware_dict(domain_id)
                if hw_dict['video']['type'].find('nvidia') == 0:
                    type = hw_dict['video']['type']
                    next_hyp,next_available_uid,next_id_pci,next_model = self.get_next_hyp_with_gpu(type,force_hyp,preferred_hyp)
                    #TODO ALBERTO
                    # FALTA modificar el xml para que arranque o pasarle de alguna manera el uuid
                    extra = {'nvidia': True,
                             'uid':    next_available_uid,
                             'id_pci': next_id_pci,
                             'model':  next_model}
                    return next_hyp,extra
                else:
                    hypers_online = get_hypers_info(id_pool=self.id_pool)

                    if force_hyp != False:
                        if force_hyp in hypers_online:
                            return force_hyp,{}
                        else:
                            logs.hmlog.error(f'force hypervisor {preferred_hyp} is not online, desktop will not start')
                            return False,{}

                    if preferred_hyp != False:
                        if force_hyp in hypers_online:
                            return preferred_hyp,{}
                        else:
                            logs.hmlog.info(f'preferred hypervisor {preferred_hyp} is no online, trying other hypervisor online in pool')
        # except:
            #     pass
        return self.balancer.get_next(**kwargs),{}

    def get_next_hyp_with_gpu(self,type,force_hyp=False,preferred_hyp=False):
        hypers_online = get_hypers_info(id_pool=self.id_pool)
        if len(hypers_online) == 0:
            return False
        hypers_online_with_gpu = [h for h in hypers_online if len(h.get('default_gpu_models',{})) > 0]
        ids_hypers_online_with_gpu = [h['id'] for h in hypers_online_with_gpu]
        if force_hyp != False:
            if force_hyp in ids_hypers_online_with_gpu:
                hypers_online_with_gpu = [h for h in hypers_online_with_gpu if h['id'] == force_hyp]
            else:
                logs.hmlog.error(f'force hypervisor {preferred_hyp} is not online, desktop will not start')
                return False,False,False,False

        if preferred_hyp != False:
            if preferred_hyp in ids_hypers_online_with_gpu:
                hypers_online_with_gpu = [h for h in hypers_online_with_gpu if h['id'] == preferred_hyp]
            else:
                logs.hmlog.info(f'preferred hypervisor {preferred_hyp} is no online, trying other hypervisor online in pool')
                return False,False,False,False

        if len(hypers_online_with_gpu) == 0:
            return False
        available_uids = {}
        max_available = 0
        next_hyp = False
        next_available_uid = False
        next_id_pci = False
        next_model = False
        for d_hyper in hypers_online_with_gpu:
            d_uids = d_hyper['nvidia_uids']
            for id_pci,d in d_uids.items():
                if type == 'nvidia':
                    model = d_hyper['default_gpu_models'][id_pci]
                else:
                    model = type.split('nvidia_')[0]
                if model in d.keys():
                    available_uids[id_pci] = [k for k,v in d[model].items() if v['started'] is False]
                    #TODO falta verificar realmente cuantos hay disponibles con libvirt
                    if len(available_uids[id_pci]) > max_available:
                        max_available = len(available_uids[id_pci])
                        next_hyp = d_hyper['id']
                        next_available_uid = available_uids[id_pci][0]
                        next_id_pci = id_pci
                        next_model = model
        return next_hyp,next_available_uid,next_id_pci,next_model





        pass

