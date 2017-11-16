# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8

# from ui_actions import UiActions
#from threads import launch_threads_status_hyp, launch_thread_worker, launch_disk_operations_thread
#from threads import dict_threads_active


# from ..hyp_threads import launch_all_hyps_threads

from engine.services.db.db import get_hypers_in_pool
from engine.config import CONFIG_DICT

TIMEOUT_TRYING_SSH = float(CONFIG_DICT["TIMEOUTS"]["timeout_trying_ssh"])


class PoolHypervisors():
    def __init__(self,id_pool):
        self.id_pool = id_pool


        self.last_index=0
    def get_next(self,to_create_disk=False, path_selected=''):
        # NEXT RELEASES WE WILL WORK HERE
        # INFO TO DEVELOPER, SI se crea un disco podemos decidir algo distinto... en la decision de pools...
        self.hyps = get_hypers_in_pool(self.id_pool)
        self.total_hyps = len(self.hyps)



        if self.total_hyps > 0:
            if to_create_disk is False:
                if self.last_index >= self.total_hyps-1:
                    self.last_index = 0
                else:
                    self.last_index += 1
                return self.hyps[self.last_index]
            elif to_create_disk is True and len(path_selected) > 0:
                pass

        else:
            return False
