# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

# coding=utf-8


from random import randint
from time import sleep
from traceback import format_exc

import pprint

from engine.services.balancers.balancer_factory import BalancerFactory
from engine.services.db.hypervisors import get_hypers_in_pool,get_pool_hypers_conf,get_hypers_info
from engine.services.db.domains import get_create_dict
from engine.services.log import logs
from engine.services.lib.functions import clean_intermediate_status

status_to_delete = ['Creating', 'CreatingAndStarting', 'CreatingDiskFromScratch', 'CreatingFromBuilder']
status_to_failed = ['Updating', 'Deleting']
status_to_stopped = ['Starting']

def move_actions_to_others_hypers(hyp_id,
                                  d_queues,
                                  remove_stopping=False,
                                  remove_if_no_more_hyps=False):
    balancer = Balancer_no_stats()

    for type_queue,d_q in d_queues.items():
        if hyp_id not in d_q:
            logs.main.info(f'no queue of type {type_queue} in hypervisor {hyp_id} to move actions to other hyper')
            continue
        retain_actions_in_queue = []
        while d_q[hyp_id].empty() is False:
            action = d_q[hyp_id].get()

            #get next hyp
            while True:
                new_hyp = balancer.get_next()
                if hyp_id in balancer.hyps and len(balancer.hyps == 1):
                    logs.workers.info(f"can't move actions to other hyps, only {hyp_id} is online")
                    new_hyp = False
                    break
                if new_hyp != hyp_id:
                    break

            if action['type'] == 'stop_thread':
                retain_actions_in_queue.append(action)
                continue

            elif action['type'] == 'shutdown_domain' or action['type'] == 'stop_domain':
                if remove_stopping is False:
                    retain_actions_in_queue.append(action)
                else:
                    id_domain = action['id_domain']
                    clean_intermediate_status(reason='delete actions from queue of hyper', only_domain_id=id_domain)

            else:
                if new_hyp is False or new_hyp not in d_q.keys():
                    if new_hyp not in d_q.keys() and type(new_hyp) is str:
                        logs.main.warn(f"can't move action {action['type']} to hypervisor {new_hyp} because queue {type_queue} don't exist")
                    if remove_if_no_more_hyps is False:
                        retain_actions_in_queue.append(action)
                    else:
                        if 'id_domain' in action.keys():
                            id_domain = action['id_domain']
                            clean_intermediate_status(reason='delete action from queue of hyper',only_domain_id=id_domain)
                            logs.main.info(f'action {action["type"]} deleted in hypervisor {hyp_id} in queue {type_queue}')
                            logs.main.debug(pprint.pformat(action))
                else:
                    d_q[new_hyp].put(action)
                    logs.main.info(f'action {action["type"]} moved from {hyp_id} to {new_hyp} in queue {type_queue}')
                    logs.main.debug(pprint.pformat(action))

        for action in retain_actions_in_queue:
            d_q[hyp_id].put(action)



class Balancer_no_stats():
    def __init__(self,id_pool='default'):
        self.hyps = []
        self.index_round_robin = 0
        self.id_pool = id_pool

    def get_next(self, **kwargs):
        self.hyps = get_hypers_in_pool(self.id_pool,exclude_hyp_only_forced=True)
        #return self.hyps[randint(0,len(self.hyps)-1)]
        self.index_round_robin += 1
        if self.index_round_robin >= len(self.hyps):
            self.index_round_robin = 0
        if len(self.hyps) > 0:
            return self.hyps[self.index_round_robin]
        else:
            return False

class PoolHypervisors():
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

    def get_next(self, domain_id=None, to_create_disk=False, path_selected='',
                 force_hyp=False,
                 preferred_hyp=False):
        kwargs = {'to_create_disk': to_create_disk,
                'path_selected': path_selected,
                'domain_id':domain_id}
        if domain_id is not None:
            # try:
                create_dict = get_create_dict(domain_id)
                if create_dict['hardware']['videos'][0].find('nvidia') == 0 or \
                        create_dict['hardware']['videos'][0].find('gpu-default') == 0 :
                    type = create_dict['hardware']['videos'][0]
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
                    hypers_online_exclude_only_forced = get_hypers_info(id_pool=self.id_pool,exclude_only_forced=True)

                    if force_hyp != False:
                        if force_hyp in [a['id'] for a in hypers_online]:
                            return force_hyp,{}
                        else:
                            logs.hmlog.error(f'force hypervisor {force_hyp} is not online, desktop will not start')
                            return False,{}

                    if preferred_hyp != False:
                        if preferred_hyp in [a['id'] for a in hypers_online_exclude_only_forced]:
                            return preferred_hyp,{}
                        else:
                            logs.hmlog.info(f'preferred hypervisor {preferred_hyp} is no online, trying other hypervisor online in pool')
        # except:
            #     pass
        return self.balancer.get_next(**kwargs),{}

    def get_next_hyp_with_gpu(self,type,force_hyp=False,preferred_hyp=False):
        hypers_online = get_hypers_info(id_pool=self.id_pool)
        hypers_online_exclude_only_forced = get_hypers_info(id_pool=self.id_pool,exclude_only_forced=True)
        if len(hypers_online) == 0:
            return False
        hypers_online_with_gpu = [h for h in hypers_online if len(h.get('default_gpu_models',{})) > 0]
        ids_hypers_online_with_gpu = [h['id'] for h in hypers_online_with_gpu]
        hypers_online_with_gpu_excluded_only_forced = [h for h in hypers_online_exclude_only_forced if len(h.get('default_gpu_models',{})) > 0]
        ids_hypers_online_with_gpu_excluded_only_forced = [h['id'] for h in hypers_online_with_gpu_excluded_only_forced]
        if force_hyp != False:
            if force_hyp in ids_hypers_online_with_gpu:
                hypers_online_with_gpu = [h for h in hypers_online_with_gpu if h['id'] == force_hyp]
            else:
                logs.hmlog.error(f'force hypervisor {preferred_hyp} is not online, desktop will not start')
                return False,False,False,False
        else:
            hypers_online_with_gpu = hypers_online_with_gpu_excluded_only_forced

        if preferred_hyp != False:
            if preferred_hyp in hypers_online_with_gpu:
                hypers_online_with_gpu = [h for h in hypers_online_with_gpu if h['id'] == preferred_hyp]
            else:
                logs.hmlog.info(f'preferred hypervisor {preferred_hyp} is no online, trying other hypervisor online in pool')
                pass

        if len(hypers_online_with_gpu) == 0:
            return False,False,False,False
        available_uids = {}
        max_available = 0
        next_hyp = False
        next_available_uid = False
        next_id_pci = False
        next_model = False
        for d_hyper in hypers_online_with_gpu:
            d_uids = d_hyper['nvidia_uids']
            for id_pci,d in d_uids.items():
                if type == 'nvidia' or type == 'nvidia-with-qxl' or type == 'gpu-default':
                    model = d_hyper['default_gpu_models'][id_pci]
                else:
                    model = type.split('nvidia_')[0]
                if model in d.keys():
                    available_uids[id_pci] = [k for k,v in d[model].items() if v['started'] is False and v['reserved'] is False]
                    #TODO falta verificar realmente cuantos hay disponibles con libvirt
                    if len(available_uids[id_pci]) > max_available:
                        max_available = len(available_uids[id_pci])
                        next_hyp = d_hyper['id']
                        next_available_uid = available_uids[id_pci][0]
                        next_id_pci = id_pci
                        next_model = model
        return next_hyp,next_available_uid,next_id_pci,next_model


