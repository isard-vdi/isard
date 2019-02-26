# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8

import threading
import traceback
from time import time, sleep

from engine.config import POLLING_INTERVAL_TRANSITIONAL_STATES
from engine.models.hyp import hyp
from engine.services.db import update_domain_hyp_started, get_domains_with_transitional_status, \
    update_domain_status, get_hyp_hostname_from_id
from engine.services.db.domains_status import get_last_domain_status, insert_db_domain_status
from engine.services.db.hypervisors_status import get_last_hyp_status, insert_db_hyp_status
from engine.services.lib.functions import calcule_cpu_hyp_stats, calcule_disk_net_domain_load, get_tid
from engine.services.lib.functions import state_and_cause_to_str, dict_domain_libvirt_state_to_isard_state
from engine.services.log import logs


class ThreadBroom(threading.Thread):
    def __init__(self, name, polling_interval, manager):
        threading.Thread.__init__(self)
        self.manager = manager
        self.name = name
        self.polling_interval = polling_interval
        self.stop = False

    def polling(self):
        while self.stop is not True:

            interval = 0.0
            while interval < self.polling_interval:
                sleep(0.1)
                interval += 0.1
                if self.stop is True:
                    break
            if self.manager.check_actions_domains_enabled() is False:
                continue


            l = get_domains_with_transitional_status()

            list_domains_without_hyp = [d for d in l if 'hyp_started' not in d.keys()]
            list_domains = [d for d in l if 'hyp_started' in d.keys()]
            for d in list_domains_without_hyp:
                logs.broom.error('DOMAIN {} WITH STATUS {} without HYPERVISOR'.format(d['id'], d['status']))
                update_domain_status('Unknown', d['id'], detail='starting or stoping status witouth hypervisor')

            hyps_to_try = set([d['hyp_started'] for d in list_domains if d is str])
            hyps_domain_started = {}
            for hyp_id in hyps_to_try:
                try:
                    hostname, port, user = get_hyp_hostname_from_id(hyp_id)
                    if hostname is False:
                        logs.broom.error('hyp {} with id has not hostname or is nos in database'.format(hyp_id))
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
                            logs.broom.error('HYPERVISOR {} libvirt connection failed')
                        hyps_domain_started[hyp_id] = False
                except Exception as e:
                    logs.broom.error('Exception when try to hypervisor {}: {}'.format(hyp_id, e))
                    logs.broom.error('Traceback: {}'.format(traceback.format_exc()))

            for d in list_domains_without_hyp:
                domain_id = d['id']
                status = d['status']
                if status == 'Stopping':
                    logs.broom.debug('DOMAIN: {} STATUS STOPPING WITHOUTH HYPERVISOR, UNKNOWN REASON'.format(domain_id))
                    update_domain_status('Stopped', domain_id,
                                         detail='Stopped by broom thread because has not hypervisor')


            for d in list_domains:
                domain_id = d['id']
                status = d['status']
                hyp_started = d['hyp_started']
                if type(hyp_started) is bool:
                    continue
                if len(hyp_started) == 0:
                    continue
                # TODO bug sometimes hyp_started not in hyps_domain_started keys... why?
                if hyp_started in hyps_domain_started.keys() and len(hyp_started) > 0:
                    if hyps_domain_started[hyp_started] is not False:
                        if status == 'Starting':
                            logs.broom.debug(
                                    'DOMAIN: {} STATUS STARTING TO RUN IN HYPERVISOR: {}'.format(domain_id,
                                                                                                 hyp_started))
                            # try:
                            #     if domain_id in hyps_domain_started[hyp_started]['active_domains']:
                            #         print(domain_id)
                            # except Exception as e:
                            #     logs.broom.error(e)
                            if domain_id in hyps_domain_started[hyp_started]['active_domains']:
                                logs.broom.debug('DOMAIN: {} ACTIVE IN HYPERVISOR: {}'.format(domain_id, hyp_started))
                                state_libvirt = hyps_domain_started[hyp_started]['hyp'].domains[domain_id].state()
                                state_str, cause = state_and_cause_to_str(state_libvirt[0], state_libvirt[1])
                                status = dict_domain_libvirt_state_to_isard_state(state_str)
                                logs.broom.debug(
                                        'DOMAIN: {} ACTIVE IN HYPERVISOR: {} WITH STATUS: {}'.format(domain_id,
                                                                                                     hyp_started,
                                                                                                     status))
                                update_domain_hyp_started(domain_id, hyp_started)
                            else:
                                logs.broom.debug('DOMAIN: {} NOT ACTIVE YET IN HYPERVISOR: {} '.format(domain_id, hyp_started))
                        elif status == 'Stopping':
                            logs.broom.debug('DOMAIN: {} STATUS STOPPING IN HYPERVISOR: {}'.format(domain_id, hyp_started))
                            if domain_id not in hyps_domain_started[hyp_started]['active_domains']:
                                update_domain_status('Stopped', domain_id, detail='Stopped by broom thread')
                        else:
                            logs.broom.debug('DOMAIN: {} NOT ACTIVE YET IN HYPERVISOR: {} '.format(domain_id, hyp_started))
                else:
                    if len(hyps_domain_started) > 0:
                        logs.broom.error('hyp_started: {} NOT IN hyps_domain_started keys:'.format(hyp_started))



    def run(self):
        self.tid = get_tid()
        logs.broom.info('starting thread: {} (TID {})'.format(self.name, self.tid))
        self.polling()

def launch_thread_broom(manager):
    t = ThreadBroom(name='broom', polling_interval=POLLING_INTERVAL_TRANSITIONAL_STATES,manager=manager)
    t.daemon = True
    t.start()
    return t
