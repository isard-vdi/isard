import time, os
#import subprocess,os
import socket
import pickle
#import platform
import struct 
#import re

from threading import Thread

# HOSTNAME=os.environ['HOSTNAME']
# SERVER=os.environ['STATS_HOST']
# PORT=2004

class Carbon():
    def __init__(self,hostname=None,server=None,port=2004):
        if hostname is None:
            self.hostname = os.environ['DOMAIN']
        else:
            self.hostname = hostname
        if server is None:
            self.server = os.environ['']
        self.port = port
        
    def send2carbon(self,dict):
        self.send(self.transform(dict))
        
    def transform(self, dicts):
        tuples = ([])
        now = int(time.time())
        for k,d in dicts.items():
            if d is False: continue
            key='isard.sysstats.'+ self.hostname +'.'+k
            for item,v in d.items():
                if type(v) is bool:
                    v = 1 if v is True else 0
                tuples.append((key+'.'+item, (now, v)))
        return tuples

    def conn(self):
        s = socket.socket()
        s.settimeout(3)
        try:
            s.connect((self.server, self.port))
            return s
        except socket.error as e:
            return False

    def send(self, tuples):
        sender = self.conn()
        if sender is not False:
            package = pickle.dumps(tuples, 1)
            size = struct.pack('!L', len(package))
            sender.sendall(size)
            sender.sendall(package)
            return True
        else:
            print("Could not connect to carbon host")
            return False
