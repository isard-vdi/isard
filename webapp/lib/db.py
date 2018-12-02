#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import rethinkdb as r


class DB:
    """
    DB is the class responsible for creating connections with the DB
    """

    def __init__(self):
        """
        __init__ creates the connection with the DB
        """
        self.conn = r.connect(host="localhost")
        self.conn.use("isard")
