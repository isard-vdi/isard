# Copyright 2019 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3
# coding=utf-8
import threading
from time import sleep

from engine.services.log import logs
from engine.services.lib.functions import get_tid, flatten_dict
from engine.services.db import get_hyp_hostnames_online
from engine.services.lib.grafana import send_dict_to_grafana

SEND_TO_GRAFANA_INTERVAL = 5
SEND_STATIC_VALUES_INTERVAL = 30

def launch_grafana_thread(d_threads_status):
    t = GrafanaThread(name='grafana',
                      d_threads_status=d_threads_status)
    t.daemon = True
    t.start()
    return t

class GrafanaThread(threading.Thread):
    def __init__(self, name,d_threads_status):
        threading.Thread.__init__(self)
        self.name = name
        self.stop = False
        self.t_status = d_threads_status


    def get_hostname_grafana(self):
        dict_grafana = {
            "active": True,
            "carbon_port": 2004,
            "hostname": "isard-grafana",
            "interval": 5,
        }
        if dict_grafana["active"] is not True:
            return False
        else:
            self.host_grafana = dict_grafana["hostname"]
            self.port = dict_grafana["carbon_port"]
            self.interval = dict_grafana["interval"]
            return True

    def send(self,d):
        send_dict_to_grafana(d, self.host_grafana, self.port)

    def run(self):
        self.tid = get_tid()
        logs.main.info('starting thread: {} (TID {})'.format(self.name, self.tid))

        #get hostname grafana config
        if self.get_hostname_grafana() is not True:
            return False

        hyps_online = []

        elapsed = SEND_STATIC_VALUES_INTERVAL
        while self.stop is False:
            sleep(SEND_TO_GRAFANA_INTERVAL)
            elapsed += SEND_TO_GRAFANA_INTERVAL


            for i,id_hyp in enumerate(self.t_status.keys()):
                try:
                    if self.t_status[id_hyp].status_obj.hyp_obj.connected is True:
                        if id_hyp not in hyps_online:
                            hyps_online.append(id_hyp)
                except:
                    logs.main.error(f'hypervisor {id_hyp} problem checking if is connected')

            #send static values of hypervisors
            if elapsed >= SEND_STATIC_VALUES_INTERVAL:
                d_hyps_info = dict()
                for i, id_hyp in enumerate(hyps_online):
                    d_hyps_info[f'hyp-info-{i}'] = self.t_status[id_hyp].status_obj.hyp_obj.info

                self.send(d_hyps_info)
                elapsed = 0

            #send stats
            dict_to_send = dict()
            j=0
            for i, id_hyp in enumerate(hyps_online):
                if id_hyp in self.t_status.keys():
                    #stats_hyp = self.t_status[id_hyp].status_obj.hyp_obj.stats_hyp
                    stats_hyp_now = self.t_status[id_hyp].status_obj.hyp_obj.stats_hyp_now
                    #stats_domains = self.t_status[id_hyp].status_obj.hyp_obj.stats_domains
                    if len(stats_hyp_now) > 0:
                        dict_to_send[f'hyp-stats-{i}'] = {'hyp-id':{id_hyp:1},'last': stats_hyp_now}
                    stats_domains_now = self.t_status[id_hyp].status_obj.hyp_obj.stats_domains_now
                    if len(stats_hyp_now) > 0:
                        for id_domain,d_stats in stats_domains_now.items():
                            dict_to_send[f'domain-stats-{j}'] = {'domain-id':{id_domain:1},'last': d_stats,}
                            j+=1
            if len(dict_to_send) > 0:
                self.send(dict_to_send)




