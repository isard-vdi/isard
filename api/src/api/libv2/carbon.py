# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import logging as log
import os
import pickle
import socket
import struct

#!/usr/bin/env python
# coding=utf-8
import time


class Carbon(object):
    def __init__(self):
        self.HOSTNAME = "isard-api"
        self.SERVER = os.environ["STATS_HOSTNAME"]
        self.PORT = 2004
        None

    def send(self, dict):
        dict = {"api": dict}
        try:
            sender = self.conn()
            package = pickle.dumps(self.transform(dict), 1)
            size = struct.pack("!L", len(package))
            sender.sendall(size)
            sender.sendall(package)
            return True
        except Exception as e:
            # ~ print(str(e))
            log.error("Could not connect to carbon host " + self.SERVER)
            return False

    def transform(self, dicts):
        tuples = []
        now = int(time.time())
        for k, d in dicts.items():
            if d is False:
                continue
            key = "isard.sysstats." + self.HOSTNAME + "." + k
            for item, v in d.items():
                if type(v) is bool:
                    v = 1 if v is True else 0
                tuples.append((key + "." + item, (now, v)))
        return tuples

    def conn(self):
        s = socket.socket()
        s.settimeout(2)
        try:
            s.connect((self.SERVER, self.PORT))
            return s
        except socket.error as e:
            raise
