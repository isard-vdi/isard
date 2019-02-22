# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import pprint
# /bin/python3
# coding=utf-8
import queue
import threading
import time
import traceback

from engine.models.hyp import hyp
from engine.services.db import update_all_domains_status, update_disk_backing_chain, update_disk_template_created, \
    get_domains_started_in_hyp, update_domains_started_in_hyp_to_unknown, remove_media
from engine.services.db.downloads import update_status_media_from_path
from engine.services.db.db import update_table_field
from engine.services.db.domains import update_domain_status, update_domain_parents
from engine.services.db.hypervisors import update_hyp_status, get_hyp_hostname_from_id, \
    update_hypervisor_failed_connection, update_db_hyp_info
from engine.services.lib.functions import dict_domain_libvirt_state_to_isard_state, state_and_cause_to_str, \
    execute_commands, \
    execute_command_with_progress, get_tid
from engine.services.lib.qcow import extract_list_backing_chain, create_cmds_disk_template_from_domain, \
    verify_output_cmds1_template_from_domain, verify_output_cmds2, verify_output_cmds3
from engine.services.log import *

# from pool_hypervisors. import PoolHypervisors

TIMEOUT_QUEUES = float(CONFIG_DICT["TIMEOUTS"]["timeout_queues"])
TIMEOUT_BETWEEN_RETRIES_HYP_IS_ALIVE = float(CONFIG_DICT["TIMEOUTS"]["timeout_between_retries_hyp_is_alive"])
RETRIES_HYP_IS_ALIVE = int(CONFIG_DICT["TIMEOUTS"]["retries_hyp_is_alive"])


def create_disk_action_dict(id_domain, path_template_disk, path_domain_disk, disk_index_in_bus=0):
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
        threads_log.debug('Thread running: {}'.format(i))
    return e


def launch_disk_operations_thread(hyp_id, hostname, user='root', port=22):
    if hyp_id is False:
        return False, False

    queue_disk_operation = queue.Queue()
    # thread_disk_operation = threading.Thread(name='disk_op_'+id,target=disk_operations_thread, args=(host_disk_operations,queue_disk_operation))
    thread_disk_operation = DiskOperationsThread(name='disk_op_' + hyp_id,
                                                 hyp_id=hyp_id,
                                                 hostname=hostname,
                                                 queue_actions=queue_disk_operation,
                                                 user=user,
                                                 port=port)
    thread_disk_operation.daemon = True
    thread_disk_operation.start()
    return thread_disk_operation, queue_disk_operation


def launch_long_operations_thread(hyp_id, hostname, user='root', port=22):
    if hyp_id is False:
        return False, False

    queue_long_operation = queue.Queue()
    thread_long_operation = LongOperationsThread(name='long_op_' + hyp_id,
                                                 hyp_id=hyp_id,
                                                 hostname=hostname,
                                                 queue_actions=queue_long_operation,
                                                 user=user,
                                                 port=port)
    thread_long_operation.daemon = True
    thread_long_operation.start()
    return thread_long_operation, queue_long_operation


def launch_delete_disk_action(action, hostname, user, port):
    disk_path = action['disk_path']
    id_domain = action['domain']
    array_out_err = execute_commands(hostname,
                                     ssh_commands=action['ssh_commands'],
                                     user=user,
                                     port=port)
    # ALBERTO FALTA ACABAR

    pass


def launch_action_delete_disk(action, hostname, user, port):
    disk_path = action['disk_path']
    id_domain = action['domain']
    array_out_err = execute_commands(hostname,
                                     ssh_commands=action['ssh_commands'],
                                     user=user,
                                     port=port)
    # last ls must fail
    if len([k['err'] for k in array_out_err if len(k['err']) == 1]):
        log.debug('all operations deleting  disk {} for domain {} runned ok'.format(disk_path, id_domain))

def launch_killall_curl(hostname,user,port):
    ssh_commands = ['killall curl']
    try:
        array_out_err = execute_commands(hostname,
                                     ssh_commands=ssh_commands,
                                     user=user,
                                     port=port)
        out = array_out_err[0]['out']
        err = array_out_err[0]['err']
        logs.downloads.info(f'kill al curl process in hypervisor {hostname}: {out} {err}')
        return True
    except Exception as e:
        logs.downloads.error(f'Kill all curl process in hypervisor {hostname} fail: {e}')

def launch_delete_media(action,hostname,user,port,final_status='Deleted'):
    array_out_err = execute_commands(hostname,
                                     ssh_commands=action['ssh_commands'],
                                     user=user,
                                     port=port)
    path = action['path']
    id_media = action['id_media']
    if len([k['err'] for k in array_out_err if len(k['err']) == 0]) != 2:
        log.error('failed deleting media {}'.format(id_media))
        update_status_media_from_path(path, 'FailedDeleted')
        return False
    # ls of the file after deleted failed, has deleted ok
    elif len(array_out_err[2]['err']) > 0:
        if final_status == 'DownloadFailed':
            update_status_media_from_path(path, final_status)
        else:
            update_status_media_from_path(path, 'Deleted')
        return True
    else:
        log.error('failed deleting media {}'.format(id_media))
        update_status_media_from_path(path, 'FailedDeleted')
        return False


def launch_action_disk(action, hostname, user, port, from_scratch=False):
    disk_path = action['disk_path']
    id_domain = action['domain']
    index_disk = action['index_disk']
    array_out_err = execute_commands(hostname,
                                     ssh_commands=action['ssh_commands'],
                                     user=user,
                                     port=port)

    if action['type'] in ['create_disk', 'create_disk_from_scratch']:
        if len([k['err'] for k in array_out_err if len(k['err']) == 0]):
            ##TODO: TEST WITH MORE THAN ONE DISK, 2 list_backing_chain must be created
            log.debug('all operations creating disk {} for new domain {} runned ok'.format(disk_path, id_domain))
            if from_scratch is False:
                out_cmd_backing_chain = array_out_err[-1]['out']

                list_backing_chain = extract_list_backing_chain(out_cmd_backing_chain)
                if id_domain is not False:
                    update_domain_parents(id_domain)
                    update_disk_backing_chain(id_domain, index_disk, disk_path, list_backing_chain)
                ##INFO TO DEVELOPER
            # ahora ya se puede llamar a starting paused
            if id_domain is not False:
                #update parents if have
                #update_domain_parents(id_domain)
                update_domain_status('CreatingDomain', id_domain, None,
                                     detail='new disk created, now go to creating desktop and testing if desktop start')
        else:

            log.error('operations creating disk {} for new domain {} failed.'.format(disk_path, id_domain))
            log.error('\n'.join(['cmd: {} / out: {} / err: {}'.format(action['ssh_commands'][i],
                                                                      array_out_err[i]['out'],
                                                                      array_out_err[i]['err']) for i in
                                 range(len(action['ssh_commands']))]))
            if id_domain is not False:
                update_domain_status('Failed', id_domain, detail='new disk create operation failed, details in logs')

    elif action['type'] == 'delete_disk':
        if len(array_out_err[0]['err']) > 0:
            log.error(
                'disk from domain {} not found, or permission denied or access to data problems'.format(id_domain))
            log.error('ERROR: {}'.format(array_out_err[0]['err']))
            update_domain_status('DiskDeleted', id_domain, detail='delete disk operation failed, disk not found: {}'.format(
                array_out_err[0]['err']))
        elif len(array_out_err[1]['err']) > 0:
            log.error('disk from domain {} found, but erase command fail'.format(id_domain))
            log.error('ERROR: {}'.format(array_out_err[0]['err']))
            update_domain_status('DiskDeleted', id_domain, detail='delete disk command failed')
        elif len(array_out_err[2]['out']) > 0:
            log.error(
                'disk from domain {} found, erase command not failed with error message, but disk is in directory.'.format(
                    id_domain))
            log.error('ERROR: {}'.format(array_out_err[0]['out']))
            update_domain_status('DiskDeleted', id_domain,
                                 detail='delete disk operation failed, disk in directory can not erase')
        else:
            log.info('disk {} from domain {} erased'.format(disk_path, id_domain))
            update_disk_backing_chain(id_domain, index_disk, 'DISK_ERASED', [])
            update_domain_status('DiskDeleted', id_domain, detail='delete disk operation run ok')


def  launch_action_create_template_disk(action, hostname, user, port):
    path_template_disk = action['path_template_disk']
    path_domain_disk = action['path_domain_disk']
    id_domain = action['id_domain']
    disk_index = action['disk_index']

    cmds1, cmds2, cmds3 = create_cmds_disk_template_from_domain(path_template_disk, path_domain_disk)

    # cmds1: Firsts commands: test if perms, df, files are ok
    cmds_done = execute_commands(hostname, ssh_commands=cmds1, dict_mode=True, user=user, port=port)
    error_severity, move_tool, cmd_to_move = verify_output_cmds1_template_from_domain(cmds_done,
                                                                                      path_domain_disk,
                                                                                      path_template_disk,
                                                                                      id_domain)
    if error_severity == None:

        # move file
        log.debug('commnad to move disk template: {}'.format(cmd_to_move))
        if move_tool == 'mv':
            cmds_done = execute_commands(hostname, ssh_commands=[cmd_to_move], dict_mode=False, user=user, port=port)

        if move_tool == 'rsync':
            execute_command_with_progress(hostname=hostname,
                                          ssh_command=cmd_to_move,
                                          id_domain=id_domain,
                                          user=user,
                                          port=port)

        # cmds2: Seconds commands: test if perms, df, files are ok
        cmds_done = execute_commands(hostname, ssh_commands=cmds2, dict_mode=True, user=user, port=port)
        error = verify_output_cmds2(cmds_done, path_domain_disk, path_template_disk, id_domain)
        if error is None:

            cmds_done = execute_commands(hostname, ssh_commands=cmds3, dict_mode=True, user=user, port=port)
            error, backing_chain_domain, backing_chain_template = verify_output_cmds3(cmds_done, path_domain_disk,
                                                                                      path_template_disk, id_domain)
            if error is None:
                # update_domain to status: TemplateDiskCreated
                #####  CREATED OK ######

                update_disk_template_created(id_domain, disk_index)
                update_disk_backing_chain(id_domain,
                                          disk_index,
                                          path_template_disk,
                                          backing_chain_template,
                                          new_template=True,
                                          list_backing_chain_template=backing_chain_template)

                # disk created, update parents and status
                #update_domain_parents(id_domain)
                update_domain_status(status='TemplateDiskCreated',
                                     id_domain=id_domain,
                                     hyp_id=False,
                                     detail='new template disk {} for template created from domain {}'.format(
                                         path_template_disk, id_domain))

            else:
                update_domain_status('Crashed', id_domain,
                                     detail='new template disk from domain {} ok, but domain and disk is unknown, details in logs'.format(
                                         id_domain))
        else:
            if error == 'Crashed':
                update_domain_status('Crashed', id_domain,
                                     detail='new template from domain {} failed and disk is unknown, details in logs'.format(
                                         id_domain))
            else:
                update_domain_status('Stopped', id_domain,
                                     detail='new template from domain {} failed, disk domain remain in place, details in logs'.format(
                                         id_domain))
    else:
        update_domain_status('Stopped', id_domain,
                             detail='new template from domain {} failed, details in logs'.format(id_domain))



def launch_thread_worker(hyp_id, queue_master=None):
    log.debug('launching thread wordker for hypervisor: {}'.format(hyp_id))
    q = queue.Queue()
    # t = threading.Thread(name='worker_'+hyp_id,target=hyp_worker_thread, args=(hyp_id,q,queue_master))
    t = HypWorkerThread(name='worker_' + hyp_id,
                        hyp_id=hyp_id,
                        queue_actions=q,
                        queue_master=queue_master)
    t.daemon = True
    t.start()
    return t, q


def launch_try_hyps(dict_hyps, enabled_thread=True):
    # launch TryHypConnectionThread for all hyps
    threads_try = {}
    hyps = {}
    for hyp_id, dict_hyp_parameters in dict_hyps.items():
        # update_hyp_status(hyp_id, 'TryConnection')
        hostname = dict_hyp_parameters['hostname']
        port = dict_hyp_parameters['port']
        user = dict_hyp_parameters['user']
        if enabled_thread == True:
            threads_try[hyp_id] = TryHypConnectionThread('try_' + hyp_id,
                                                            hyp_id,
                                                            hostname,
                                                            port=port,
                                                            user=user)
            threads_try[hyp_id].start()
        else:
            hyps[hyp_id], ok = try_hyp_connection(hyp_id, hostname)

    return_state = {}
    for hyp_id, hostname in dict_hyps.items():
        return_state[hyp_id] = {}
        TIMEOUT_TRY_HYP = CONFIG_DICT['TIMEOUTS']['timeout_trying_hyp_and_ssh']

        if enabled_thread == True:
            if threads_try[hyp_id].is_alive() is True:
                pass
            threads_try[hyp_id].join(timeout=TIMEOUT_TRY_HYP)
        try:
            hyps[hyp_id] = threads_try[hyp_id].hyp_obj
            return_state[hyp_id]['reason'] = hyps[hyp_id].fail_connected_reason
        except Exception as e:
            log.error('try hypervisor fail - reason: {}'.format(e))
            return_state[hyp_id]['reason'] = 'threads_try fail {}'.format(e)

    return return_state


def hyp_from_hyp_id(hyp_id):
    try:
        host, port, user = get_hyp_hostname_from_id(hyp_id)
        h = hyp(host, user=user, port=port)
        return h
    except:
        return False


def set_domains_coherence(dict_hyps_ready):
    for hyp_id, hostname in dict_hyps_ready.items():
        hyp_obj = hyp_from_hyp_id(hyp_id)
        try:
            hyp_obj.get_domains()
        except:
            log.error('hypervisor {} can not get domains'.format(hyp_id))
            update_hyp_status(hyp_id, 'Error')
            break
        # update domain_status
        update_all_domains_status(reset_status='Stopped', from_status=['Starting'])
        update_all_domains_status(reset_status='Started', from_status=['Stopping'])
        domains_started_in_rethink = get_domains_started_in_hyp(hyp_id)
        domains_are_started = []

        for domain_name, domain_obj in hyp_obj.domains.items():
            domain_state_libvirt = domain_obj.state()
            state, reason = state_and_cause_to_str(domain_state_libvirt[0], domain_state_libvirt[1])
            status_isard = dict_domain_libvirt_state_to_isard_state[state]
            update_domain_status(status=status_isard, id_domain=domain_name, hyp_id=hyp_id, detail=reason)
            domains_are_started.append(domain_name)

        if len(domains_started_in_rethink) > 0:
            domains_are_shutdown = list(set(domains_started_in_rethink).difference(set(domains_are_started)))
            for domain_stopped in domains_are_shutdown:
                update_domain_status(status='Stopped', id_domain=domain_stopped, hyp_id='')
        # TODO INFO TO DEVELOPER: faltaría revisar que ningún dominio está duplicado en y started en dos hypervisores
        # a nivel de libvirt, porque a nivel de rethink es imposible, y si pasa poner un erroraco gigante
        # a parte de dejarlo en unknown

        update_hyp_status(hyp_id, 'ReadyToStart')


def try_hyp_connection(hyp_id, hostname, port, user):
    update_hyp_status(hyp_id, 'TryConnection')
    log.debug('Starting trying to connect to hypervisor {} '.format(hostname))
    # INFO TO DEVELOPER, VOLVER A ACTIVAR CUANDO NO FALLE LA AUTENTICACIÓN CON ALGORITMOS MODERNOS DE SSH
    # hyp_obj = hyp(hostname,user=user,port=port,try_ssh_autologin=True)
    hyp_obj = hyp(hostname, user=user, port=port, try_ssh_autologin=True)
    log.debug('####@@@@$$$$$$$$$$$$$$$$')
    log.debug('hostname: {} , reason: {}'.format(hostname, hyp_obj.fail_connected_reason))
    try:
        reason = hyp_obj.fail_connected_reason
    except Exception as e:
        log.error('try hyp {}, error: {}'.format(hyp_id, e))
        reason = 'no reason available'

    update_hypervisor_failed_connection(hyp_id, reason)
    if hyp_obj.connected is True:
        log.debug('hypervisor {} libvirt connection ready'.format(hyp_id))
        hyp_obj.get_kvm_mod()
        hyp_obj.get_hyp_info()
        update_db_hyp_info(hyp_id,hyp_obj.info)
        if hyp_obj.info['kvm_module'] == 'intel' or  hyp_obj.info['kvm_module'] == 'amd':
            ok = True
            update_hyp_status(hyp_id, 'ReadyToStart')
        else:
            ok = False
            log.error('hypervisor {} has not virtualization support (VT-x for Intel processors and AMD-V for AMD processors). '.format(hyp_id))
            update_hyp_status(hyp_id, 'Error', detail="KVM requires that the virtual machine host's processor has virtualization " +
                                                      "support (named VT-x for Intel processors and AMD-V for AMD processors). " +
                                                      "Check CPU capabilities and enable virtualization support in your BIOS.")
        hyp_obj.disconnect()
    else:
        ok = False
        log.error('hypervisor {} failed when trying to connect'.format(hyp_id))
        log.error('fail_connected_reason: {}'.format(reason))
        update_hyp_status(hyp_id, 'Error', detail=reason)

    return hyp_obj, ok

# IMPORT Thread Classes HERE
from engine.services.threads.disk_operations_thread import DiskOperationsThread
from engine.services.threads.hyp_worker_thread import HypWorkerThread
from engine.services.threads.long_operations_thread import LongOperationsThread
from engine.services.threads.try_hyp_connection_thread import TryHypConnectionThread
