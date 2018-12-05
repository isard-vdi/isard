#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

from ..models.config import Config

from .local import Local
from .ldap import LDAP


"""
kinds is an array that contains all the authentication kinds
"""
kinds = {"local": Local, "ldap": LDAP}


def initialize_kinds():
    """
    initialize_kinds initializes all the enabled authentication classes
    :return: returns an object where the key is the kind an the content is the authentication object initialized
    """
    cfg = Config()
    cfg.get()

    initialized_kinds = {}

    for kind in kinds:
        if cfg.auth[kind]["active"]:
            initialized_kinds[kind] = kinds[kind]()
            initialized_kinds[kind].connect()

    return initialized_kinds
