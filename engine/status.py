# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8


from time import time, sleep
import threading
import traceback

from .log import *
from .config import CONFIG_DICT, POLLING_INTERVAL_TRANSITIONAL_STATES
from .hyp import hyp
from .functions import state_and_cause_to_str, dict_domain_libvirt_state_to_isard_state
from .db import get_hyp_hostnames_online, get_last_hyp_status, insert_db_hyp_status, get_config_branch
from .db import get_last_domain_status, insert_db_domain_status, get_hyp_hostname_from_id, update_hypervisor_failed_connection
from .db import get_domain_hyp_started_and_status_and_detail, update_domain_hyp_started, exist_domain,get_domains_with_transitional_status
from .db import update_domain_status


from .functions import calcule_cpu_stats, calcule_disk_net_domain_load, get_tid

max_len_fifo_domains = int(CONFIG_DICT['STATS']['max_queue_domains_status'])
max_len_fifo_hyps = int(CONFIG_DICT['STATS']['max_queue_hyps_status'])


class UpdateStatus():
    def __init__(self, id, hostname,port=22,user='root'):
        self.id = id
        self.hostname = hostname
        self.user = user
        self.port = port
        self.hyp_obj = hyp(hostname,user=self.user,port=self.port)

    def update_status_hyps_rethink(self):
        dict_hyp_status = dict()
        before_connect = time()

        if type(self.hyp_obj) is hyp:
            try:
                self.hyp_obj.conn.getLibVersion()
                self.hyp_obj.connected = True

            except:
                log.info(
                    'getLibVersion failed in connection testing, reconnecting to hypervisor {} from status thread'.format(
                        self.hostname))
                self.hyp_obj = hyp(hostname,user=self.user,port=self.port)
                dict_hyp_status['try_open_connection_to_hyp'] = True
                try:
                    self.hyp_obj.conn.getLibVersion()
                    self.hyp_obj.connected = True
                except:
                    log.info('reconnection to hypervisor {} in status thread fail'.format(self.hostname))
                    self.hyp_obj.connected = False
        else:
            log.info('unknown type, not hyp, reconnecting to hypervisor {] from status thread'.format(self.hostname))
            self.hyp_obj = h = self.hyp_obj = hyp(hostname,user=self.user,port=self.port)
            dict_hyp_status['try_open_connection_to_hyp'] = True

        dict_hyp_status['hyp_id'] = self.id
        dict_hyp_status['hostname'] = self.hostname

        if self.hyp_obj.connected:
            before = time()
            self.hyp_obj.get_load()
            self.hyp_obj.get_domains()
            now = time()

            dict_hyp_status['connected'] = True
            dict_hyp_status['when'] = now
            dict_hyp_status['delay_query_load'] = now - before
            dict_hyp_status['delay_from_connect'] = now - before_connect
            dict_hyp_status['load'] = self.hyp_obj.load
            dict_hyp_status['domains'] = self.hyp_obj.domains.keys()

            # hyps status

            dict_last_hyp_status = get_last_hyp_status(self.id)

            if dict_last_hyp_status is not None:
                try:
                    dict_hyp_status['cpu_percent'] = calcule_cpu_stats(dict_last_hyp_status['load']['cpu_load'],
                                                                       dict_hyp_status['load']['cpu_load'])[0]
                except:
                    log.error('error calculating cpu_percent in hyp_id {} '.format(self.id))
            else:
                dict_hyp_status['cpu_percent'] = False

            # domain_status
            for name, status in self.hyp_obj.domain_stats.items():
                dict_domain = dict()
                dict_domain['when'] = now
                dict_domain['name'] = name
                dict_domain['status'] = status

                dict_domain_last = get_last_domain_status(name)

                if dict_domain_last is not None:
                    time_elapsed = dict_domain['when'] - dict_domain_last['when']

                    dict_domain['status']['cpu_usage'] = \
                        (dict_domain['status']['procesed_stats']['cpu_time'] - \
                         dict_domain_last['status']['procesed_stats']['cpu_time']) \
                        / time_elapsed

                    dict_domain['status']['disk_rw'], dict_domain['status']['net_rw'] = \
                        calcule_disk_net_domain_load(time_elapsed,
                                                     dict_domain['status']['procesed_stats'],
                                                     dict_domain_last['status']['procesed_stats'])

                # def threading_enumerate():
                #     # time.sleep(0.5)
                #     e = threading.enumerate()
                #     l = [t._Thread__name for t in e]
                #     l.sort()
                #     for i in l:
                #         log.debug('Thread running: {}'.format(i))
                #     return e
                # #OJO INFO TO DEVELOPER
                # log.debug('%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%')
                # threading_enumerate()
                insert_db_domain_status(dict_domain)

                # INFO TO DEVELOPER, REVISAR SI EL ESTADO NO ES STARTED
                # y tampoco tengo clalro que es lo que pasa
                # falta mirar que pasa si ese dominio no está en la base de datos,
                # también falta terminar de pensar que pasa si aparece como stoppped...
                # if exist_domain(name):
                #     in_db_domain = get_domain_hyp_started_and_status_and_detail(name)
                #     if 'hyp_started' not in in_db_domain.keys():
                #         if dict_domain['status']['state'] ==  'running':
                #             update_domain_hyp_started(domain_id=name,
                #                                       hyp_id=dict_domain['status']['hyp'],
                #                                       detail=dict_domain['status']['state_reason'])
                #
                #     elif dict_domain['status']['hyp'] != in_db_domain['hyp_started']:
                #         ## OJO INFO TO DEVELOPER, NO MODIFICAMOS ESTADO
                #         if dict_domain['status']['state'] ==  'running':
                #             update_domain_hyp_started(domain_id=name,
                #                                       hyp_id=dict_domain['status']['hyp'],
                #                                       detail=dict_domain['status']['state_reason'])
                # self.hyp_obj.disconnect()
        else:
            log.error('#########################################################')
            log.error('hypervisor {} connect fail in status thread'.format(self.hostname))
            dict_hyp_status['connected'] = False
            dict_hyp_status['when'] = now

        insert_db_hyp_status(dict_hyp_status)



        # falta poner como ina8ctivos los dominios que no se encuentren,
        # habrá qur borrar diccionarios?



# class ThreadIsard(threading.Thread):
#     def __init__(self,
#                  group=None,
#                  target=None,
#                  name=None,
#                  args=(),
#                  kwargs=None,
#                  verbose=None):
#         self.target_function = target_function
#         self._args = args
#         self._kwargs = kwargs
#
#     def run(self):
#         self.tid = get_tid()
#         log.info('starting thread: {} (TID {})'.format(self.name,self.tid))
#         try:
#             if self.target_function:
#                 self.target_function(*self._args, **self._kwargs)
#         finally:
#             # Avoid a refcycle if the thread is running a function with
#             # an argument that has a member that points to the thread.
#             del self._target, self._args, self._kwargs


class ThreadBroom(threading.Thread):
    def __init__(self, name, polling_interval):
        threading.Thread.__init__(self)
        self.name = name
        self.polling_interval = polling_interval
        self.stop = False

    def polling(self):
        while self.stop is not True:
            l = get_domains_with_transitional_status()

            list_domains_without_hyp = [d for d in l if 'hyp_started' not in d.keys()]
            list_domains = [d for d in l if 'hyp_started' in d.keys()]
            for d in list_domains_without_hyp:
                log.error('DOMAIN {} WITH STATUS {} without HYPERVISOR'.format(d['id'],d['status']))
                update_domain_status('Unknown', d['id'], detail='starting or stoping status witouth hypervisor')

            hyps_to_try = set([d['hyp_started'] for d in list_domains if d is str])
            hyps_domain_started = {}
            for hyp_id in hyps_to_try:
                try:
                    hostname, port, user = get_hyp_hostname_from_id(hyp_id)
                    if hostname is False:
                        log.error('hyp {} with id has not hostname or is nos in database'.format(hyp_id))
                    else:
                        h = hyp(hostname, user=user, port=port)
                        if h.connected:
                            hyps_domain_started[hyp_id] = {}
                            hyps_domain_started[hyp_id]['hyp'] = h
                            list_domains_from_hyp = h.get_domains()
                            if list_domains_from_hyp is None:
                                list_domains_from_hyp = []
                            hyps_domain_started[hyp_id]['active_domains'] = list_domains_from_hyp
                        else:
                            log.error('HYPERVISOR {} libvirt connection failed')
                        hyps_domain_started[hyp_id] = False
                except Exception as e:
                    log.error('Exception when try to hypervisor {}: {}'.format(hyp_id, e))
                    log.error('Traceback: {}'.format(traceback.format_exc()))

            for d in list_domains_without_hyp:
                domain_id = d['id']
                status = d['status']
                if status == 'Stopping':
                    log.debug('DOMAIN: {} STATUS STOPPING WITHOUTH HYPERVISOR, UNKNOWN REASON'.format(domain_id))
                    update_domain_status('Stopped', domain_id, detail='Stopped by broom thread because has not hypervisor')

            for d in list_domains:
                domain_id = d['id']
                status = d['status']
                hyp_started = d['hyp_started']
                #TODO bug sometimes hyp_started not in hyps_domain_started keys... why?
                if hyp_started in hyps_domain_started.keys() and len(hyp_started) > 0:
                  if hyps_domain_started[hyp_started] is not False:
                    if status == 'Starting':
                        log.debug('DOMAIN: {} STATUS STARTING TO RUN IN HYPERVISOR: {}'.format(domain_id, hyp_started))
                        # try:
                        #     if domain_id in hyps_domain_started[hyp_started]['active_domains']:
                        #         print(domain_id)
                        # except Exception as e:
                        #     log.error(e)
                        if domain_id in hyps_domain_started[hyp_started]['active_domains']:
                            log.debug('DOMAIN: {} ACTIVE IN HYPERVISOR: {}'.format(domain_id, hyp_started))
                            state_libvirt = hyps_domain_started[hyp_started]['hyp'].domains[domain_id].state()
                            state_str, cuase = state_and_cause_to_str(state_libvirt[0], state_libvirt[1])
                            status = dict_domain_libvirt_state_to_isard_state(state_str)
                            log.debug('DOMAIN: {} ACTIVE IN HYPERVISOR: {} WITH STATUS: {}'.format(domain_id, hyp_started, status))
                            update_domain_hyp_started(domain_id,hyp_started)
                        else:
                            log.debug('DOMAIN: {} NOT ACTIVE YET IN HYPERVISOR: {} '.format(domain_id, hyp_started))
                    elif status == 'Stopping':
                        log.debug('DOMAIN: {} STATUS STOPPING IN HYPERVISOR: {}'.format(domain_id, hyp_started))
                        if domain_id not in hyps_domain_started[hyp_started]['active_domains']:
                            update_domain_status('Stopped', domain_id, detail='Stopped by broom thread')
                    else:
                        log.debug('DOMAIN: {} NOT ACTIVE YET IN HYPERVISOR: {} '.format(domain_id, hyp_started))
                else:
                    log.error('hyp_started: {} NOT IN hyps_domain_started keys:'.format(hyp_started))


            interval = 0.0
            while interval < self.polling_interval:
                sleep(0.1)
                interval = interval + 0.1
                if self.stop is True:
                    break

    def run(self):
        self.tid = get_tid()
        log.info('starting thread: {} (TID {})'.format(self.name,self.tid))
        self.polling()

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

    def polling_status(self):

        self.status_obj = UpdateStatus(self.hyp_id, self.hostname,port=self.port,user=self.user)

        while self.stop is not True:
            self.status_obj.update_status_hyps_rethink()
            interval = 0.0
            while interval < self.polling_interval:
                sleep(0.1)
                interval = interval + 0.1
                if self.stop is True:
                    break


    def run(self):
        self.tid = get_tid()
        log.info('starting thread: {} (TID {})'.format(self.name,self.tid))
        self.polling_status()

def launch_thread_status(hyp_id,polling_interval):

    t = ThreadStatus(name='status_'+hyp_id,
                        hyp_id=hyp_id,
                        polling_interval=polling_interval)
    t.daemon = True
    t.start()
    return t

def launch_thread_broom():

    t = ThreadBroom(name='broom', polling_interval=POLLING_INTERVAL_TRANSITIONAL_STATES)
    t.daemon = True
    t.start()
    return t




# domain_status=dict()
# hyp_status=dict()
# hyp_info=dict()
#hyps_objects = {}
#stop_polling_status = {}

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
