# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
#      Daniel Criado Casas
# License: AGPLv3

class BalancerInterface(object):
    def get_next(self, args): raise NotImplementedError