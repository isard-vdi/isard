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
from engine.services.db.config import get_config

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
        self.restart_send_config = False
        self.active = False
        self.send_to_grafana_interval = SEND_TO_GRAFANA_INTERVAL
        self.send_static_values_interval = SEND_STATIC_VALUES_INTERVAL
        self.host_grafana = False
        self.port = False



    def get_hostname_grafana(self):
        try:
            dict_grafana = get_config()['engine']['grafana']

            if dict_grafana["active"] is not True:
                self.active = False
                return False
            else:
                self.host_grafana = dict_grafana["hostname"]
                self.port = int(dict_grafana["carbon_port"])
                self.send_static_values_interval = int(dict_grafana.get('send_static_values_interval',
                                                                    SEND_STATIC_VALUES_INTERVAL))
                self.send_to_grafana_interval = int(dict_grafana.get('interval',
                                                                 SEND_TO_GRAFANA_INTERVAL))
                self.active = True
                return True
        except Exception as e:
            logs.main.error(f'grafana config error: {e}')
            self.active = False
            return False

    def send(self,d):
        send_dict_to_grafana(d, self.host_grafana, self.port)

    def run(self):
        self.tid = get_tid()
        logs.main.info('starting thread: {} (TID {})'.format(self.name, self.tid))

        #get hostname grafana config
        self.get_hostname_grafana()

        hyps_online = []

        elapsed = self.send_static_values_interval
        while self.stop is False:
            sleep(self.send_to_grafana_interval)
            elapsed += self.send_to_grafana_interval

            if self.restart_send_config is True:
                self.restart_send_config = False
                self.get_hostname_grafana()

            if self.active is True:
                for i,id_hyp in enumerate(self.t_status.keys()):
                    try:
                        if self.t_status[id_hyp].status_obj.hyp_obj.connected is True:
                            if id_hyp not in hyps_online:
                                hyps_online.append(id_hyp)
                        check_hyp = True
                    except:
                        logs.main.error(f'hypervisor {id_hyp} problem checking if is connected')
                        check_hyp = False

                if len(hyps_online) > 0 and check_hyp is True:
                    #send static values of hypervisors
                    if elapsed >= self.send_static_values_interval:
                        d_hyps_info = dict()
                        for i, id_hyp in enumerate(hyps_online):
                            d_hyps_info[f'hyp-info-{i}'] = self.t_status[id_hyp].status_obj.hyp_obj.info
                        # ~ self.send(d_hyps_info)
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
                                dict_to_send[f'hypers.'+id_hyp] = {'stats':stats_hyp_now,'info':d_hyps_info['hyp-info-'+str(i)],'domains':{}}
                                stats_domains_now = self.t_status[id_hyp].status_obj.hyp_obj.stats_domains_now
                            # ~ for id_domain,d_stats in stats_domains_now.items():
                            # ~ if len(stats_hyp_now) > 0:
                                # ~ for id_domain,d_stats in stats_domains_now.items():
                                    # ~ dict_to_send[f'domain-stats-{j}'] = {'domain-id':{id_domain:1},'last': d_stats,}
                                dict_to_send[f'hypers.'+id_hyp]['domains']=stats_domains_now #{x:0 for x in stats_domains_now}
                                    # ~ print(stats_domains_now)
                                    # ~ j+=1

                    if len(dict_to_send) > 0:
                        self.send(dict_to_send)




