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

def launch_grafana_thread(d_threads_status,manager_hypervisor):
    t = GrafanaThread(name='grafana',
                      d_threads_status=d_threads_status,
                      manager_hypervisor=manager_hypervisor)
    t.daemon = True
    t.start()
    return t

class GrafanaThread(threading.Thread):
    def __init__(self, name,d_threads_status,manager_hypervisor):
        threading.Thread.__init__(self)
        self.name = name
        self.stop = False
        self.t_status = d_threads_status
        self.m = manager_hypervisor
        self.restart_send_config = False
        self.active = False
        self.send_to_grafana_interval = SEND_TO_GRAFANA_INTERVAL
        self.send_static_values_interval = SEND_STATIC_VALUES_INTERVAL
        self.host_grafana = False
        self.port = False

    def engine_info_to_grafana(self):
        d_engine={}
        d_to_grafana = {}
        d_to_grafana['is_alive'] = False
        try:
            if self.m.t_background is not None:
                try:
                    self.m.t_background.is_alive()
                except AttributeError:
                    d_engine['background_is_alive'] = False
                    return d_engine

                if self.m.t_background.is_alive():

                    d_engine['is_alive'] = True

                    d_engine['background_is_alive'] = True
                    d_engine[
                        'event_thread_is_alive'] = self.m.t_events.is_alive() if self.m.t_events is not None else False
                    d_engine['broom_thread_is_alive'] = self.m.t_broom.is_alive() if self.m.t_broom is not None else False
                    d_engine['download_changes_thread_is_alive'] = self.m.t_downloads_changes.is_alive() \
                        if self.m.t_downloads_changes is not None else False

                    d_engine['changes_hyps_thread_is_alive'] = self.m.t_changes_hyps.is_alive() \
                        if self.m.t_changes_hyps is not None else False
                    d_engine[
                        'changes_domains_thread_is_alive'] = self.m.t_changes_domains.is_alive() if self.m.t_changes_domains is not None else False
                    d_engine['working_threads'] = list(self.m.t_workers.keys())
                    d_engine['status_threads'] = list(self.m.t_status.keys())
                    d_engine['disk_operations_threads'] = list(self.m.t_disk_operations.keys())
                    d_engine['long_operations_threads'] = list(self.m.t_long_operations.keys())

                    d_engine['alive_threads'] = dict()
                    d_engine['alive_threads']['working_threads'] = {name: t.is_alive() for name, t in
                                                                    self.m.t_workers.items()}
                    d_engine['alive_threads']['status_threads'] = {name: t.is_alive() for name, t in
                                                                   self.m.t_status.items()}
                    d_engine['alive_threads']['disk_operations_threads'] = {name: t.is_alive() for name, t in
                                                                            self.m.t_disk_operations.items()}
                    d_engine['alive_threads']['long_operations_threads'] = {name: t.is_alive() for name, t in
                                                                            self.m.t_long_operations.items()}

                    d_engine['queue_size_working_threads'] = {k: q.qsize() for k, q in self.m.q.workers.items()}
                    d_engine['queue_disk_operations_threads'] = {k: q.qsize() for k, q in
                                                                 self.m.q_disk_operations.items()}

                else:
                    d_engine['is_alive'] = False
            else:
                d_engine['is_alive'] = False

            if d_engine['is_alive'] is True:
                d_to_grafana['threads'] = {}
                d_to_grafana['queues'] = {}
                d_to_grafana['hypervisors'] = {}

                d_to_grafana['threads']['alive_working_threads'] = len(d_engine['alive_threads']['working_threads'])
                d_to_grafana['threads']['alive_status_threads'] = len(d_engine['alive_threads']['status_threads'])
                d_to_grafana['threads']['alive_disk_operations_threads'] = len(d_engine['alive_threads']['disk_operations_threads'])
                d_to_grafana['threads']['alive_long_operations_threads'] = len(d_engine['alive_threads']['long_operations_threads'])
                d_to_grafana['threads']['background_is_alive']              = 1 if d_engine['background_is_alive']              is True else 0
                d_to_grafana['threads']['broom_thread_is_alive']            = 1 if d_engine['broom_thread_is_alive']            is True else 0
                d_to_grafana['threads']['changes_domains_thread_is_alive']  = 1 if d_engine['changes_domains_thread_is_alive']  is True else 0
                d_to_grafana['threads']['changes_hyps_thread_is_alive']     = 1 if d_engine['changes_hyps_thread_is_alive']     is True else 0
                d_to_grafana['threads']['download_changes_thread_is_alive'] = 1 if d_engine['download_changes_thread_is_alive'] is True else 0
                d_to_grafana['threads']['event_thread_is_alive']            = 1 if d_engine['event_thread_is_alive']            is True else 0
                d_to_grafana['threads']['total_threads']            = sum(d_to_grafana['threads'].values())

                d_to_grafana['queues'] ['queue_size_working_threads']       = sum(d_engine['queue_size_working_threads'].values())
                d_to_grafana['queues'] ['queue_disk_operations_threads']    = sum(d_engine['queue_disk_operations_threads'].values())


                d_to_grafana['hypervisors']['disk_operations_threads'] = d_engine['disk_operations_threads']
                d_to_grafana['hypervisors']['long_operations_threads'] = d_engine['long_operations_threads']
                d_to_grafana['hypervisors']['queue_disk_operations_threads'] = d_engine['queue_disk_operations_threads']
                d_to_grafana['hypervisors']['queue_size_working_threads'] = d_engine['queue_size_working_threads']
                d_to_grafana['hypervisors']['status_threads'] = d_engine['status_threads']
                d_to_grafana['hypervisors']['working_threads'] = d_engine['working_threads']

            d_to_grafana['is_alive'] = d_engine['is_alive']
            e = threading.enumerate()
            d_to_grafana['python_threads'] = len(e)
            for t in e:
                if hasattr(t, 'tid'):  # only available on Unix
                    print('Thread running (TID: {}): {}'.format(t.tid, t.name))
                else:
                    print('Thread running: {}'.format(t.name))
            return d_to_grafana

        except AttributeError:
            d_to_grafana['is_alive'] = False
            print('ERROR ----- ENGINE IS DEATH')
            return d_to_grafana

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

                dict_to_send = dict()
                if len(hyps_online) > 0 and check_hyp is True:
                    #send static values of hypervisors
                    if elapsed >= self.send_static_values_interval:
                        d_hyps_info = dict()
                        for i, id_hyp in enumerate(hyps_online):
                            d_hyps_info[f'hyp-info-{i}'] = self.t_status[id_hyp].status_obj.hyp_obj.info
                        # ~ self.send(d_hyps_info)
                        elapsed = 0

                    #send stats
                    j=0
                    for i, id_hyp in enumerate(hyps_online):
                        if id_hyp in self.t_status.keys():
                            stats_hyp_now = self.t_status[id_hyp].status_obj.hyp_obj.stats_hyp_now
                            if len(stats_hyp_now) > 0:
                                dict_to_send[f'hypers.'+id_hyp] = {'stats':stats_hyp_now,'info':d_hyps_info['hyp-info-'+str(i)],'domains':{}}

                                stats_domains_now = self.t_status[id_hyp].status_obj.hyp_obj.stats_domains_now
                                dict_to_send[f'hypers.'+id_hyp]['domains']=stats_domains_now #{x:0 for x in stats_domains_now}
                dict_to_send['engine'] = self.engine_info_to_grafana()
                self.send(dict_to_send)




