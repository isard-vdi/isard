import collections
import os
import re
import socket
import time
from time import sleep

import rethinkdb as r
from lib.carbon import Carbon
from lib.flask_rethink import RethinkDB

import docker

c = Carbon()
dbconn = RethinkDB()

from lib.helpers import cu, execute

try:
    ip_squid = socket.gethostbyname("isard-squid")
except:
    ip_squid = None
try:
    ip_websockify = socket.gethostbyname("isard-websockify")
except:
    ip_websockify = None


class Hypervisors:
    def __init__(self, interval=5):
        self.interval = interval
        self.client = None

    def check(self):
        ## We should check if we can c
        try:
            sleep(10)
            self.client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
            self.container_hyp = self.client.containers.get("isard-hypervisor")
            return True
        except:
            return False
        # ~ return True if os.path.isfile('/var/run/docker.sock') else False

    def stats(self):
        while True:
            cmd_ss = 'ss -t state established -p "( sport > 5900 )"'
            # ~ cmd_ss = 'ss -t state established -p "( sport > 5900 )" |grep kvm'
            cmd_virsh = "virsh list"
            # ~ cmd_virsh = 'virsh list |grep -i running|wc -l'

            raw = self.container_hyp.exec_run(cmd_virsh)
            if raw[0] != 0:
                print("Error in command: " + cmd_virsh)
                break
            try:
                num_desktops = int(len(raw[1].decode("utf-8").split("\n")) - 4)
            except:
                num_desktops = 0

            raw = self.container_hyp.exec_run(cmd_ss)
            if raw[0] != 0:
                print("Error in command: " + cmd_ss)
                break
            # ~ print(raw[1].decode("utf-8"))

            data = raw[1].decode("utf-8").splitlines()
            data.pop(0)
            out_ss = "\n".join(data)
            # print(out_ss)
            port_ip = [a.split(":")[1] for a in out_ss.splitlines()]
            resum_connections = collections.Counter(
                [i.split()[1] for i in set(port_ip)]
            )

            viewers_spice = resum_connections.get(ip_squid, 0)
            viewers_websockify = resum_connections.get(ip_websockify, 0)
            total_viewers = viewers_spice + viewers_websockify

            # ~ print({'domains':{'started':num_desktops},
            # ~ 'domains.viewers':{'total':total_viewers, 'spice-client':viewers_spice,'vnc-html5':viewers_websockify}})

            ########### GRAFANA
            c.send2carbon(
                {
                    "domains": {"started": num_desktops},
                    "domains.viewers": {
                        "total": total_viewers,
                        "spice-client": viewers_spice,
                        "vnc-html5": viewers_websockify,
                    },
                }
            )

            sleep(self.interval)
