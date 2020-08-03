# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

from engine.services.balancers.balancer_interface import BalancerInterface
from engine.services.db import get_hypers_in_pool


class RoundRobin(BalancerInterface):
    def __init__(self, id_pool=None):
        self.id_pool = id_pool
        self.last_index = 0

    def get_next(self, args):
        to_create_disk = args.get("to_create_disk")
        path_selected = args.get("path_selected")
        # NEXT RELEASES WE WILL WORK HERE
        # INFO TO DEVELOPER, SI se crea un disco podemos decidir algo distinto... en la decision de pools...
        self.hyps = get_hypers_in_pool(self.id_pool)
        self.total_hyps = len(self.hyps)

        if self.total_hyps > 0:
            if to_create_disk is False:
                if self.last_index >= self.total_hyps - 1:
                    self.last_index = 0
                else:
                    self.last_index += 1
                return self.hyps[self.last_index]
            elif to_create_disk is True and len(path_selected) > 0:
                pass

        else:
            return False