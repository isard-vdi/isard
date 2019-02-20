# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3
# coding=utf-8

import queue
import threading
import time

from time import sleep

from libvirt import VIR_DOMAIN_START_PAUSED, libvirtError

from engine.models.hyp import hyp
from engine.services.db import get_hyp_hostname_from_id, update_db_hyp_info, update_domain_status, update_hyp_status, \
    update_domains_started_in_hyp_to_unknown, update_table_field, get_engine
from engine.services.lib.functions import get_tid, engine_restart
from engine.services.log import logs
from engine.services.threads.threads import TIMEOUT_QUEUES, launch_action_disk, RETRIES_HYP_IS_ALIVE, \
    TIMEOUT_BETWEEN_RETRIES_HYP_IS_ALIVE, launch_delete_media, launch_killall_curl
from engine.models.domain_xml import XML_SNIPPET_CDROM, XML_SNIPPET_DISK_VIRTIO, XML_SNIPPET_DISK_CUSTOM

class HypWorkerThread(threading.Thread):
    def __init__(self, name, hyp_id, queue_actions, queue_master=None):
        threading.Thread.__init__(self)
        self.name = name
        self.hyp_id = hyp_id
        self.stop = False
        self.queue_actions = queue_actions
        self.queue_master = queue_master

    def run(self):
        self.tid = get_tid()
        logs.workers.info('starting thread: {} (TID {})'.format(self.name, self.tid))
        host, port, user = get_hyp_hostname_from_id(self.hyp_id)
        port = int(port)
        self.hostname = host
        self.h = hyp(self.hostname, user=user, port=port)
        # self.h.get_kvm_mod()
        # self.h.get_hyp_info()


        update_db_hyp_info(self.hyp_id, self.h.info)
        hyp_id = self.hyp_id

        while self.stop is not True:
            try:
                # do={type:'start_domain','xml':'xml','id_domain'='prova'}
                action = self.queue_actions.get(timeout=TIMEOUT_QUEUES)

                logs.workers.debug('received action in working thread {}'.format(action['type']))

                if action['type'] == 'start_paused_domain':
                    logs.workers.debug('xml to start paused some lines...: {}'.format(action['xml'][30:100]))
                    try:
                        self.h.conn.createXML(action['xml'], flags=VIR_DOMAIN_START_PAUSED)
                        # 32 is the constant for domains paused
                        # reference: https://libvirt.org/html/libvirt-libvirt-domain.html#VIR_CONNECT_LIST_DOMAINS_PAUSED

                        FLAG_LIST_DOMAINS_PAUSED = 32
                        list_all_domains = self.h.conn.listAllDomains(FLAG_LIST_DOMAINS_PAUSED)
                        list_names_domains = [d.name() for d in list_all_domains]
                        dict_domains = dict(zip(list_names_domains,list_all_domains))
                        if action['id_domain'] in list_names_domains:
                            # domain started in pause mode
                            domain = dict_domains[action['id_domain']]
                            domain_active = True
                            try:
                                domain.isActive()
                                domain.destroy()
                                try:
                                    domain.isActive()
                                except Exception as e:
                                    logs.workers.debug('verified domain {} is destroyed'.format(action['id_domain']))
                                domain_active = False

                            except libvirtError as e:
                                from pprint import pformat
                                error_msg = pformat(e.get_error_message())

                                update_domain_status('FailedCreatingDomain', action['id_domain'], hyp_id=self.hyp_id,
                                                     detail='domain {} failed when try to destroy from paused domain in hypervisor {}. creating domain operation is aborted')
                                logs.workers.error(
                                        'Exception in libvirt starting paused xml for domain {} in hypervisor {}. Exception message: {} '.format(
                                                action['id_domain'], self.hyp_id, error_msg))
                                continue


                            if domain_active is False:
                                # domain is destroyed, all ok
                                update_domain_status('CreatingDomain', action['id_domain'], hyp_id='',
                                                      detail='Domain created and test OK: Started, paused and now stopped in hyp {}'.format(self.hyp_id))
                                logs.workers.debug(
                                        'domain {} creating operation finalished. Started paused and destroyed in hypervisor {}. Now status is Stopped. READY TO USE'.format(
                                                action['id_domain'], self.hyp_id))


                            else:
                                update_domain_status('Crashed', action['id_domain'], hyp_id=self.hyp_id,
                                                     detail='Domain is created, started in pause mode but not destroyed,creating domain operation is aborted')
                                logs.workers.error(
                                        'domain {} started paused but not destroyed in hypervisor {}, must be destroyed'.format(
                                                action['id_domain'], self.hyp_id))
                        else:
                            update_domain_status('Crashed', action['id_domain'], hyp_id=self.hyp_id,
                                                 detail='XML for domain {} can not start in pause mode in hypervisor {}, creating domain operation is aborted by unknown cause'.format(
                                                         action['id_domain'], self.hyp_id))
                            logs.workers.error(
                                    'XML for domain {} can not start in pause mode in hypervisor {}, creating domain operation is aborted, not exception, rare case, unknown cause'.format(
                                            action['id_domain'], self.hyp_id))

                    except libvirtError as e:
                        from pprint import pformat
                        error_msg = pformat(e.get_error_message())

                        update_domain_status('FailedCreatingDomain', action['id_domain'], hyp_id=self.hyp_id,
                                             detail='domain {} failed when try to start in pause mode in hypervisor {}. creating domain operation is aborted')
                        logs.workers.error(
                            'Exception in libvirt starting paused xml for domain {} in hypervisor {}. Exception message: {} '.format(
                                action['id_domain'], self.hyp_id, error_msg))
                    except Exception as e:
                        update_domain_status('Crashed', action['id_domain'], hyp_id=self.hyp_id,
                                             detail='domain {} failed when try to start in pause mode in hypervisor {}. creating domain operation is aborted')
                        logs.workers.error(
                            'Exception starting paused xml for domain {} in hypervisor {}. NOT LIBVIRT EXCEPTION, RARE CASE. Exception message: {}'.format(
                                    action['id_domain'], self.hyp_id, str(e)))

                ## START DOMAIN
                elif action['type'] == 'start_domain':
                    logs.workers.debug('xml to start some lines...: {}'.format(action['xml'][30:100]))
                    try:
                        self.h.conn.createXML(action['xml'])
                        # wait to event started to save state in database
                        #update_domain_status('Started', action['id_domain'], hyp_id=self.hyp_id, detail='Domain has started in worker thread')
                        logs.workers.debug('STARTED domain {}: createdXML action in hypervisor {} has been sent'.format(
                            action['id_domain'], host))
                    except libvirtError as e:
                        update_domain_status('Failed', action['id_domain'], hyp_id=self.hyp_id,
                                             detail=("Hypervisor can not create domain with libvirt exception: " + str(e)))
                        logs.workers.debug('exception in starting domain {}: '.format(e))
                    except Exception as e:
                        update_domain_status('Failed', action['id_domain'], hyp_id=self.hyp_id, detail=("Exception when starting domain: " + str(e)))
                        logs.workers.debug('exception in starting domain {}: '.format(e))

                ## STOP DOMAIN
                elif action['type'] == 'stop_domain':
                    logs.workers.debug('action stop domain: {}'.format(action['id_domain'][30:100]))
                    try:
                        self.h.conn.lookupByName(action['id_domain']).destroy()

                        logs.workers.debug('STOPPED domain {}'.format(action['id_domain']))

                        check_if_delete = action.get('delete_after_stopped',False)

                        if check_if_delete is True:
                            update_domain_status('Stopped', action['id_domain'], hyp_id='')
                            update_domain_status('Deleting', action['id_domain'], hyp_id='')
                        else:
                            update_domain_status('Stopped', action['id_domain'], hyp_id='')


                    except Exception as e:
                        update_domain_status('Failed', action['id_domain'], hyp_id=self.hyp_id, detail=str(e))
                        logs.workers.debug('exception in stopping domain {}: '.format(e))

                elif action['type'] in ['create_disk', 'delete_disk']:
                    launch_action_disk(action,
                                       self.hostname,
                                       user,
                                       port)

                elif action['type'] in ['add_media_hot']:
                    pass

                elif action['type'] in ['killall_curl']:
                    launch_killall_curl(self.hostname,
                                       user,
                                       port)

                elif action['type'] in ['delete_media']:
                    final_status = action.get('final_status','Deleted')

                    launch_delete_media (action,
                                       self.hostname,
                                       user,
                                       port,
                                       final_status=final_status)

                    # ## DESTROY THREAD
                    # elif action['type'] == 'destroy_thread':
                    #     list_works_in_queue = list(self.queue_actions.queue)
                    #     if self.queue_master is not None:
                    #         self.queue_master.put(['destroy_working_thread',self.hyp_id,list_works_in_queue])
                    #     #INFO TO DEVELOPER, si entra aquí es porque no quedaba nada en cola, si no ya lo habrán matado antes
                    #
                    #     logs.workers.error('thread worker from hypervisor {} exit from error status'.format(hyp_id))
                    #

                    # raise 'destoyed'

                elif action['type'] == 'create_disk':

                    pass


                elif action['type'] == 'hyp_info':
                    self.h.get_hyp_info()
                    logs.workers.debug('hypervisor motherboard: {}'.format(self.h.info['motherboard_manufacturer']))

                ## DESTROY THREAD
                elif action['type'] == 'stop_thread':
                    self.stop = True
                else:
                    logs.workers.error('type action {} not supported in queue actions'.format(action['type']))
                    # time.sleep(0.1)
                    ## TRY DOMAIN


            except queue.Empty:
                try:
                    self.h.conn.getLibVersion()
                    pass
                    # logs.workers.debug('hypervisor {} is alive'.format(host))
                except:
                    logs.workers.info('trying to reconnect hypervisor {}, alive test in working thread failed'.format(host))
                    alive = False
                    for i in range(RETRIES_HYP_IS_ALIVE):
                        try:
                            time.sleep(TIMEOUT_BETWEEN_RETRIES_HYP_IS_ALIVE)
                            self.h.conn.getLibVersion()
                            alive = True
                            logs.workers.info('hypervisor {} is alive'.format(host))
                            break
                        except:
                            logs.workers.info('hypervisor {} is NOT alive'.format(host))
                    if alive is False:
                        try:
                            self.h.connect_to_hyp()
                            self.h.conn.getLibVersion()
                            update_hyp_status(self.hyp_id, 'Online')
                        except:
                            logs.workers.debug('hypervisor {} failed'.format(host))
                            logs.workers.error('fail reconnecting to hypervisor {} in working thread'.format(host))
                            reason = self.h.fail_connected_reason
                            update_hyp_status(self.hyp_id, 'Error', reason)
                            update_domains_started_in_hyp_to_unknown(self.hyp_id)

                            list_works_in_queue = list(self.queue_actions.queue)
                            if self.queue_master is not None:
                                self.queue_master.put(['error_working_thread', self.hyp_id, list_works_in_queue])
                            logs.workers.error('thread worker from hypervisor {} exit from error status'.format(hyp_id))
                            self.active = False
                            break
        # ~ else:
            # ~ update_hyp_status(self.hyp_id, 'Error','bios vmx or svm virtualization capabilities not activated')
            # ~ update_table_field('hypervisors',self.hyp_id,'enabled',False)
            # ~ logs.workers.error('hypervisor {} disabled: bios vmx or svm virtualization capabilities not activated')
            # ~ #restart when engine is started (not starting)
            # ~ timeout = 10
            # ~ i = 0.0
            # ~ while i < timeout:
                # ~ if get_engine()['status_all_threads'] == 'Started':
                    # ~ engine_restart()
                    # ~ break
                # ~ else:
                    # ~ i + 0.2
                    # ~ sleep(0.2)


