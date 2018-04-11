# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3
# coding=utf-8

import pprint

import queue
import threading
from datetime import datetime
from time import sleep

import rethinkdb as r

from engine.config import TEST_HYP_FAIL_INTERVAL, STATUS_POLLING_INTERVAL, TIME_BETWEEN_POLLING, \
    POLLING_INTERVAL_BACKGROUND
from engine.controllers.events_recolector import launch_thread_hyps_event
from engine.controllers.status import launch_thread_status
from engine.controllers.broom import launch_thread_broom
from engine.controllers.ui_actions import UiActions
from engine.models.pool_hypervisors import PoolHypervisors
from engine.services.db.db import new_rethink_connection, \
    get_pools_from_hyp, update_table_field
from engine.services.db.hypervisors import get_hyps_ready_to_start, get_hypers_disk_operations, update_hyp_status, \
    get_hyp_hostname_user_port_from_id, update_all_hyps_status, get_hyps_with_status
from engine.services.db import get_domain_hyp_started, get_if_all_disk_template_created, \
    set_unknown_domains_not_in_hyps, get_domain, remove_domain, update_domain_history_from_id_domain
from engine.services.db.domains import update_domain_status, update_domain_start_after_created, update_domain_delete_after_stopped
from engine.services.lib.functions import get_threads_running, get_tid, engine_restart
from engine.services.log import logs
from engine.services.threads.download_thread import launch_thread_download_changes
from engine.services.threads.threads import launch_try_hyps, set_domains_coherence, launch_thread_worker, \
    launch_disk_operations_thread, \
    launch_long_operations_thread
from engine.services.lib.functions import clean_intermediate_status

class ManagerHypervisors(object):
    def __init__(self, launch_threads=True, with_status_threads=True,
                 status_polling_interval=STATUS_POLLING_INTERVAL,
                 test_hyp_fail_interval=TEST_HYP_FAIL_INTERVAL):

        logs.main.info('MAIN PID: {}'.format(get_tid()))

        self.time_between_polling = TIME_BETWEEN_POLLING
        self.polling_interval_background = POLLING_INTERVAL_BACKGROUND
        self.with_status_threads = with_status_threads

        self.q = self.QueuesThreads()
        self.t_workers = {}
        self.t_status = {}
        self.pools = {}
        self.t_disk_operations = {}
        self.q_disk_operations = {}
        self.t_long_operations = {}
        self.q_long_operations = {}
        self.t_changes_hyps = None
        self.t_events = None
        self.t_changes_domains = None
        self.t_broom = None
        self.t_background = None
        self.t_downloads_changes = None
        self.quit = False

        self.num_workers = 0
        self.threads_started = False

        self.STATUS_POLLING_INTERVAL = status_polling_interval
        self.TEST_HYP_FAIL_INTERVAL = test_hyp_fail_interval

        update_all_hyps_status(reset_status='Offline')
        if launch_threads is True:
            self.launch_thread_background_polling()

    def launch_thread_background_polling(self):
        self.t_background = self.ThreadBackground(name='manager_pooling', parent=self)
        self.t_background.daemon = True
        self.t_background.start()

    def check_actions_domains_enabled(self):
        if self.num_workers > 0 and self.threads_started is True:
            return True
        else:
            return False

    def update_info_threads_engine(self):
        d = {}
        alive=[]
        dead=[]
        not_defined=[]
        #events,broom
        for name in ['events','broom','downloads_changes','changes_hyps','changes_domains']:
            try:
                alive.append(name) if self.__getattribute__('t_'+name).is_alive() else dead.append(name)
            except:
                #thread not defined
                not_defined.append(name)

        for name in ['workers','status','disk_operations','long_operations']:
            for hyp,t in self.__getattribute__('t_'+name).items():
                try:
                    alive.append(name + '_' + hyp) if t.is_alive() else dead.append(name + '_' + hyp)
                except:
                    not_defined.append(name)
                    pass

        d['alive']=alive
        d['dead']=dead
        d['not_defined']=not_defined
        update_table_field('engine', 'engine', 'threads', d)
        return alive,dead,not_defined

    def stop_threads(self):
        # events and broom
        self.t_events.stop = True
        while True:
            if self.t_events.is_alive() is False:
                break
            sleep(0.1)
        self.t_broom.stop = True
        # operations / status
        for k,v in self.t_long_operations.items():
            v.stop = True
        for k, v in self.t_disk_operations.items():
            v.stop = True
        for k, v in self.t_workers.items():
            v.stop = True
        for k, v in self.t_status.items():
            v.stop = True

        self.q_disk_operations



        # changes
        update_table_field('engine', 'engine', 'status_all_threads', 'Stopping')

        # self.t_changes_domains.stop = True
        # self.t_changes_hyps.stop = True
        # self.t_downloads_changes.stop = True
        #
        # if self.t_changes_domains.cursor_changes is not False:
        #     self.t_changes_domains.cursor_changes()
        #     self.t_changes_domains.r_conn.close()
        # if self.t_changes_hyps.r_conn is not False:
        #     self.t_changes_hyps.r_conn.close()
        # if self.t_downloads_changes.r_conn is not False:
        #     self.t_downloads_changes.r_conn.close()



    class ThreadBackground(threading.Thread):
        def __init__(self, name, parent):
            threading.Thread.__init__(self)
            self.name = name
            self.manager = parent
            self.stop = False
            # self.manager = parent
            self.hyps_running = []

        def set_parent(self, parent):
            self.manager = parent

        def check_and_start_hyps(self):
            pass

        def launch_threads_disk_and_long_operations(self):

            self.manager.hypers_disk_operations = get_hypers_disk_operations()

            for hyp_disk_operations in self.manager.hypers_disk_operations:
                hyp_long_operations = hyp_disk_operations
                d = get_hyp_hostname_user_port_from_id(hyp_disk_operations)

                self.manager.t_disk_operations[hyp_disk_operations], \
                self.manager.q_disk_operations[hyp_disk_operations] = launch_disk_operations_thread(
                    hyp_id=hyp_disk_operations,
                    hostname=d['hostname'],
                    user=d['user'],
                    port=d['port']
                )
                self.manager.t_long_operations[hyp_long_operations], \
                self.manager.q_long_operations[hyp_long_operations] = launch_long_operations_thread(
                    hyp_id=hyp_long_operations,
                    hostname=d['hostname'],
                    user=d['user'],
                    port=d['port']
                )

        def test_hyps_and_start_threads(self):

            l_hyps_to_test = get_hyps_with_status(list_status=['Error', 'Offline'], empty=True)

            dict_hyps_to_test = {d['id']: {'hostname': d['hostname'],
                                           'port': d['port'] if 'port' in d.keys() else 22,
                                           'user': d['user'] if 'user' in d.keys() else 'root'} for d in
                                 l_hyps_to_test}

            launch_try_hyps(dict_hyps_to_test)
            dict_hyps_ready = self.manager.dict_hyps_ready = get_hyps_ready_to_start()

            if len(dict_hyps_ready) > 0:
                logs.main.debug('hyps_ready_to_start: ' + pprint.pformat(dict_hyps_ready))

                #launch thread events
                if self.manager.t_events is None:
                    logs.main.info('launching hypervisor events thread')
                    self.manager.t_events = launch_thread_hyps_event(dict_hyps_ready)
                else:
                    #if new hypervisor has added then add hypervisor to receive events
                    logs.main.info('hypervisors added to thread events')
                    logs.main.info(pprint.pformat(dict_hyps_ready))
                    self.manager.t_events.hyps.update(dict_hyps_ready)
                    for hyp_id, hostname in self.manager.t_events.hyps.items():
                        self.manager.t_events.add_hyp_to_receive_events(hyp_id)
                set_unknown_domains_not_in_hyps(dict_hyps_ready.keys())
                set_domains_coherence(dict_hyps_ready)

                pools = set()
                for hyp_id, hostname in dict_hyps_ready.items():
                    update_hyp_status(hyp_id, 'StartingThreads')
                    # start worker thread
                    self.manager.t_workers[hyp_id], self.manager.q.workers[hyp_id] = launch_thread_worker(hyp_id)
                    if self.manager.with_status_threads is True:
                        self.manager.t_status[hyp_id] = launch_thread_status(hyp_id,
                                                                             self.manager.STATUS_POLLING_INTERVAL)

                    # self.manager.launch_threads(hyp_id)
                    # INFO TO DEVELOPER FALTA VERIFICAR QUE REALMENTE ESTÁN ARRANCADOS LOS THREADS??
                    # comprobar alguna variable a true en alguno de los threads
                    update_hyp_status(hyp_id, 'Online')
                    pools.update(get_pools_from_hyp(hyp_id))

                for id_pool in pools:
                    if id_pool not in self.manager.pools.keys():
                        self.manager.pools[id_pool] = PoolHypervisors(id_pool, self.manager, len(dict_hyps_ready))

        def run(self):
            self.tid = get_tid()
            logs.main.info('starting thread: {} (TID {})'.format(self.name, self.tid))
            q = self.manager.q.background
            first_loop = True

            clean_intermediate_status()

            l_hyps_to_test = get_hyps_with_status(list_status=['Error', 'Offline'], empty=True)
            while len(l_hyps_to_test) == 0:
                logs.main.error('no hypervisor enable, waiting for one hypervisor')
                sleep(0.5)
                l_hyps_to_test = get_hyps_with_status(list_status=['Error', 'Offline'], empty=True)

            while self.manager.quit is False:
                # ONLY FOR DEBUG
                logs.main.debug('##### THREADS ##################')
                get_threads_running()
                self.manager.update_info_threads_engine()

                # DISK_OPERATIONS:
                if len(self.manager.t_disk_operations) == 0:
                    self.launch_threads_disk_and_long_operations()

                # TEST HYPS AND START THREADS FROM RETHINK
                self.test_hyps_and_start_threads()

                # LAUNCH CHANGES THREADS
                if first_loop is True:
                    update_table_field('engine', 'engine', 'status_all_threads', 'Starting')
                    self.manager.t_changes_hyps = self.manager.HypervisorChangesThread('changes_hyp', self.manager)
                    self.manager.t_changes_hyps.daemon = True
                    self.manager.t_changes_hyps.start()

                    self.manager.t_changes_domains = self.manager.DomainsChangesThread('changes_domains', self.manager)
                    self.manager.t_changes_domains.daemon = True
                    self.manager.t_changes_domains.start()

                    logs.main.debug('Launching Download Changes Thread')
                    self.manager.t_downloads_changes = launch_thread_download_changes(self.manager)

                    self.manager.t_broom = launch_thread_broom(self.manager)

                    first_loop = False

                    logs.main.info('THREADS LAUNCHED FROM BACKGROUND THREAD')
                    update_table_field('engine', 'engine', 'status_all_threads', 'Starting')
                    while True:
                        sleep(0.1)
                        alive, dead, not_defined = self.manager.update_info_threads_engine()
                        pprint.pprint({'alive':alive,
                                       'dead':dead,
                                       'not_defined':not_defined})
                        if len(not_defined) == 0 and len(dead) == 0:
                            update_table_field('engine', 'engine', 'status_all_threads', 'Started')
                            self.manager.num_workers = len(self.manager.t_workers)
                            self.manager.threads_started = True
                            break

                try:
                    action = q.get(timeout=self.manager.TEST_HYP_FAIL_INTERVAL)
                    if action['type'] == 'stop':
                        self.manager.quit = True
                        logs.main.info('engine end')
                except queue.Empty:
                    pass
                except Exception as e:
                    logs.main.error(e)
                    return False

                    ## TODO INFO TO DEVELOPER
                    # VERFICAR QUE EL THREAD DE DISK_OPERATIONS ESTÁ ACTIVO Y QUE SI NO
                    ## ESTÁ ARRANCAR UN THREAD DE DISK_OPERATIONS
                    ## PODRÍA SALTAR AUTOMÁTICO A OTRO
                    ## ??

    class QueuesThreads:
        def __init__(self):
            self.background = queue.Queue()
            self.workers = {}
            self.quit = False
            self.action = ''

    class HypervisorChangesThread(threading.Thread):
        def __init__(self, name, parent):
            threading.Thread.__init__(self)
            self.manager = parent
            self.name = name
            self.stop = False
            self.r_conn = False

        def run(self):
            self.tid = get_tid()
            logs.main.info('starting thread: {} (TID {})'.format(self.name, self.tid))
            self.r_conn = new_rethink_connection()
            # rtable=r.table('disk_operations')
            # for c in r.table('hypervisors').changes(include_initial=True, include_states=True).run(r_conn):
            for c in r.table('hypervisors').pluck('capabilities',
                                                  'enabled',
                                                  'hostname',
                                                  'hypervisors_pools',
                                                  'port',
                                                  'user',
                                                  'viewer_hostname',
                                                  'viewer_nat_hostname').merge({'table': 'hypervisors'}).changes().\
                    union(r.table('engine').pluck('threads', 'status_all_threads').merge({'table': 'engine'}).changes())\
                    .run(self.r_conn):

                #stop thread
                if self.stop is True:
                    break

                if c['new_val'] is not None:
                    if c['new_val']['table'] == 'engine':
                        if c['new_val']['status_all_threads'] == 'Stopping':
                            break

                # hypervisor deleted
                if c['new_val'] is None:
                    if c['old_val'].get('table',False) == 'hypervisors':

                        logs.main.info('hypervisor deleted in rethink')
                        logs.main.info(pprint.pformat(c))
                        #TODO: verify no domains in hypervisor running (front end and backend) and fence or unknown if
                        # domains are running and hypevisor communication have lost
                        engine_restart()
                # hypervisor created
                elif c['old_val'] is None:
                    if c['new_val'].get('table',False) == 'hypervisors':
                        logs.main.info('hypervisor created in rethink')
                        logs.main.info(pprint.pformat(c))
                        engine_restart()
                else:
                    if c['new_val'].get('table', False) == 'hypervisors':
                        #TODO: verify no domains in hypervisor running (front end and backend) and fence or unknown if
                        # domains are running and hypevisor communication have lost
                        logs.main.info('hypervisor fields modified in rethink')
                        logs.main.info(pprint.pformat(c))
                        engine_restart()

                    #self.manager.q.background.put({'type': 'add_hyp'})

            self.r_conn.close()

    class DomainsChangesThread(threading.Thread):
        def __init__(self, name, parent):
            threading.Thread.__init__(self)
            self.manager = parent
            self.name = name
            self.stop = False
            self.r_conn = False

        def run(self):
            self.tid = get_tid()
            logs.changes.info('starting thread: {} (TID {})'.format(self.name, self.tid))
            logs.changes.debug('^^^^^^^^^^^^^^^^^^^ DOMAIN CHANGES THREAD ^^^^^^^^^^^^^^^^^')
            ui = UiActions(self.manager)

            # Test hypervisor disk operations
            # Create Test disk in hypervisor disk operations
            virtio_test_disk_relative_path = 'admin/admin/admin/virtio_testdisk.qcow2'
            ui.creating_test_disk(test_disk_relative_route=virtio_test_disk_relative_path)


            self.r_conn = new_rethink_connection()

            cursor = r.table('domains').pluck('id', 'kind', 'status', 'detail').merge({'table': 'domains'}).changes().\
                union(r.table('engine').pluck('threads', 'status_all_threads').merge({'table': 'engine'}).changes()).\
                run(self.r_conn)

            for c in cursor:

                if self.stop is True:
                    break

                if c.get('new_val', None) is not None:
                    if c['new_val']['table'] == 'engine':
                        if c['new_val']['status_all_threads'] == 'Stopping':
                            break
                        else:
                            continue

                logs.changes.debug('domain changes detected in main thread')

                detail_msg_if_no_hyps_online = 'No hypervisors Online in pool'
                if self.manager.check_actions_domains_enabled() is False:
                    if c.get('new_val', None) is not None:
                        if c.get('old_val', None) is not None:
                            if c['new_val']['status'][-3:] == 'ing':
                                update_domain_status(c['old_val']['status'], c['old_val']['id'], detail=detail_msg_if_no_hyps_online)

                    #if no hypervisor availables no check status changes
                    continue

                new_domain = False
                new_status = False
                old_status = False
                import pprint
                logs.changes.debug(pprint.pformat(c))



                # action deleted
                if c.get('new_val', None) is None:
                    pass
                # action created
                if c.get('old_val', None) is None:
                    new_domain = True
                    new_status = c['new_val']['status']
                    domain_id = c['new_val']['id']
                    logs.changes.debug('domain_id: {}'.format(new_domain))
                    # if engine is stopped/restarting or not hypervisors online
                    if self.manager.check_actions_domains_enabled() is False:
                        continue
                    pass

                if c.get('new_val', None) is not None and c.get('old_val', None) is not None:
                    old_status = c['old_val']['status']
                    new_status = c['new_val']['status']
                    new_detail = c['new_val']['detail']
                    domain_id = c['new_val']['id']
                    logs.changes.debug('domain_id: {}'.format(domain_id))
                    # if engine is stopped/restarting or not hypervisors online




                    if old_status != new_status:



                        # print('&&&&&&& ID DOMAIN {} - old_status: {} , new_status: {}, detail: {}'.format(domain_id,old_status,new_status, new_detail))
                        # if new_status[-3:] == 'ing':
                        if 1 > 0:
                            date_now = datetime.now()
                            update_domain_history_from_id_domain(domain_id, new_status, new_detail, date_now)
                    else:
                        # print('&&&&&&&ESTADOS IGUALES OJO &&&&&&&\n&&&&&&&& ID DOMAIN {} - old_status: {} , new_status: {}, detail: {}'.
                        #       format(domain_id,old_status,new_status,new_detail))
                        pass

                if (new_domain is True and new_status == "CreatingDiskFromScratch") or \
                        (old_status == 'FailedCreatingDomain' and new_status == "CreatingDiskFromScratch"):
                    ui.creating_disk_from_scratch(domain_id)

                if (new_domain is True and new_status == "Creating") or \
                        (old_status == 'FailedCreatingDomain' and new_status == "Creating"):
                    ui.creating_disks_from_template(domain_id)

                if (new_domain is True and new_status == "CreatingAndStarting"):
                    update_domain_start_after_created(domain_id)
                    ui.creating_disks_from_template(domain_id)


                    # INFO TO DEVELOPER
                    # recoger template de la que hay que derivar
                    # verificar que realmente es una template
                    # hay que recoger ram?? cpu?? o si no hay nada copiamos de la template??

                if (new_domain is True and new_status == "CreatingFromBuilder") or \
                        (old_status == 'FailedCreatingDomain' and new_status == "CreatingFromBuilder"):
                    ui.creating_disk_from_virtbuilder(domain_id)

                if (old_status in ['CreatingDisk','CreatingDiskFromScratch'] and new_status == "CreatingDomain") or \
                        (old_status == 'RunningVirtBuilder' and new_status == "CreatingDomainFromBuilder"):
                    logs.changes.debug('llamo a creating_and_test_xml con domain id {}'.format(domain_id))
                    if new_status == "CreatingDomainFromBuilder":
                        ui.creating_and_test_xml_start(domain_id,
                                                       creating_from_create_dict=True,
                                                       xml_from_virt_install=True)
                    if new_status == "CreatingDomain":
                        ui.creating_and_test_xml_start(domain_id,
                                                       creating_from_create_dict=True)

                if old_status == 'Stopped' and new_status == "CreatingTemplate":
                    ui.create_template_disks_from_domain(domain_id)

                if old_status == 'Stopped' and new_status == "Deleting":
                    ui.deleting_disks_from_domain(domain_id)

                if (old_status == 'Stopped' and new_status == "Updating") or \
                        (old_status == 'Downloaded' and new_status == "Updating"):
                    ui.updating_from_create_dict(domain_id)

                if old_status == 'DeletingDomainDisk' and new_status == "DiskDeleted":
                    logs.changes.debug('disk deleted, mow remove domain form database')
                    remove_domain(domain_id)
                    if get_domain(domain_id) is None:
                        logs.changes.info('domain {} deleted from database'.format(domain_id))
                    else:
                        update_domain_status('Failed', id_domain,
                                             detail='domain {} can not be deleted from database'.format(domain_id))

                if old_status == 'CreatingTemplateDisk' and new_status == "TemplateDiskCreated":
                    # create_template_from_dict(dict_new_template)
                    if get_if_all_disk_template_created(domain_id):
                        ui.create_template_in_db(domain_id)
                    else:
                        # INFO TO DEVELOPER, este else no se si tiene mucho sentido, hay que hacer pruebas con la
                        # creación de una template con dos discos y ver si pasa por aquí
                        # waiting to create other disks
                        update_domain_status(status='CreatingTemplateDisk',
                                             id_domain=domain_id,
                                             hyp_id=False,
                                             detail='Waiting to create more disks for template')

                if (old_status == 'Stopped' and new_status == "Starting") or \
                        (old_status == 'Failed' and new_status == "Starting"):
                    ui.start_domain_from_id(id=domain_id, ssl=True)

                if (old_status == 'Started' and new_status == "Stopping" ) or \
                        (old_status == 'Suspended' and new_status == "Stopping" ):
                    # INFO TO DEVELOPER Esto es lo que debería ser, pero hay líos con el hyp_started
                    # ui.stop_domain_from_id(id=domain_id)
                    hyp_started = get_domain_hyp_started(domain_id)
                    if hyp_started:
                        ui.stop_domain(id_domain=domain_id, hyp_id=hyp_started)
                    else:
                        logs.main.error('domain without hyp_started can not be stopped: {}. '.format(domain_id))

                if (old_status == 'Started' and new_status == "StoppingAndDeleting" ) or \
                        (old_status == 'Suspended' and new_status == "StoppingAndDeleting" ):
                    # INFO TO DEVELOPER Esto es lo que debería ser, pero hay líos con el hyp_started
                    # ui.stop_domain_from_id(id=domain_id)
                    hyp_started = get_domain_hyp_started(domain_id)
                    print(hyp_started)
                    ui.stop_domain(id_domain=domain_id, hyp_id=hyp_started, delete_after_stopped=True)

            logs.main.info('finalished thread domain changes')
