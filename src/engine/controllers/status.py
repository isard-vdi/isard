# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8


import threading
import traceback
from time import time, sleep
from collections import deque


from engine.models.hyp import hyp
from engine.services.db import update_domain_hyp_started, get_domains_with_transitional_status, \
    update_domain_status, get_hyp_hostname_from_id
from engine.services.db.domains_status import get_last_domain_status, insert_db_domain_status
from engine.services.db.hypervisors_status import get_last_hyp_status, insert_db_hyp_status
from engine.services.lib.functions import calcule_cpu_hyp_stats, calcule_disk_net_domain_load, get_tid
from engine.services.lib.functions import state_and_cause_to_str, dict_domain_libvirt_state_to_isard_state
from engine.services.log import *

max_len_fifo_domains = int(CONFIG_DICT['STATS']['max_queue_domains_status'])
max_len_fifo_hyps = int(CONFIG_DICT['STATS']['max_queue_hyps_status'])

max_len_queue_previous_hyp_stats = 10
max_len_queue_previous_domain_stats = 10


class UpdateStatus:
    def __init__(self, id_hyp, hostname, polling_interval, rate_allowed_diff_between_samples=2.5, port=22, user='root'):
        self.hyp_id = id_hyp
        self.polling_interval = polling_interval
        self.rate_allowed_diff_between_samples = rate_allowed_diff_between_samples
        self.hostname = hostname
        self.user = user
        self.port = port
        self.hyp_obj = hyp(hostname, user=self.user, port=self.port)
        self.fifo_recent_hyp_stats = deque([], maxlen=max_len_queue_previous_hyp_stats)
        self.recent_domains_stats = {}

        hyp_stats = {

        }

    def try_connect_hyp(self):
        if type(self.hyp_obj) is hyp:
            try:
                self.hyp_obj.conn.getLibVersion()
                self.hyp_obj.connected = True

            except:
                log.info('getLibVersion failed in connection testing, reconnecting to hypervisor {} from status thread'
                         .format(self.hostname))
                try:
                    self.hyp_obj = hyp(self.hostname, user=self.user, port=self.port)

                    self.hyp_obj.conn.getLibVersion()
                    self.hyp_obj.connected = True
                    return True
                except:
                    log.info('reconnection to hypervisor {} in status thread fail'.format(self.hostname))
                    self.hyp_obj.connected = False
                    return False
        else:
            log.info('unknown type, not hyp, reconnecting to hypervisor {} from status thread'.format(self.hostname))
            try:
                self.hyp_obj = hyp(self.hostname, user=self.user, port=self.port)
                self.hyp_obj.conn.getLibVersion()
                self.hyp_obj.connected = True
                return True
            except:
                log.info('reconnection to hypervisor {} in status thread fail'.format(self.hostname))
                self.hyp_obj.connected = False
                return False

    def update_status_hyps_rethink(self):
        dict_hyp_status = dict()
        selected_hyp_values = dict()
        before_connect = time()

        if self.try_connect_hyp() is False:
            log.error('#########################################################')
            log.error('hypervisor {} connect fail in status thread'.format(self.hostname))
            dict_hyp_status['connected'] = False
            dict_hyp_status['when'] = before_connect
            return False
        else:
            dict_hyp_status['connected'] = True

            h = self.hyp_obj

            dict_hyp_status['hyp_id'] = self.hyp_id
            dict_hyp_status['hostname'] = self.hostname

        if self.hyp_obj.connected:
            before = time()
            self.hyp_obj.get_load()




class ThreadStatus(threading.Thread):
    def __init__(self,
                 name,
                 hyp_id,
                 polling_interval=10,
                 ):
        threading.Thread.__init__(self)
        self.name = name
        self.stop = False
        self.hyp_id = hyp_id
        self.hostname, self.port, self.user = get_hyp_hostname_from_id(hyp_id)
        self.polling_interval = polling_interval
        self.status_obj = None

    def polling_status(self):

        self.status_obj = UpdateStatus(self.hyp_id, self.hostname, polling_interval=self.polling_interval,
                                       port=self.port, user=self.user)

        while self.stop is not True:
            self.status_obj.update_status_hyps_rethink()
            interval = 0.0
            while interval < self.polling_interval:
                sleep(0.1)
                interval += 0.1
                if self.stop is True:
                    break

    def run(self):
        self.tid = get_tid()
        log.info('starting thread: {} (TID {})'.format(self.name, self.tid))
        self.polling_status()


def launch_thread_status(hyp_id, polling_interval):
    t = ThreadStatus(name='status_' + hyp_id,
                     hyp_id=hyp_id,
                     polling_interval=polling_interval)
    t.daemon = True
    t.start()
    return t




# domain_status=dict()
# hyp_status=dict()
# hyp_info=dict()
# hyps_objects = {}
# stop_polling_status = {}

# def polling_status(id,hostname,polling_interval,stop_polling_status=None):
#     get_config_branch
#     stop_polling_status[id]=False
#
#     status_obj = UpdateStatus(id,hostname)
#
#     while stop_polling_status[id] is not True:
#         status_obj.update_status_hyps_rethink()
#         interval = 0.0
#         while interval < polling_interval:
#             sleep(0.1)
#             interval = interval + 0.1
#             if stop_polling_status[id] is True:
#                 break


# def polling_status(id, hostname, dict_threads_events):
#     stop_polling_status[id] = False
#
#     status_obj = UpdateStatus(id, hostname)
#     update_hypervisor_failed_connection(id,status_obj.hyp_obj.fail_connected_reason)
#     if status_obj.hyp_obj.connected is False:
#         log.error('hypervisor {} failed when connecting and thread status not started'.format(id))
#
#
#     CONFIG_STATS = get_config_branch('stats')
#     polling_interval = float(CONFIG_STATS['POLLING_INTERVAL'])
#
#     e = dict_threads_events['status'][id]
#     global_kill = dict_threads_events['global']['kill']
#
#     while not (e.isSet() or global_kill.isSet()):
#         log.debug('wait_for_event_timeout starting')
#         event_is_set = e.wait(polling_interval)
#
#         if event_is_set:
#             log.debug('event set: %s', event_is_set)
#             break
#         else:
#             log.debug('doing other things')
#             status_obj.update_status_hyps_rethink()
#
#     log.debug('exit for status thread in hypervisor {}'.format(id))
#
#
# def thread_status_hyp(id, hostname, dict_threads_events):
#     if id not in dict_threads_events['status'].keys():
#         dict_threads_events['status'][id] = threading.Event()
#     dict_threads_events['status'][id].clear()
#     thread_status = threading.Thread(name='status_hyp_{}'.format(id),
#                                      target=polling_status,
#                                      kwargs={'id'         : id,
#                                              'hostname'   : hostname,
#                                              'dict_threads_events': dict_threads_events})
#     thread_status.daemon = True
#     thread_status.start()
#     return thread_status



#
# class thread_status_hyp(threading.Thread):
#     global hyp_stats_interval
#     thread_status = threading.Thread(name='status_hyp_{}'.format(id),
#                                      target=polling_status,
#                                      kwargs={'id': id,
#                                              'hostname': hostname,
#                                              'polling_interval': hyp_stats_interval})
#     thread_status.daemon = True
#     thread_status.start()
#     return thread_status
#


#
# class RethinkHypEvent(object):
#
#     def __init__(self):
#         r.connect( "localhost", 28015, db='isard').repl()
#         self.rdb = r.db('isard')
#         None
#
#     def insert_event_in_db(self,dict_event):
#         print dict_event
#         try:
#             r.connect( "localhost", 28015, db='isard').repl()
#             self.rdb = r.db('isard')
#             r.table('hypervisors_events').insert(dict_event).run()
#         except Exception as e:
#             log.error('rethink insert hyp event fail: {}'.format(e))
#


# def update_spice_port(domain_id,hyp_id):
#     pass

# def update_hyp_status(hostname):
#     h = hyp(hostname)
#     if h.connected:
#         h.get_load()
#         h.get_domains()
#
#         d_hyp['connected'] = True
#         d_hyp['when'] = time()
#         d_hyp['load'] = h.load
#         d_hyp['domains'] = h.domains.keys()
#
#         hyp_status[hostname].append(d_hyp)
#
#         h.disconnect()
#     else:
#         d['connected'] = False

#
#
# def initialize_status_hyps(list_hyps):
#     for hostname in list_hyps:
#         hyp_status[hostname] = deque(maxlen=max_len_fifo_hyps)
#         d_hyp = dict()
#         h = hyp(hostname)
#         if h.connected:
#             h.get_hyp_info()
#             hyp_info[hostname]=h.info
#
#             h.disconnect()
#             log.debug('hypervisor {} initialize status dictionaries with fifo lists'.format(hostname))
#         else:
#             d_hyp['connected'] = False
#
#     update_status_hyps(list_hyps)
#
# def update_status_hyps(list_hyps):
#     for hostname in list_hyps:
#         d_hyp = dict()
#         before_connect=time()
#         h = hyp(hostname)
#         if h.connected:
#             before=time()
#             h.get_load()
#             h.get_domains()
#             now=time()
#             d_hyp['connected'] = True
#             d_hyp['when'] = now
#             d_hyp['delay_query_load'] = now - before
#             d_hyp['delay_from_connect'] = now - before_connect
#             d_hyp['load'] = h.load
#             d_hyp['domains'] = h.domains.keys()
#
#             #hyps status
#             hyp_status[hostname].append(d_hyp)
#             if len(hyp_status[hostname]) > 1:
#                 cpu_percent = calcule_cpu_stats(hyp_status[hostname][-2]['load']['cpu_load'],
#                                                 hyp_status[hostname][-1]['load']['cpu_load'])[0]
#
#                 hyp_status[hostname][-1]['cpu_percent'] = cpu_percent
#
#             #domain_status
#             for name,status in h.domain_stats.items():
#                 if name not in domain_status.keys():
#                     domain_status[name] = deque(maxlen=max_len_fifo_domains)
#                 d_domain=dict()
#                 d_domain['when'] = now
#                 d_domain['status'] = status
#                 domain_status[name].append(d_domain)
#
#                 if len(domain_status[name]) > 1:
#                     time_elapsed = domain_status[name][-1]['when'] - domain_status[name][-2]['when']
#
#                     domain_status[name][-1]['status']['cpu_usage'] = \
#                                 (domain_status[name][-1]['status']['procesed_stats']['cpu_time'] - \
#                                  domain_status[name][-2]['status']['procesed_stats']['cpu_time']) \
#                                  / time_elapsed
#
#                     domain_status[name][-1]['status']['disk_rw'], domain_status[name][-1]['status']['net_rw'] = \
#                         calcule_disk_net_domain_load(time_elapsed,
#                                              domain_status[name][-1]['status']['procesed_stats'],
#                                              domain_status[name][-2]['status']['procesed_stats'])
#
#         h.disconnect()

#
# def main():
#     dict_hyps_online = get_hyp_hostnames_online()
#     launch_threads_status_hyp()
#
#
# if __name__ == "__main__":
#     main()
