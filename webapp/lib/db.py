#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import rethinkdb as r

from .load_config import load_config


class DB:
    """
    DB is the class responsible for creating connections with the DB
    """

    def __init__(self):
        """
        __init__ creates the connection with the DB
        """
        cfg = load_config()

        self.conn = r.connect(host=cfg["RETHINKDB_HOST"], port=cfg["RETHINKDB_PORT"])
        self.conn.use(cfg["RETHINKDB_DB"])
