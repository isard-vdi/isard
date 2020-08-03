import requests
from pprint import pprint
#!/usr/bin/python

import libvirt
import sys, os
from time import sleep
from lib.carbon import Carbon
c=Carbon()
from pprint import pprint
        
class Domains():
    def __init__(self,interval=5, uri='qemu+unix:///system?socket=/var/run/libvirt/libvirt-sock-ro'):
        self.uri=uri
        self.interval = interval
        
    def stats(self):
        try:
            while True:
                #Cambiar el diccionario con lo que queramos pillar por self.conn
                doms=self.conn.getAllDomainStats(flags=libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE)
                d={'started':str(len(self.conn.listDomainsID()))}
                c.send2carbon({"domains":d})
                # ~ newdoms={}                
                # ~ for d in doms:
                    # ~ newdoms['stats.'+d[0].name()+'.balloon']={'current':d[1]['balloon.current'],
                                                                # ~ 'last-update':d[1]['balloon.last-update'],
                                                                # ~ 'maximum':d[1]['balloon.maximum'],
                                                                # ~ 'rss':d[1]['balloon.rss']}
                # ~ pprint(newdoms)
                # ~ c.send2carbon({"domains":newdoms})
                sleep(self.interval)
        except Exception as e:
            print(e)
            return False
            
    def check(self):
        try:
            self.conn=libvirt.openReadOnly(self.uri)
            if self.conn == None:
                print('Failed to open connection to the hypervisor')
                return False
            return True
        except Exception as e:
            print(e)
            return False

 
    def get_domain_stats(self):
        doms = conn.getAllDomainStats(flags=libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE)
        mydoms = {}
        for d in doms:
            mydoms[d[0].name()+'.']















