# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8
import queue
import threading
import rethinkdb as r
import time
import pprint

from .pool_hypervisors import PoolHypervisors
from .threads import launch_try_hyps, set_unknown_domains_not_in_hyps
from .threads import set_domains_coherence, launch_thread_worker, launch_disk_operations_thread
from .events_recolector import launch_thread_hyps_event
from .status import launch_thread_status, launch_thread_broom
from .db import get_hyps_with_status, get_pool_from_domain, update_hyp_status, remove_domain, get_domain
from .db import new_rethink_connection, update_all_hyps_status, get_pools_from_hyp, get_domain_hyp_started
from .db import get_if_all_disk_template_created, update_domain_status, get_hypers_disk_operations
from .db import get_hyps_ready_to_start, get_hyp_hostname_user_port_from_id
from .functions import get_threads_running, get_tid
from .ui_actions import UiActions
from .log import *
from .config import TEST_HYP_FAIL_INTERVAL, STATUS_POLLING_INTERVAL, TIME_BETWEEN_POLLING, POLLING_INTERVAL_BACKGROUND


class ManagerHypervisors(object):
    def __init__(self, launch_threads=True,with_status_threads=True,
                 status_polling_interval=STATUS_POLLING_INTERVAL,
                 test_hyp_fail_interval=TEST_HYP_FAIL_INTERVAL):

        log.info('MAIN PID: {}'.format(get_tid()))

        self.time_between_polling = TIME_BETWEEN_POLLING
        self.polling_interval_background = POLLING_INTERVAL_BACKGROUND
        self.with_status_threads = with_status_threads

        self.q = self.QueuesThreads()
        self.t_workers = {}
        self.t_status = {}
        self.pools = {}
        self.t_disk_operations = {}
        self.q_disk_operations = {}
        self.t_changes_hyps = None
        self.t_changes_domains = None
        self.t_broom = None
        self.t_background = None
        self.quit = False

        self.STATUS_POLLING_INTERVAL = status_polling_interval
        self.TEST_HYP_FAIL_INTERVAL = test_hyp_fail_interval

        update_all_hyps_status(reset_status='Offline')
        if launch_threads is True:
            self.launch_thread_background_polling()

    def launch_thread_background_polling(self):
        self.t_background = self.ThreadBackground(name='manager_pooling', parent=self)
        self.t_background.daemon = True
        self.t_background.start()

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

        def launch_threads_disk_operations(self):
            self.manager.hypers_disk_operations = get_hypers_disk_operations()

            for hyp_disk_operations in self.manager.hypers_disk_operations:
                d = get_hyp_hostname_user_port_from_id(hyp_disk_operations)

                self.manager.t_disk_operations[hyp_disk_operations], \
                self.manager.q_disk_operations[hyp_disk_operations] = launch_disk_operations_thread(
                        hyp_id=hyp_disk_operations,
                        hostname=d['hostname'],
                        user=d['user'],
                        port=d['port']
                )

        def test_hyps_and_start_threads(self):

            l_hyps_to_test = get_hyps_with_status(list_status=['Error', 'Offline'], empty=True)
            dict_hyps_to_test = {d['id']: {'hostname': d['hostname'],
                                           'port'    : d['port'] if 'port' in d.keys() else 22,
                                           'user'    : d['user'] if 'user' in d.keys() else 'root'} for d in
                                 l_hyps_to_test}

            launch_try_hyps(dict_hyps_to_test)
            dict_hyps_ready = self.manager.dict_hyps_ready = get_hyps_ready_to_start()
            if len(dict_hyps_ready) > 0:
                log.debug('hyps_ready_to_start: ' + pprint.pformat(dict_hyps_ready))

                set_unknown_domains_not_in_hyps(dict_hyps_ready.keys())
                set_domains_coherence(dict_hyps_ready)

                self.manager.t_events = launch_thread_hyps_event(dict_hyps_ready)

                for hyp_id, hostname in dict_hyps_ready.items():
                    update_hyp_status(hyp_id, 'StartingThreads')
                    # start worker thread
                    self.manager.t_workers[hyp_id], self.manager.q.workers[hyp_id] = launch_thread_worker(hyp_id)
                    if self.manager.with_status_threads is True:
                        self.manager.t_status[hyp_id] = launch_thread_status(hyp_id, self.manager.STATUS_POLLING_INTERVAL)

                    # self.manager.launch_threads(hyp_id)
                    # INFO TO DEVELOPER FALTA VERIFICAR QUE REALMENTE ESTÁN ARRANCADOS LOS THREADS??
                    # comprobar alguna variable a true en alguno de los threads
                    update_hyp_status(hyp_id, 'Online')
                    pools = get_pools_from_hyp(hyp_id)
                    for id_pool in pools:
                        if id_pool not in self.manager.pools.keys():
                            self.manager.pools[id_pool] = PoolHypervisors(id_pool)



        def run(self):
            self.tid = get_tid()
            log.info('starting thread: {} (TID {})'.format(self.name, self.tid))
            q = self.manager.q.background
            first_loop = True

            while self.manager.quit is False:
                # ONLY FOR DEBUG
                log.debug('##### THREADS ##################')
                get_threads_running()
                # DISK_OPERATIONS:
                if len(self.manager.t_disk_operations) == 0:
                    self.launch_threads_disk_operations()

                # TEST HYPS AND START THREADS FROM RETHINK
                self.test_hyps_and_start_threads()

                # LAUNCH CHANGES THREADS
                if first_loop is True:
                    self.manager.t_changes_hyps = self.manager.HypervisorChangesThread('changes_hyp', self.manager)
                    self.manager.t_changes_hyps.daemon = True
                    self.manager.t_changes_hyps.start()

                    self.manager.t_changes_domains = self.manager.DomainsChangesThread('changes_domains', self.manager)
                    self.manager.t_changes_domains.daemon = True
                    self.manager.t_changes_domains.start()

                    self.manager.t_broom = launch_thread_broom()

                    first_loop = False

                # TODO INFO TO DEVELOPER, ESTO DEBERAÍ FUNCIONAR CON UN PAR DE EVENTOS QUIZÁS

                try:
                    action = q.get(timeout=self.manager.TEST_HYP_FAIL_INTERVAL)
                    if action['type'] == 'stop':
                        self.manager.quit = True
                except queue.Empty:
                    pass
                except Exception as e:
                    log.error(e)
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

        def run(self):
            self.tid = get_tid()
            log.info('starting thread: {} (TID {})'.format(self.name, self.tid))
            r_conn = new_rethink_connection()
            # rtable=r.table('disk_operations')
            # for c in r.table('hypervisors').changes(include_initial=True, include_states=True).run(r_conn):
            for c in r.table('hypervisors').changes().run(r_conn):

                # hypervisor deleted
                if c['new_val'] is None:
                    log.info('hypervisor deleted in rethink')
                    log.info(pprint.pformat(c))
                    # pprint.pprint(c)
                    pass
                # hypervisor created
                if c['old_val'] is None:
                    log.info('hypervisor created in rethink')
                    log.info(pprint.pformat(c))
                    self.manager.q.background.put({'type': 'add_hyp'})

            r_conn.close()

    class ActionsChangesThread(threading.Thread):
        def __init__(self, name, parent):
            threading.Thread.__init__(self)
            self.manager = parent
            self.name = name

        def run(self):
            self.tid = get_tid()
            log.info('starting thread: {} (TID {})'.format(self.name, self.tid))
            log.debug('^^^^^^^^^^^^^^^^^^^ ACTIONS THREAD ^^^^^^^^^^^^^^^^^')
            ui = UiActions(self.manager)
            r_conn = new_rethink_connection()

            # rtable=r.table('disk_operations')
            # for c in r.table('hypervisors').changes(include_initial=True, include_states=True).run(r_conn):
            for c in r.table('actions').changes().run(r_conn):

                # action deleted
                if c['new_val'] is None:
                    pass
                # action created
                if c['old_val'] is None:
                    log.debug(pprint.pformat(c))
                    new_action = c['new_val']
                    log.debug('action: {} - {}'.format(new_action['id'], new_action['action']))
                    action = new_action['action']
                    parameters = new_action['parameters']
                    ui.action_from_api(action=action, parameters=parameters)
                    # pprint.pprint(get_threads_running())
                    # pprint.pprint(self.manager.dict_hyps_ready)
            r_conn.close()

    class DomainsChangesThread(threading.Thread):
        def __init__(self, name, parent):
            threading.Thread.__init__(self)
            self.manager = parent
            self.name = name

        def run(self):
            self.tid = get_tid()
            log.info('starting thread: {} (TID {})'.format(self.name, self.tid))
            log.debug('^^^^^^^^^^^^^^^^^^^ DOMAIN CHANGES THREAD ^^^^^^^^^^^^^^^^^')
            ui = UiActions(self.manager)
            r_conn = new_rethink_connection()

            # rtable=r.table('disk_operations')
            # for c in r.table('hypervisors').changes(include_initial=True, include_states=True).run(r_conn):
            # for c in r.table('actions').changes().run(r_conn):
            # for c in r.table('domains').get_all(username, index='user').\
            #                            filter((r.row["kind"] == 'user_template') | (r.row["kind"] == 'public_template')).\
            #                            pluck({'id', 'name','icon','kind','description'}).\
            #                            changes(include_initial=True).run(db.conn):

            for c in r.table('domains').pluck('id', 'kind', 'status').changes().run(r_conn):

                log.debug('domain changes detected in main thread')
                new_domain = False
                new_status = False
                old_status = False
                import pprint
                log.debug(pprint.pformat(c))


                # action deleted
                if c['new_val'] is None:
                    pass
                # action created
                if c['old_val'] is None:
                    new_domain = True
                    new_status = c['new_val']['status']
                    domain_id = c['new_val']['id']
                    pass

                if c['new_val'] is not None and c['old_val'] is not None:
                    old_status = c['old_val']['status']
                    new_status = c['new_val']['status']
                    domain_id = c['new_val']['id']
                    log.debug('domain_id: {}'.format(domain_id))

                if (new_domain is True and new_status == "Creating") or \
                        (old_status == 'FailedCreatingDomain' and new_status == "Creating"):
                    ui.creating_disks_from_template(domain_id)

                    # INFO TO DEVELOPER
                    # recoger template de la que hay que derivar
                    # verificar que realmente es una template
                    # hay que recoger ram?? cpu?? o si no hay nada copiamos de la template??

                if old_status == 'CreatingDisk' and new_status == "CreatingDomain":
                    log.debug('llamo a creating_and_test_xml con domain id {}'.format(domain_id))
                    ui.creating_and_test_xml_start(domain_id,
                                                   creating_from_create_dict=True)

                if old_status == 'Stopped' and new_status == "CreatingTemplate":
                    ui.create_template_disks_from_domain(domain_id)

                if old_status == 'Stopped' and new_status == "Deleting":
                    ui.deleting_disks_from_domain(domain_id)

                if old_status == 'DeletingDomainDisk' and new_status == "DiskDeleted":
                    log.debug('disk deleted, mow remove domain form database')
                    remove_domain(domain_id)
                    if get_domain(domain_id) is None:
                        log.info('domain {} deleted from database'.format(domain_id))
                    else:
                        update_domain_status('Failed', id_domain, detail='domain {} can not be deleted from database'.format(domain_id))

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

                if old_status == 'Started' and new_status == "Stopping":
                    # INFO TO DEVELOPER Esto es lo que debería ser, pero hay líos con el hyp_started
                    # ui.stop_domain_from_id(id=domain_id)
                    hyp_started = get_domain_hyp_started(domain_id)
                    ui.stop_domain(id_domain=domain_id, hyp_id=hyp_started)

            r_conn.close()

