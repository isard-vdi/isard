# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

#/bin/python3
# coding=utf-8
from lxml import etree
from collections import OrderedDict
import queue
import threading
import time
import os

from libvirt import VIR_DOMAIN_START_PAUSED,libvirtError
from os.path import dirname as extract_dir_path

from time import sleep
import threading
# from pool_hypervisors import update_online_hypervisors
from .db import get_hyp_hostnames_online,update_domain_hyp_started, update_all_domains_status
from .db import update_hypervisor_failed_connection, update_hyp_status, set_unknown_domains_not_in_hyps
from .db import update_domain_status, get_domains_started_in_hyp, get_hyp_hostname_from_id, update_domains_started_in_hyp_to_unknown
from .functions import dict_domain_libvirt_state_to_isard_state, state_and_cause_to_str,execute_commands, execute_command_with_progress,get_tid
from .qcow import extract_list_backing_chain,create_cmds_disk_template_from_domain, verify_output_cmds1_template_from_domain,verify_output_cmds2,verify_output_cmds3
from .db import update_db_hyp_info, update_disk_template_created, update_disk_backing_chain
from .vm import create_template_from_dict

import pprint


from .hyp import hyp
from .log import *
from .db import update_domain_status, get_id_hyp_from_uri,insert_disk_operation,update_disk_operation
# from pool_hypervisors. import PoolHypervisors
from .functions import exec_remote_updating_progress,exec_remote_list_of_cmds, exec_remote_list_of_cmds_dict

from .config import CONFIG_DICT

TIMEOUT_QUEUES = float(CONFIG_DICT["TIMEOUTS"]["timeout_queues"])
TIMEOUT_BETWEEN_RETRIES_HYP_IS_ALIVE = float(CONFIG_DICT["TIMEOUTS"]["timeout_between_retries_hyp_is_alive"])
RETRIES_HYP_IS_ALIVE = int(CONFIG_DICT["TIMEOUTS"]["retries_hyp_is_alive"])


def create_disk_action_dict(id_domain,path_template_disk,path_domain_disk,disk_index_in_bus=0):
    action = {}
    action['id_domain'] = id_domain
    action['type'] = 'create_template_disk_from_domain'
    action['path_template_disk'] = path_template_disk
    action['path_domain_disk'] = path_domain_disk
    action['disk_index'] = disk_index_in_bus

def threading_enumerate():
    # time.sleep(0.5)
    e = threading.enumerate()
    l = [t._Thread__name for t in e]
    l.sort()
    for i in l:
        log.debug('Thread running: {}'.format(i))
    return e

def launch_disk_operations_thread(hyp_id,hostname,user='root',port=22):

    if hyp_id is False:
        return False,False

    queue_disk_operation = queue.Queue()
    #thread_disk_operation = threading.Thread(name='disk_op_'+id,target=disk_operations_thread, args=(host_disk_operations,queue_disk_operation))
    thread_disk_operation = DiskOperationsThread(name='disk_op_'+hyp_id,
                                                 hyp_id = hyp_id,
                                                 hostname = hostname,
                                                 queue_actions = queue_disk_operation,
                                                 user='root',
                                                 port=22)
    thread_disk_operation.daemon = True
    thread_disk_operation.start()
    return thread_disk_operation,queue_disk_operation

def launch_delete_disk_action(action,hostname,user,port):
    disk_path = action['disk_path']
    id_domain = action['domain']
    array_out_err = execute_commands(hostname,
                                     ssh_commands=action['ssh_comands'],
                                     user=user,
                                     port=port)
    #ALBERTO FALTA ACABAR

    pass


def launch_action_delete_disk(action,hostname,user,port):
    disk_path  = action['disk_path']
    id_domain  = action['domain']
    array_out_err = execute_commands(hostname,
                                     ssh_commands=action['ssh_comands'],
                                     user=user,
                                     port=port)
    #last ls must fail
    if len([k['err'] for k in array_out_err if len(k['err']) == 1]):
        log.debug('all operations deleting  disk {} for domain {} runned ok'.format(disk_path, id_domain))



def launch_action_disk(action,hostname,user,port):
    disk_path  = action['disk_path']
    id_domain  = action['domain']
    index_disk = action['index_disk']
    array_out_err = execute_commands(hostname,
                                     ssh_commands=action['ssh_comands'],
                                     user=user,
                                     port=port)

    if action['type'] == 'create_disk':
        if len([k['err'] for k in array_out_err if len(k['err']) == 0]):
            ##TODO: TEST WITH MORE THAN ONE DISK, 2 list_backing_chain must be created
            log.debug('all operations creating disk {} for new domain {} runned ok'.format(disk_path, id_domain))
            out_cmd_backing_chain = array_out_err[-1]['out']

            list_backing_chain = extract_list_backing_chain(out_cmd_backing_chain)
            update_disk_backing_chain(id_domain, index_disk, disk_path, list_backing_chain)
            ##INFO TO DEVELOPER
            # ahora ya se puede llamar a starting paused
            update_domain_status('CreatingDomain', id_domain, None,
                                 detail='new disk created, now go to creating desktop and testing if desktop start')
        else:

            log.error('operations creating disk {} for new domain {} failed.'.format(disk_path, id_domain))
            log.error('\n'.join(['cmd: {} / out: {} / err: {}'.format(action['ssh_comands'][i],
                                                                      array_out_err[i]['out'],
                                                                      array_out_err[i]['err']) for i in
                                 range(len(action['ssh_comands']))]))
            update_domain_status('Failed', id_domain, detail='new disk create operation failed, details in logs')

    elif action['type'] == 'delete_disk':
        if len(array_out_err[0]['err']) > 0:
            log.error('disk from domain {} not found, or permission denied or access to data problems'.format(id_domain))
            log.error('ERROR: {}'.format(array_out_err[0]['err']))
            update_domain_status('Failed', id_domain, detail='delete disk operation failed, disk not found: {}'.format(array_out_err[0]['err']))
        elif len(array_out_err[0]['err']) > 0:
            log.error('disk from domain {} found, but erase command fail'.format(id_domain))
            log.error('ERROR: {}'.format(array_out_err[0]['err']))
            update_domain_status('Failed', id_domain, detail='delete disk command failed')
        elif len(array_out_err[2]['out']) > 0:
            log.error('disk from domain {} found, erase command not failed with error message, but disk is in directory.'.format(id_domain))
            log.error('ERROR: {}'.format(array_out_err[0]['out']))
            update_domain_status('Failed', id_domain, detail='delete disk operation failed, disk in directory can not erase')
        else:
            log.info('disk {} from domain {} erased'.format(disk_path,id_domain))
            update_disk_backing_chain(id_domain, index_disk, 'DISK_ERASED', [])
            update_domain_status('DiskDeleted', id_domain, detail='delete disk operation run ok')


def launch_action_create_template_disk(action, hostname, user, port):
    path_template_disk = action['path_template_disk']
    path_domain_disk = action['path_domain_disk']
    id_domain = action['id_domain']
    disk_index = action['disk_index']

    cmds1,cmds2, cmds3 = create_cmds_disk_template_from_domain(path_template_disk,path_domain_disk)

    # cmds1: Firsts commands: test if perms, df, files are ok
    cmds_done = execute_commands(hostname, cmds1, dict_mode=True, user=user, port=port)
    error_severity, move_tool, cmd_to_move = verify_output_cmds1_template_from_domain(cmds_done,
                                                                                      path_domain_disk,
                                                                                      path_template_disk,
                                                                                      id_domain)
    if error_severity == None:

        # move file
        if move_tool == 'mv':
            execute_commands([cmd_to_move])
        if move_tool == 'rsync':
            execute_command_with_progress(hostname=hostname,
                                          ssh_command=cmd_to_move,
                                          id_domain=id_domain,
                                          user=user,
                                          port=port)

        # cmds2: Seconds commands: test if perms, df, files are ok
        cmds_done = execute_commands(hostname, cmds2, dict_mode=True, user=user, port=port)
        error = verify_output_cmds2(cmds_done,path_domain_disk,path_template_disk,id_domain)
        if error is None:

            cmds_done = execute_commands(hostname, cmds3, dict_mode=True, user=user, port=port)
            error, backing_chain_domain, backing_chain_template = verify_output_cmds3(cmds_done,path_domain_disk,path_template_disk,id_domain)
            if error is None:
                #update_domain to status: TemplateDiskCreated
                #####  CREATED OK ######

                update_disk_template_created(id_domain,disk_index)
                update_disk_backing_chain(id_domain,
                                          disk_index,
                                          path_template_disk,
                                          backing_chain_template,
                                          new_template=True,
                                          list_backing_chain_template=backing_chain_template)

                update_domain_status(status='TemplateDiskCreated',
                                     id_domain=id_domain,
                                     hyp_id=False,
                                     detail='new template disk {} for template created from domain {}'.format(path_template_disk,id_domain))

            else:
                update_domain_status('Crashed',id_domain,detail='new template disk from domain {} ok, but domain and disk is unknown, details in logs'.format(id_domain))
        else:
            if error == 'Crashed':
                update_domain_status('Crashed',id_domain,detail='new template from domain {} failed and disk is unknown, details in logs'.format(id_domain))
            else:
                update_domain_status('Stopped',id_domain,detail='new template from domain {} failed, disk domain remain in place, details in logs'.format(id_domain))
    else:
        update_domain_status('Stopped',id_domain,detail='new template from domain {} failed, details in logs'.format(id_domain))


class DiskOperationsThread(threading.Thread):
    def __init__(self, name, hyp_id,hostname,queue_actions,user='root',port=22,queue_master=None):
        threading.Thread.__init__(self)
        self.name = name
        self.hyp_id = hyp_id
        self.hostname = hostname
        self.user = user
        self.port = port
        self.stop = False
        self.queue_actions = queue_actions
        self.queue_master = queue_master

    def run(self):
        self.tid = get_tid()
        log.info('starting thread: {} (TID {})'.format(self.name,self.tid))
        self.disk_operations_thread()

    def disk_operations_thread(self):
        host = self.hostname
        self.tid = get_tid()
        log.debug('Thread to launchdisks operations in host {} with TID: {}...'.format(host, self.tid))


        while self.stop is not True:
            try:
                action=self.queue_actions.get(timeout=TIMEOUT_QUEUES)
                # for ssh commands
                if action['type'] in ['create_disk']:
                    launch_action_disk(action,
                                       self.hostname,
                                       self.user,
                                       self.port)
                if action['type'] in ['delete_disk']:
                    launch_delete_disk_action( action,
                                               self.hostname,
                                               self.user,
                                               self.port)

                elif action['type'] in ['create_template_disk_from_domain']:
                    launch_action_create_template_disk(action,
                                       self.hostname,
                                       self.user,
                                       self.port)

                elif action['type'] == 'stop_thread':
                    self.stop = True
                else:
                    log.debug('type action {} not supported')
            except queue.Empty:
                pass
            except Exception as e:
                log.error('Exception when creating disk template: {}'.format(e))
                return False

        if self.stop is True:
            while self.queue_actions.empty() is not True:
                action=self.queue_actions.get(timeout=TIMEOUT_QUEUES)
                if action['type'] == 'create_disk':
                    disk_path = action['disk_path']
                    id_domain = action['domain']
                    log.error('operations creating disk {} for new domain {} failed. Commands, outs and errors: {}'.format(disk_path,id_domain))
                    log.error('\n'.join(['cmd: {}'.format(action['ssh_comands'][i]) for i in range(len(action['ssh_comands']))]))
                    update_domain_status('Failed',id_domain,detail='new disk create operation failed, thread disk operations is stopping, detail of operations cancelled in logs')


class HypWorkerThread(threading.Thread):
    def __init__(self, name, hyp_id,queue_actions,queue_master=None):
        threading.Thread.__init__(self)
        self.name = name
        self.hyp_id = hyp_id
        self.stop = False
        self.queue_actions = queue_actions
        self.queue_master = queue_master

    def run(self):
        self.tid = get_tid()
        log.info('starting thread: {} (TID {})'.format(self.name,self.tid))
        host,port,user = get_hyp_hostname_from_id(self.hyp_id)
        port = int(port)
        self.hostname = host
        self.h = hyp(self.hostname,user=user,port=port)
        self.h.get_hyp_info()
        update_db_hyp_info(self.hyp_id,self.h.info)
        hyp_id = self.hyp_id

        while self.stop is not True:
            try:
                #do={type:'start_domain','xml':'xml','id_domain'='prova'}
                action=self.queue_actions.get(timeout=TIMEOUT_QUEUES)

                log.debug('recibe {}'.format(action['type']))


                if action['type'] == 'start_paused_domain':
                    log.debug('xml to start some lines...: {}'.format(action['xml'][30:100]))
                    try:
                        self.h.conn.createXML(action['xml'],flags=VIR_DOMAIN_START_PAUSED)
                        # 32 is the constant for domains paused
                        # reference: https://libvirt.org/html/libvirt-libvirt-domain.html#VIR_CONNECT_LIST_DOMAINS_PAUSED
                        FLAG_LIST_DOMAINS_PAUSED=32
                        if len([d for d in self.h.conn.listAllDomains(FLAG_LIST_DOMAINS_PAUSED) if d.name() == action['id_domain']]) == 1:
                            #domain started in pause mode
                            domain = [d for d in self.h.conn.listAllDomains(FLAG_LIST_DOMAINS_PAUSED) if d.name() == action['id_domain']][0]
                            if domain.destroy() == 0:
                                #domain is destroyed, all ok
                                update_domain_status('Stopped',action['id_domain'],hyp_id=self.hyp_id,detail='Domain is created, ready to use')
                                log.debug('domain {} creating operation finalished. Started paused and destroyed in hypervisor {}. Now status is Stopped. READY TO USE'.format(action['id_domain'],self.hyp_id))

                                if action['id_domain'].find('_disposable_') == 0:
                                    update_domain_status('Starting', action['id_domain'],
                                                         detail='Disposable domain starting')
                            else:
                                update_domain_status('Crashed',action['id_domain'],hyp_id=self.hyp_id,
                                                     detail='Domain is created, started in pause mode but not destroyed,creating domain operation is aborted')
                                log.error('domain {} started paused but not destroyed in hypervisor {}, must be destroyed'.format(action['id_domain'],self.hyp_id))
                        else:
                            update_domain_status('Crashed',action['id_domain'],hyp_id=self.hyp_id,
                                                 detail='XML for domain {} can not start in pause mode in hypervisor {}, creating domain operation is aborted by unknown cause'.format(action['id_domain'],self.hyp_id))
                            log.error('XML for domain {} can not start in pause mode in hypervisor {}, creating domain operation is aborted, not exception, rare case, unknown cause'.format(action['id_domain'],self.hyp_id))

                    except libvirtError as e:
                        from pprint import pformat
                        error_msg = pformat(e.get_error_message())

                        update_domain_status('FailedCreatingDomain',action['id_domain'],hyp_id=self.hyp_id,detail='domain {} failed when try to start in pause mode in hypervisor {}. creating domain operation is aborted')
                        log.error('Exception in libvirt starting paused xml for domain {} in hypervisor {}. Exception message: {} '.format(action['id_domain'],self.hyp_id,error_msg))

                    except Exception as e:
                        update_domain_status('Crashed',action['id_domain'],hyp_id=self.hyp_id,detail='domain {} failed when try to start in pause mode in hypervisor {}. creating domain operation is aborted')
                        log.error('Exception starting paused xml for domain {} in hypervisor {}. NOT LIBVIRT EXCEPTION, RARE CASE. Exception message: '.format(str(e)))

                ## START DOMAIN
                elif action['type'] == 'start_domain':
                    log.debug('xml to start some lines...: {}'.format(action['xml'][30:100]))
                    try:
                        self.h.conn.createXML(action['xml'])
                        update_domain_status('Started',action['id_domain'],hyp_id=self.hyp_id,detail='')
                        log.debug('STARTED domain {}: createdXML action in hypervisor {} has been sent'.format(action['id_domain'],host))
                    except Exception as e:
                        update_domain_status('Failed', action['id_domain'], hyp_id=self.hyp_id, detail=str(e))
                        log.debug('exception in starting domain {}: '.format(e))

                ## STOP DOMAIN
                elif action['type'] == 'stop_domain':
                    log.debug('action stop domain: {}'.format(action['id_domain'][30:100]))
                    try:
                        self.h.conn.lookupByName(action['id_domain']).destroy()
                        update_domain_status('Stopped',action['id_domain'])
                        log.debug('STOPPED domain {}'.format(action['id_domain']))
                    except Exception as e:
                        update_domain_status('Failed',action['id_domain'], hyp_id=self.hyp_id, detail=str(e))
                        log.debug('exception in stopping domain {}: '.format(e))

                elif action['type'] in ['create_disk', 'delete_disk']:
                    launch_action_disk(action,
                                       self.hostname,
                                       user,
                                       port)

                    # ## DESTROY THREAD
                    # elif action['type'] == 'destroy_thread':
                    #     list_works_in_queue = list(self.queue_actions.queue)
                    #     if self.queue_master is not None:
                    #         self.queue_master.put(['destroy_working_thread',self.hyp_id,list_works_in_queue])
                    #     #INFO TO DEVELOPER, si entra aquí es porque no quedaba nada en cola, si no ya lo habrán matado antes
                    #
                    #     log.error('thread worker from hypervisor {} exit from error status'.format(hyp_id))
                    #

                    #raise 'destoyed'

                elif action['type'] == 'create_disk':


                    pass


                elif action['type'] == 'hyp_info':
                    self.h.get_hyp_info()
                    log.debug('hypervisor motherboard: {}'.format(self.h.info['motherboard_manufacturer']))

                ## DESTROY THREAD
                elif action['type'] == 'stop_thread':
                    self.stop = True
                else:
                    log.debug('type action {} not supported in queue actions'.format(action['type']))
                    #time.sleep(0.1)
                    ## TRY DOMAIN


            except queue.Empty:
                try:
                    self.h.conn.getLibVersion()
                    pass
                    #log.debug('hypervisor {} is alive'.format(host))
                except:
                    log.info('trying to reconnect hypervisor {}, alive test in working thread failed'.format(host))
                    alive = False
                    for i in range(RETRIES_HYP_IS_ALIVE):
                        try:
                            time.sleep(TIMEOUT_BETWEEN_RETRIES_HYP_IS_ALIVE)
                            self.h.conn.getLibVersion()
                            alive=True
                            log.info('hypervisor {} is alive'.format(host))
                            break
                        except:
                            log.info('hypervisor {} is NOT alive'.format(host))
                    if alive is False:
                        try:
                            self.h.connect_to_hyp()
                            self.h.conn.getLibVersion()
                        except:
                            log.debug('hypervisor {} failed'.format(host))
                            log.error('fail reconnecting to hypervisor {} in working thread'.format(host))
                            reason = self.h.fail_connected_reason
                            update_hyp_status(self.hyp_id,'Error',reason)
                            update_domains_started_in_hyp_to_unknown(self.hyp_id)

                            list_works_in_queue = list(self.queue_actions.queue)
                            if self.queue_master is not None:
                                self.queue_master.put(['error_working_thread',self.hyp_id,list_works_in_queue])
                            log.error('thread worker from hypervisor {} exit from error status'.format(hyp_id))
                            self.active = False
                            break



def launch_thread_worker(hyp_id,queue_master=None):
    log.debug('launching thread wordker for hypervisor: {}'.format(hyp_id))
    q = queue.Queue()
    # t = threading.Thread(name='worker_'+hyp_id,target=hyp_worker_thread, args=(hyp_id,q,queue_master))
    t = HypWorkerThread(name='worker_'+hyp_id,
                        hyp_id=hyp_id,
                        queue_actions=q,
                        queue_master=queue_master)
    t.daemon = True
    t.start()
    return t,q



def launch_try_hyps(dict_hyps,enabled_thread=True):

    # launch try_hyp_connection_thread for all hyps
    threads_try={}
    hyps={}
    for hyp_id,dict_hyp_parameters in dict_hyps.items():
        #update_hyp_status(hyp_id, 'TryConnection')
        hostname = dict_hyp_parameters['hostname']
        port = dict_hyp_parameters['port']
        user = dict_hyp_parameters['user']
        if enabled_thread == True:
            threads_try[hyp_id] = try_hyp_connection_thread('try_' + hyp_id,
                                                            hyp_id,
                                                            hostname,
                                                            port=port,
                                                            user=user)
            threads_try[hyp_id].start()
        else:
            hyps[hyp_id],ok = try_hyp_connection(hyp_id,hostname)

    return_state={}
    for hyp_id,hostname in dict_hyps.items():
        return_state[hyp_id]={}
        TIMEOUT_TRY_HYP = CONFIG_DICT['TIMEOUTS']['timeout_trying_hyp_and_ssh']

        if enabled_thread == True:
            if threads_try[hyp_id].is_alive() is True:
                pass
            threads_try[hyp_id].join(timeout = TIMEOUT_TRY_HYP)
            hyps[hyp_id]=threads_try[hyp_id].hyp_obj
        try:
            return_state[hyp_id]['reason'] = hyps[hyp_id].fail_connected_reason
        except Exception as e:
            log.error('try hypervisor fail - reason: {}'.format(e))
            return_state[hyp_id]['reason'] = 'threads_try fail {}'.format(e)



    return return_state

def hyp_from_hyp_id(hyp_id):
    try:
        host,port,user = get_hyp_hostname_from_id(hyp_id)
        h = hyp(host,user=user,port=port)
        return h
    except:
        return False

def set_domains_coherence(dict_hyps_ready):
    for hyp_id,hostname in dict_hyps_ready.items():
        hyp_obj = hyp_from_hyp_id(hyp_id)
        try:
            hyp_obj.get_domains()
        except:
            log.error('hypervisor {} can not get domains'.format(hyp_id))
            update_hyp_status(hyp_id, 'Error')
            break
        #update domain_status
        update_all_domains_status(reset_status='Stopped',from_status=['Starting'])
        update_all_domains_status(reset_status='Started',from_status=['Stopping'])
        domains_started_in_rethink = get_domains_started_in_hyp(hyp_id)
        domains_are_started = []

        for domain_name,domain_obj in hyp_obj.domains.items():
            domain_state_libvirt = domain_obj.state()
            state,reason = state_and_cause_to_str(domain_state_libvirt[0],domain_state_libvirt[1])
            status_isard = dict_domain_libvirt_state_to_isard_state[state]
            update_domain_status(status=status_isard,id_domain=domain_name,hyp_id=hyp_id,detail=reason)
            domains_are_started.append(domain_name)

        if len(domains_started_in_rethink) > 0:
            domains_are_shutdown = list(set(domains_started_in_rethink).difference(set(domains_are_started)))
            for domain_stopped in domains_are_shutdown:
                update_domain_status(status='Stopped',id_domain=domain_stopped)
        #TODO INFO TO DEVELOPER: faltaría revisar que ningún dominio está duplicado en y started en dos hypervisores
        # a nivel de libvirt, porque a nivel de rethink es imposible, y si pasa poner un erroraco gigante
        # a parte de dejarlo en unknown

        update_hyp_status(hyp_id, 'ReadyToStart')




def try_hyp_connection(hyp_id,hostname,port,user):
    update_hyp_status(hyp_id, 'TryConnection')
    log.debug( 'Starting trying to connect to hypervisor {} '.format(hostname))
    # INFO TO DEVELOPER, VOLVER A ACTIVAR CUANDO NO FALLE LA AUTENTICACIÓN CON ALGORITMOS MODERNOS DE SSH
    # hyp_obj = hyp(hostname,user=user,port=port,try_ssh_autologin=True)
    hyp_obj = hyp(hostname,user=user,port=port,try_ssh_autologin=True)
    log.debug('####@@@@$$$$$$$$$$$$$$$$')
    log.debug('hostname: {} , reason: {}'.format(hostname,hyp_obj.fail_connected_reason))
    try:
        reason = hyp_obj.fail_connected_reason
    except Exception as e:
        log.error('try hyp {}, error: {}'.format(hyp_id,e))
        reason = 'no reason available'


    update_hypervisor_failed_connection(hyp_id,reason)
    if hyp_obj.connected is True:
        ok = True
        log.debug('hypervisor {} ready'.format(hyp_id))
        update_hyp_status(hyp_id, 'ReadyToStart')
        hyp_obj.disconnect()
    else:
        ok = False
        log.error('hypervisor {} failed when trying to connect'.format(hyp_id))
        log.error('fail_connected_reason: {}'.format(reason))
        update_hyp_status(hyp_id, 'Error',detail=reason)

    return hyp_obj,ok

class try_hyp_connection_thread (threading.Thread):

    def __init__(self, name, hyp_id, hostname,port,user):
        threading.Thread.__init__(self)
        self.name = name
        self.hyp_id = hyp_id
        self.hostname = hostname
        self.port = port
        self.user = user

    def run(self):
        self.tid = get_tid()
        log.info('starting thread: {} (TID {})'.format(self.name,self.tid))

        self.hyp_obj,self.ok=try_hyp_connection(self.hyp_id,self.hostname,self.port,self.user)

        log.debug('Exiting from thread {} try_hyp {}'.format(self.name, self.hostname))

        return self.ok


