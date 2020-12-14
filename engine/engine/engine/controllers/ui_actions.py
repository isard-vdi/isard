# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# /bin/python3
# coding=utf-8

import itertools
import time
import traceback
from os.path import dirname as extract_dir_path
# from qcow import create_disk_from_base, backing_chain, create_cmds_disk_from_base
from time import sleep

from engine.models.domain_xml import DomainXML, update_xml_from_dict_domain, populate_dict_hardware_from_create_dict
from engine.models.domain_xml import recreate_xml_to_start, BUS_TYPES
from engine.services.db import update_domain_viewer_started_values, update_table_field, \
    get_interface, update_domain_hyp_started, update_domain_hyp_stopped, get_domain_hyp_started, \
    update_domain_dict_hardware, remove_disk_template_created_list_in_domain, remove_dict_new_template_from_domain, \
    create_disk_template_created_list_in_domain, get_pool_from_domain, get_domain, insert_domain, delete_domain, \
    update_domain_status, get_domain_forced_hyp, get_hypers_in_pool, get_domain_kind, get_if_delete_after_stop, \
    get_dict_from_item_in_table, update_domain_dict_create_dict, update_origin_and_parents_to_new_template, \
    get_custom_dict_from_domain, update_domain_forced_hyp, get_domain_force_update, update_domain_force_update
from engine.services.lib.functions import exec_remote_list_of_cmds
from engine.services.lib.qcow import create_cmd_disk_from_virtbuilder, get_host_long_operations_from_path
from engine.services.lib.qcow import create_cmds_disk_from_base, create_cmds_delete_disk, get_path_to_disk, \
    get_host_disk_operations_from_path, create_cmd_disk_from_scratch, add_cmds_if_custom
from engine.services.log import *

DEFAULT_HOST_MODE = 'host-passthrough'

class UiActions(object):
    def __init__(self, manager):
        log.info("Backend uiactions created")
        self.manager = manager
        self.round_robin_index_non_persistent = 0

    def action_from_api(self, action, parameters):
        if action == 'start_domain':

            if 'ssl' in parameters.keys() and parameters['ssl'] == False:
                ssl_spice = False
            if 'domain_id' in parameters.keys():
                self.start_domain_from_id(parameters['domain_id'], ssl_spice)



    ### STARTING DOMAIN
    def start_domain_from_id(self, id, ssl=True):
        # INFO TO DEVELOPER, QUE DE UN ERROR SI EL ID NO EXISTE

        id_domain = id
        pool_id = get_pool_from_domain(id_domain)
        cpu_host_model = self.manager.pools[pool_id].conf.get('cpu_host_model',DEFAULT_HOST_MODE)

        if get_domain_force_update(id_domain):
            if self.update_hardware_dict_and_xml_from_create_dict(id_domain):
                update_domain_force_update(id_domain,False)
            else:
                return False


        try:
            xml = recreate_xml_to_start(id_domain, ssl, cpu_host_model)
        except Exception as e:
            log.error('recreate_xml_to_start in domain {}'.format(id_domain))
            log.error('Traceback: \n .{}'.format(traceback.format_exc()))
            log.error('Exception message: {}'.format(e))
            xml = False

        if xml is False:
            update_domain_status('Failed', id_domain,
                                 detail="DomainXML can not parse and modify xml to start")
            return False
        else:
            hyp = self.start_domain_from_xml(xml, id_domain, pool_id=pool_id)
            return hyp

    def start_paused_domain_from_xml(self, xml, id_domain, pool_id):
    #def start_paused_domain_from_xml(self, xml, id_domain, pool_id, start_after_created=False):

        failed = False
        if pool_id in self.manager.pools.keys():
            next_hyp = self.manager.pools[pool_id].get_next(domain_id=id_domain)
            log.debug('//////////////////////')
            if next_hyp is not False:
                log.debug('next_hyp={}'.format(next_hyp))
                dict_action = {'type': 'start_paused_domain', 'xml': xml, 'id_domain': id_domain}
                # if start_after_created is True:
                #     dict_action['start_after_created'] = True
                #else:

                if LOG_LEVEL == 'DEBUG':
                    print(f'%%%% DOMAIN CREATING:{id_domain} -- XML TO START PAUSED IN HYPERVISOR {next_hyp} %%%%')
                    print(xml)
                    update_table_field('domains', id_domain, 'xml_to_start', xml)
                    print('%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%')

                self.manager.q.workers[next_hyp].put(
                    dict_action)
                update_domain_status(status='CreatingDomain',
                                     id_domain=id_domain,
                                     hyp_id=False,
                                     detail='Waiting to try starting paused in hypervisor {} in pool {} ({} operations in queue)'.format(
                                         next_hyp,
                                         pool_id,
                                         self.manager.q.workers[next_hyp].qsize()))
            else:
                log.error('get next hypervisor in pool {} failed'.format(pool_id))
                failed = True
        else:
            log.error('pool_id {} does not exists??'.format(pool_id))
            failed = True

        if failed is True:
            update_domain_status(status='FailedCreatingDomain',
                                 id_domain=id_domain,
                                 hyp_id=next_hyp,
                                 detail='desktop not started: no hypervisors online in pool {}'.format(pool_id))

            log.error('desktop not started: no hypervisors online in pool {}'.format(pool_id))
            return False
        else:
            return next_hyp

    def start_domain_from_xml(self, xml, id_domain, pool_id='default'):
        failed = False
        if pool_id in self.manager.pools.keys():
            forced_hyp = get_domain_forced_hyp(id_domain)
            if forced_hyp is not False:
                hyps_in_pool = get_hypers_in_pool(pool_id, only_online=False)
                if forced_hyp in hyps_in_pool:
                    next_hyp = forced_hyp
                else:
                    log.error('force hypervisor failed for doomain {}: {}  not in hypervisors pool {}'.format(id_domain,
                                                                                                              forced_hyp,
                                                                                                              pool_id))
                    next_hyp = self.manager.pools[pool_id].get_next(domain_id=id_domain)
            else:
                next_hyp = self.manager.pools[pool_id].get_next(domain_id=id_domain)

            if next_hyp is not False:
                # update_domain_status(status='Starting',
                #                      id_domain=id_domain,
                #                      hyp_id=next_hyp,
                #                      detail='desktop starting paused in pool {} on hypervisor {}'.format(pool_id,
                #                                                                                          next_hyp))

                if LOG_LEVEL == 'DEBUG':
                    print(f'%%%% DOMAIN: {id_domain} -- XML TO START IN HYPERVISOR: {next_hyp} %%%%')
                    ##print(xml)
                    update_table_field('domains',id_domain,'xml_to_start',xml)
                    print('%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%')

                self.manager.q.workers[next_hyp].put({'type': 'start_domain', 'xml': xml, 'id_domain': id_domain})
            else:
                log.error('get next hypervisor in pool {} failed'.format(pool_id))
                failed = True
        else:
            log.error('pool_id {} does not exists??'.format(pool_id))
            failed = True

        if failed is True:
            update_domain_status(status='Failed',
                                 id_domain=id_domain,
                                 hyp_id=next_hyp,
                                 detail='desktop not started: no hypervisors online in pool {}'.format(pool_id))

            log.error('desktop not started: no hypervisors online in pool {}'.format(pool_id))
            return False
        else:
            return next_hyp

    def destroy_domain_from_id(self, id):
        pass

    def stop_domain_from_id(self, id):
        # INFO TO DEVELOPER. puede pasar que alguna actualización en algún otro hilo del status haga que
        # durante un corto período de tiempo devuelva None,para evitarlo durante un segundo vamos a ir pidiendo cada
        # 100 ms que nos de el hypervisor
        time_wait = 0.0
        while time_wait <= 20.0:

            hyp_id = get_domain_hyp_started(id)
            if hyp_id != None:
                if len(hyp_id) > 0:
                    break
            else:
                time_wait = time_wait + 0.1
                sleep(0.1)
                log.debug('waiting {} seconds to find hypervisor started for domain {}'.format(time_wait, id))
        log.debug('stop domain id {} in {}'.format(id, hyp_id))
        # hyp_id = get_domain_hyp_started(id)
        # log.debug('stop domain id {} in {}'.format(id,hyp_id))
        if hyp_id is None:
            hyp_id = ''
        if len(hyp_id) <= 0:
            log.debug('hypervisor where domain {} is started not finded'.format(id))
            update_domain_status(status='Unknown',
                                 id_domain=id_domain,
                                 hyp_id=None,
                                 detail='hypervisor where domain {} is started not finded'.format(id))
        else:
            self.stop_domain(id, hyp_id)

    def stop_domain(self, id_domain, hyp_id, delete_after_stopped=False):
        update_domain_status(status='Stopping',
                             id_domain=id_domain,
                             hyp_id=hyp_id,
                             detail='desktop stopping in hyp {}'.format(hyp_id))

        from pprint import pprint
        action = {'type': 'stop_domain',
                  'id_domain': id_domain,
                  'delete_after_stopped': delete_after_stopped}

        self.manager.q.workers[hyp_id].put(action)
        return True



    def delete_domain(self, id_domain):
        pass

    # quitar también las estadísticas y eventos

    def delete_template(self, id_template):
        pass

    # return false si hay alguna derivada

    def update_template(self,
                        id_template,
                        name,
                        description,
                        cpu,
                        ram,
                        id_net=None,
                        force_server=None):
        pass

    def update_domain(self,
                      id_old,
                      id_new,
                      # user,
                      # category,
                      # group,
                      name,
                      description,
                      cpu,
                      ram,
                      id_net=None,
                      force_server=None,
                      # only_cmds=False,
                      # path_to_disk_dir=None,
                      disk_filename=None):
        # INFO TO DEVELOPER: ojo al renombrar el id del dominio, Hay que eliminar y recrear el
        # dominio en rethink y cambiar el nombre del fichero que me lo pasará ui
        # la ui siempre me pasa todoas
        # si id_old == id_new solo update, si no eliminar y rehacer disco
        pass

        # alberto: comentar con josep maria,

    # en principio crea todo lo que se necesita en la base de datos
    # esta función sólo ha de crear el disco derivado donde le diga el campo de la base de datos
    # recrear el xml y verificar que se define o arranca ok
    # yo crearía el disco con una ruta relativa respecto a una variable de configuración
    # y el path que se guarda en el disco podría ser relativo, aunque igual no vale la pena...

    def deleting_disks_from_domain(self, id_domain, force=False):
        # ALBERTO FALTA ACABAR

        dict_domain = get_domain(id_domain)

        if dict_domain['kind'] != 'desktop' and force is False:
            log.info('{} is a template, disks will be deleted')
        if 'hardware' in dict_domain.keys():
            if len(dict_domain['hardware']['disks']) > 0:
                index_disk = 0
                for d in dict_domain['hardware']['disks']:

                    disk_path = d['file']
                    pool_id = dict_domain['hypervisors_pools'][0]
                    if pool_id not in self.manager.pools.keys():
                        log.error(
                            'hypervisor pool {} nor running in manager, can\'t delete disks in domain {}'.format(pool_id,
                                                                                                                 id_domain))
                        return False

                    forced_hyp = get_domain_forced_hyp(id_domain)
                    if forced_hyp is not False:
                        hyps_in_pool = get_hypers_in_pool(pool_id, only_online=False)
                        if forced_hyp in hyps_in_pool:
                            next_hyp = forced_hyp
                        else:
                            log.error('force hypervisor failed for doomain {}: {}  not in hypervisors pool {}'.format(
                                id_domain,
                                forced_hyp,
                                pool_id))
                            next_hyp = self.manager.pools[pool_id].get_next(domain_id=id_domain)
                    else:
                        next_hyp = self.manager.pools[pool_id].get_next(domain_id=id_domain)

                    log.debug('hypervisor where delete disk {}: {}'.format(disk_path, next_hyp))
                    cmds = create_cmds_delete_disk(disk_path)

                    action = dict()
                    action['id_domain'] = id_domain
                    action['type'] = 'delete_disk'
                    action['disk_path'] = disk_path
                    action['domain'] = id_domain
                    action['ssh_commands'] = cmds
                    action['index_disk'] = index_disk

                    try:

                        update_domain_status(status='DeletingDomainDisk',
                                             id_domain=id_domain,
                                             hyp_id=False,
                                             detail='Deleting disk {} in domain {}, queued in hypervisor thread {}'.format(
                                                 disk_path,
                                                 id_domain,
                                                 next_hyp
                                             ))

                        self.manager.q.workers[next_hyp].put(action)
                    except Exception as e:
                        update_domain_status(status='Stopped',
                                             id_domain=id_domain,
                                             hyp_id=False,
                                             detail='Creating template operation failed when insert action in queue for disk operations')
                        log.error(
                            'Creating disk operation failed when insert action in queue for disk operations in host {}. Exception: {}'.format(
                                next_hyp, e))
                        return False

                    index_disk += 1
            else:
                log.debug('no disk to delete in domain {}'.format(id_domain))
        else:
            log.error('no hardware dict in domain to delete {}, deleting domain but not deleted disks'.format(id_domain))
            delete_domain(id_domain)

        return True

    def create_template_disks_from_domain(self, id_domain):
        dict_domain = get_domain(id_domain)

        create_dict = dict_domain['create_dict']

        pool_var = create_dict['template_dict']['hypervisors_pools']
        pool_id = pool_var if type(pool_var) is str else pool_var[0]

        try:
            dict_new_template = create_dict['template_dict']
        except KeyError as e:
            update_domain_status(status='Stopped',
                                 id_domain=id_domain,
                                 hyp_id=False,
                                 detail='Action Creating Template from domain failed. No template_json in domain dictionary')
            log.error(
                'No template_dict in keys of domain dictionary, when creating template form domain {}. Exception: {}'.format(
                    id_domain, str(e)))
            return False

        disk_index_in_bus = 0
        if 'disks' in dict_domain['hardware']:

            list_disk_template_path_relative = [d['file'] for d in create_dict['hardware']['disks']]
            create_disk_template_created_list_in_domain(id_domain)
            for i in range(len(list_disk_template_path_relative)):
                # for disk in dict_domain['hardware']['disks']:
                path_domain_disk = dict_domain['hardware']['disks'][i]['file']

                try:
                    path_template_disk_relative = dict_new_template['create_dict']['hardware']['disks'][i]['file']
                    # path_template_disk_relative = list_disk_template_path_relative[i]
                except KeyError as e:
                    update_domain_status(status='Stopped',
                                         id_domain=id_domain,
                                         hyp_id=False,
                                         detail='Action Creating Template from domain failed. No disks in template_json in domain dictionary')
                    log.error(
                        'No disks in template_json in keys of domain dictionary, when creating template form domain {}. Exception: {}'.format(
                            id_domain, str(e)))
                    return False

                if dict_new_template['kind'] == 'base':
                    type_path_selected = 'bases'
                else:
                    type_path_selected = 'templates'

                new_file, path_selected = get_path_to_disk(path_template_disk_relative, pool=pool_id,
                                                           type_path=type_path_selected)
                path_absolute_template_disk = new_file = new_file.replace('//', '/')
                dict_new_template['create_dict']['hardware']['disks'][i]['file'] = new_file
                dict_new_template['create_dict']['hardware']['disks'][i]['path_selected'] = path_selected

                update_table_field('domains', id_domain, 'create_dict', create_dict)

                action = {}
                action['id_domain'] = id_domain
                action['type'] = 'create_template_disk_from_domain'
                action['path_template_disk'] = path_absolute_template_disk
                action['path_domain_disk'] = path_domain_disk
                action['disk_index'] = disk_index_in_bus

                hyp_to_disk_create = get_host_disk_operations_from_path(path_selected, pool=pool_id,
                                                                        type_path=type_path_selected)

                # INFO TO DEVELOPER: falta terminar de ver que hacemos con el pool para crear
                # discos, debería haber un disk operations por pool
                try:

                    update_domain_status(status='CreatingTemplateDisk',
                                         id_domain=id_domain,
                                         hyp_id=False,
                                         detail='Creating template disk operation is launched in hostname {} ({} operations in queue)'.format(
                                             hyp_to_disk_create,
                                             self.manager.q_disk_operations[hyp_to_disk_create].qsize()))
                    self.manager.q_disk_operations[hyp_to_disk_create].put(action)
                except Exception as e:
                    update_domain_status(status='Stopped',
                                         id_domain=id_domain,
                                         hyp_id=False,
                                         detail='Creating template operation failed when insert action in queue for disk operations')
                    log.error(
                        'Creating disk operation failed when insert action in queue for disk operations in host {}. Exception: {}'.format(
                            hyp_to_disk_create, e))
                    return False

                    disk_index_in_bus = disk_index_in_bus + 1

            return True

            # first: move and rename disk to templates folder

    def create_template_in_db(self, id_domain):
        domain_dict = get_domain(id_domain)
        template_dict = domain_dict['create_dict']['template_dict']
        template_dict['status'] = 'CreatingNewTemplateInDB'
        template_id = template_dict['id']
        if insert_domain(template_dict)['inserted'] == 1:
            hw_dict = domain_dict['hardware'].copy()
            for i in range(len(hw_dict['disks'])):
                hw_dict['disks'][i]['file'] = template_dict['create_dict']['hardware']['disks'][i]['file']
            update_table_field('domains', template_id, 'hardware', hw_dict, merge_dict=False)
            xml_parsed = update_xml_from_dict_domain(id_domain=template_id, xml=domain_dict['xml'])
            if xml_parsed is False:
                update_domain_status(status='Failed',
                                     id_domain=template_id,
                                     hyp_id=False,
                                     detail='XML Parser Error, xml is not valid')
                return False
            remove_disk_template_created_list_in_domain(id_domain)
            remove_dict_new_template_from_domain(id_domain)
            if 'parents' in domain_dict.keys():
                domain_parents_chain_update = domain_dict['parents'].copy()
            else:
                domain_parents_chain_update = []

            domain_parents_chain_update.append(template_id)
            update_table_field('domains', id_domain, 'parents', domain_parents_chain_update)
            update_origin_and_parents_to_new_template(id_domain,template_id)
            # update_table_field('domains', template_id, 'xml', xml_parsed, merge_dict=False)
            update_domain_status(status='Stopped',
                                 id_domain=template_id,
                                 hyp_id=False,
                                 detail='Template created, ready to create domains from this template')
            update_domain_status(status='Stopped',
                                 id_domain=id_domain,
                                 hyp_id=False,
                                 detail='Template created from this domain, now domain is ready to start again')


        else:
            log.error('template {} can not be inserted in rethink, domain_id duplicated??'.format(template_id))
            return False

    def creating_test_disk(self,test_disk_relative_route,size_str='1M',type_path='media',pool_id='default'):

        path_new_disk, path_selected = get_path_to_disk(test_disk_relative_route,
                                                                     pool=pool_id,
                                                                     type_path=type_path)

        hyp_to_disk_create = get_host_disk_operations_from_path(path_selected, pool=pool_id, type_path=type_path)

        cmds = create_cmd_disk_from_scratch(path_new_disk=path_new_disk,
                                            size_str=size_str)

        action = {}
        action['type'] = 'create_disk_from_scratch'
        action['disk_path'] = path_new_disk
        action['index_disk'] = 0
        action['domain'] = False
        action['ssh_commands'] = cmds

        self.manager.q_disk_operations[hyp_to_disk_create].put(action)

    def creating_disk_from_scratch(self,id_new):
        dict_domain = get_domain(id_new)

        pool_var = dict_domain['hypervisors_pools']
        pool_id = pool_var if type(pool_var) is str else pool_var[0]

        dict_to_create = dict_domain['create_dict']

        if 'disks' in dict_to_create['hardware'].keys():
            if len(dict_to_create['hardware']['disks']) > 0:

                # for index_disk in range(len(dict_to_create['hardware']['disks'])):
                #     relative_path = dict_to_create['hardware']['disks'][index_disk]['file']
                #     path_new_file, path_selected = get_path_to_disk(relative_path, pool=pool_id)
                #     # UPDATE PATH IN DOMAIN
                #     dict_to_create['hardware']['disks'][index_disk]['file'] = new_file
                #     dict_to_create['hardware']['disks'][index_disk]['path_selected'] = path_selected

                relative_path = dict_to_create['hardware']['disks'][0]['file']
                path_new_disk, path_selected = get_path_to_disk(relative_path, pool=pool_id)
                # UPDATE PATH IN DOMAIN

                d_update_domain = {'hardware':{'disks':[{}]}}
                if len(dict_to_create['hardware']['disks']) > 0:
                    ## supplementary disks
                    for i,dict_other_disk in enumerate(dict_to_create['hardware']['disks'][1:]):
                        path_other_disk, path_other_disk_selected = get_path_to_disk(dict_other_disk['file'],
                                                                                     pool=pool_id,
                                                                                     type_path=dict_other_disk['type_path'])
                        d_update_domain['hardware']['disks'].append({})
                        d_update_domain['hardware']['disks'][i+1]['file'] = path_other_disk
                        d_update_domain['hardware']['disks'][i+1]['path_selected'] = path_other_disk_selected
                        d_update_domain['hardware']['disks'][i + 1]['bus'] = dict_other_disk.get('bus','virtio')
                        if dict_other_disk.get('readonly',True) is True:
                            d_update_domain['hardware']['disks'][i + 1]['readonly'] = True
                        else:
                            pass
                            # TODO
                            # update_media_write_access_by_domain(id_media,id_domain)

                d_update_domain['hardware']['disks'][0]['file'] = path_new_disk
                d_update_domain['hardware']['disks'][0]['path_selected'] = path_selected
                d_update_domain['hardware']['disks'][0]['size'] = dict_to_create['hardware']['disks'][0]['size']
                if 'bus' in dict_to_create['hardware']['disks'][0].keys():
                    if dict_to_create['hardware']['disks'][0]['bus'] in BUS_TYPES:
                        d_update_domain['hardware']['disks'][0]['bus'] = dict_to_create['hardware']['disks'][0]['bus']
                update_domain_dict_hardware(id_new, d_update_domain)
                update_domain_dict_create_dict(id_new, d_update_domain)

                size_str = dict_to_create['hardware']['disks'][0]['size']

                hyp_to_disk_create = get_host_disk_operations_from_path(path_selected, pool=pool_id, type_path='groups')

                cmds = create_cmd_disk_from_scratch(path_new_disk=path_new_disk,
                                                         size_str=size_str)

                action = {}
                action['type'] = 'create_disk_from_scratch'
                action['disk_path'] = path_new_disk
                action['index_disk'] = 0
                action['domain'] = id_new
                action['ssh_commands'] = cmds
                try:
                    update_domain_status(status='CreatingDiskFromScratch',
                                         id_domain=id_new,
                                         hyp_id=False,
                                         detail='Creating disk commands are launched in hypervisor {} ({} operations in queue)'.format(
                                             hyp_to_disk_create,
                                             self.manager.q_disk_operations[hyp_to_disk_create].qsize()))
                    self.manager.q_disk_operations[hyp_to_disk_create].put(action)

                except Exception as e:
                    update_domain_status(status='FailedCreatingDomain',
                                         id_domain=id_new,
                                         hyp_id=False,
                                         detail='Creating disk operation failed when insert action in queue for disk operations')
                    log.error(
                        'Creating disk operation failed when insert action in queue for disk operations. Exception: {}'.format(
                            e))

        else:
            update_domain_status(status='CreatingDomain',
                                 id_domain=id_new,
                                 hyp_id=False,
                                 detail='Creating domain withouth disks')


    def creating_disk_from_virtbuilder(self,
                                       id_new):
        dict_domain = get_domain(id_new)

        pool_var = dict_domain['hypervisors_pools']
        pool_id = pool_var if type(pool_var) is str else pool_var[0]

        dict_to_create = dict_domain['create_dict']

        relative_path = dict_to_create['hardware']['disks'][0]['file']
        path_new_disk, path_selected = get_path_to_disk(relative_path, pool=pool_id)
        # UPDATE PATH IN DOMAIN
        dict_to_create['hardware']['disks'][0]['file'] = path_new_disk
        dict_to_create['hardware']['disks'][0]['path_selected'] = path_selected

        size_str = dict_to_create['hardware']['disks'][0]['size']
        memory_in_mb = int(dict_to_create['hardware']['memory'] / 1024)
        options_virt_builder = dict_to_create['builder']['options']
        options_virt_install = dict_to_create['install']['options']
        id_domains_virt_builder = dict_to_create['builder']['id']
        id_os_virt_install = dict_to_create['install']['id']

        # UPDATE HARDWARE DICT
        hardware_update = {}
        hardware_update['disks'] = dict_to_create['hardware']['disks']
        update_domain_dict_hardware(id_new, hardware_update)

        hyp_to_disk_create = get_host_long_operations_from_path(path_selected, pool=pool_id, type_path='groups')

        cmds = create_cmd_disk_from_virtbuilder(path_new_qcow=path_new_disk,
                                                os_version=id_domains_virt_builder,
                                                id_os_virt_install=id_os_virt_install,
                                                name_domain_in_xml=id_new,
                                                size_str=size_str,
                                                memory_in_mb=memory_in_mb,
                                                options_cmd=options_virt_builder)

        # cmds = [{'cmd':'ls -lah > /tmp/prova.txt','title':'es un ls'}]

        action = {}
        action['type'] = 'create_disk_virt_builder'
        action['disk_path'] = path_new_disk
        action['index_disk'] = 0
        action['domain'] = id_new
        action['ssh_commands'] = cmds

        try:
            update_domain_status(status='RunningVirtBuilder',
                                 id_domain=id_new,
                                 hyp_id=False,
                                 detail='Creating virt-builder image operation is launched in hypervisor {} ({} operations in queue)'.format(
                                     hyp_to_disk_create,
                                     self.manager.q_long_operations[hyp_to_disk_create].qsize()))
            self.manager.q_long_operations[hyp_to_disk_create].put(action)

        except Exception as e:
            update_domain_status(status='FailedCreatingDomain',
                                 id_domain=id_new,
                                 hyp_id=False,
                                 detail='Creating disk operation failed when insert action in queue for disk operations')
            log.error(
                'Creating disk operation failed when insert action in queue for disk operations. Exception: {}'.format(
                    e))

    def creating_disks_from_template(self,
                                     id_new):
        dict_domain = get_domain(id_new)
        persistent = dict_domain.get('persistent',True)
        if 'create_dict' in dict_domain.keys():
            dict_to_create = dict_domain['create_dict']

        pool_var = dict_domain['hypervisors_pools']
        pool_id = pool_var if type(pool_var) is str else pool_var[0]

        # INFO TO DEVELOPER DEBERÍA SER UN FOR PARA CADA DISCO
        # y si el disco no tiene backing_chain, crear un disco vacío
        # del tamño que marcase
        # d['hardware']['disks'][0]['size']
        # el backing_file debería estar asociado a cada disco:
        # d['hardware']['disks'][0]['backing_file']

        for index_disk in range(len(dict_to_create['hardware']['disks'])):
            relative_path = dict_to_create['hardware']['disks'][index_disk]['file']
            new_file, path_selected = get_path_to_disk(relative_path, pool=pool_id)
            # UPDATE PATH IN DOMAIN
            dict_to_create['hardware']['disks'][index_disk]['file'] = new_file
            dict_to_create['hardware']['disks'][index_disk]['path_selected'] = path_selected

        update_table_field('domains',id_new,'create_dict',dict_to_create)

        #TODO: REVISAR SI RELAMENTE ES NECESARIO o esta acción responde a versiones antiguas de nuestras funciones de creación
        hardware_update = {}
        hardware_update['disks'] = dict_to_create['hardware']['disks']
        update_domain_dict_hardware(id_new, hardware_update)
        ##################

        for index_disk in range(len(dict_to_create['hardware']['disks'])):
            backing_file = dict_to_create['hardware']['disks'][index_disk]['parent']
            new_file = dict_to_create['hardware']['disks'][index_disk]['file']
            path_selected = dict_to_create['hardware']['disks'][index_disk]['path_selected']
            hyp_to_disk_create = get_host_disk_operations_from_path(path_selected, pool=pool_id, type_path='groups')
            if persistent is False:
                print(f'desktop not persistent, forced hyp: {hyp_to_disk_create}')
                update_domain_forced_hyp(id_domain=id_new,hyp_id=hyp_to_disk_create)

            cmds = create_cmds_disk_from_base(path_base=backing_file, path_new=new_file)
            log.debug('commands to disk create to launch in disk_operations: \n{}'.format('\n'.join(cmds)))
            action = {}
            action['type'] = 'create_disk'
            action['disk_path'] = new_file
            action['index_disk'] = index_disk
            action['domain'] = id_new

            if index_disk == 0:
                cmds += add_cmds_if_custom(id_domain = id_new, path_new=new_file)
                # from pprint import pformat
                # log.info(pformat(cmds))
            action['ssh_commands'] = cmds

            try:
                update_domain_status(status='CreatingDisk',
                                     id_domain=id_new,
                                     hyp_id=False,
                                     detail='Creating disk operation is launched in hypervisor {} ({} operations in queue)'.format(
                                         hyp_to_disk_create,
                                         self.manager.q_disk_operations[hyp_to_disk_create].qsize()))
                self.manager.q_disk_operations[hyp_to_disk_create].put(action)

            except Exception as e:
                update_domain_status(status='FailedCreatingDomain',
                                     id_domain=id_new,
                                     hyp_id=False,
                                     detail='Creating disk operation failed when insert action in queue for disk operations')
                log.error(
                    'Creating disk operation failed when insert action in queue for disk operations. Exception: {}'.format(
                        e))

    def update_hardware_dict_and_xml_from_create_dict(self,id_domain):
        try:
            populate_dict_hardware_from_create_dict(id_domain)
        except Exception as e:
            log.error('error when populate dict hardware from create dict in domain {}'.format(id_domain))
            log.error('Traceback: \n .{}'.format(traceback.format_exc()))
            log.error('Exception message: {}'.format(e))
            update_domain_status('Failed', id_domain,
                                 detail='Updating aborted, failed when populate hardware dictionary')
            return False

        try:
            xml_raw = update_xml_from_dict_domain(id_domain)
            if xml_raw is False:
                update_domain_status(status='Failed',
                                     id_domain=id_domain,
                                     detail='XML Parser Error, xml is not valid')
                return False

        except Exception as e:
            log.error('error when populate dict hardware from create dict in domain {}'.format(id_domain))
            log.error('Traceback: \n .{}'.format(traceback.format_exc()))
            log.error('Exception message: {}'.format(e))
            update_domain_status('Failed', id_domain,
                                 detail='Updating aborted, failed when updating xml from hardware dictionary')
            return False
        return True

    def updating_from_create_dict(self, id_domain,ssl=True):
        if self.update_hardware_dict_and_xml_from_create_dict(id_domain):
            update_domain_status('Updating', id_domain,
                                 detail='xml and hardware dict updated, waiting to test if domain start paused in hypervisor')
            pool_id = get_pool_from_domain(id_domain)
            if pool_id is False:
                update_domain_status('Failed', id_domain, detail='Updating aborted, domain has not pool')
                return False

            kind = get_domain_kind(id_domain)
            if kind == 'desktop':
                cpu_host_model = self.manager.pools[pool_id].conf.get('cpu_host_model', DEFAULT_HOST_MODE)
                xml_to_test = recreate_xml_to_start(id_domain,ssl,cpu_host_model)
                self.start_paused_domain_from_xml(xml=xml_to_test, id_domain=id_domain, pool_id=pool_id)
            else:
                update_domain_status('Stopped', id_domain,
                                     detail='Updating finalished, ready to derivate desktops')

                return True

    def creating_and_test_xml_start(self, id_domain, creating_from_create_dict=False,
                                    xml_from_virt_install=False,
                                    xml_string=None,ssl=True):
        if creating_from_create_dict is True:
            try:
                populate_dict_hardware_from_create_dict(id_domain)
            except Exception as e:
                log.error('error when populate dict hardware from create dict in domain {}'.format(id_domain))
                log.error('Traceback: \n .{}'.format(traceback.format_exc()))
                log.error('Exception message: {}'.format(e))

        domain = get_domain(id_domain)
        #create_dict_hw = domain['create_dict']['hardware']
        # for media in ['isos','floppies']
        #     if 'isos' in create_dict_hw.keys():
        #         for index_disk in range(len(create_dict_hw['isos'])):
        #             update_hw['hardware']['isos'][index_disk]['file'] = new_file

        if type(xml_string) is str:
            xml_from = xml_string

        elif 'create_from_virt_install_xml' in domain['create_dict']:
            xml_from = get_dict_from_item_in_table('virt_install',domain['create_dict']['create_from_virt_install_xml'])['xml']

        elif xml_from_virt_install is False:
            id_template = domain['create_dict']['origin']
            template = get_domain(id_template)
            xml_from = template['xml']
            parents_chain = template.get('parents',[]) + domain.get('parents',[])
            #when creating template from domain, the domain would be inserted as a parent while template is creating
            # parent_chain never can't have id_domain as parent
            if id_domain in parents_chain:
                for i in range(parents_chain.count('a')):
                    parents_chain.remove(id_domain)

            update_table_field('domains', id_domain, 'parents', parents_chain)


        elif xml_from_virt_install is True:
            xml_from = domain['xml_virt_install']

        else:
            return False

        update_table_field('domains', id_domain, 'xml', xml_from)


        xml_raw = update_xml_from_dict_domain(id_domain)
        if xml_raw is False:
            update_domain_status(status='FailedCreatingDomain',
                                 id_domain=id_domain,
                                 detail='XML Parser Error, xml is not valid')
            return False
        update_domain_status('CreatingDomain', id_domain,
                             detail='xml and hardware dict updated, waiting to test if domain start paused in hypervisor')
        pool_id = get_pool_from_domain(id_domain)


        if 'start_after_created' in domain.keys():
            if domain['start_after_created'] is True:
                update_domain_status('StartingDomainDisposable', id_domain,
                                     detail='xml and hardware dict updated, starting domain disposable')

                # update_domain_status('Starting', id_domain,
                #                      detail='xml and hardware dict updated, starting domain disposable')

                self.start_domain_from_id(id_domain)

        else:
            #change viewer password, remove selinux options and recreate network interfaces
            try:
                cpu_host_model = self.manager.pools[pool_id].conf.get('cpu_host_model', DEFAULT_HOST_MODE)
                xml = recreate_xml_to_start(id_domain,ssl,cpu_host_model)
            except Exception as e:
                log.error('recreate_xml_to_start in domain {}'.format(id_domain))
                log.error('Traceback: \n .{}'.format(traceback.format_exc()))
                log.error('Exception message: {}'.format(e))
                xml = False

            if xml is False:
                update_domain_status('Failed', id_domain,
                                     detail="DomainXML can't parse and modify xml to start")
            else:
                self.start_paused_domain_from_xml(xml=xml,
                                                  id_domain=id_domain,
                                                  pool_id=pool_id)


    # INFO TO DEVELOPER: HAY QUE QUITAR CATEGORY Y GROUP DE LOS PARÁMETROS QUE RECIBE LA FUNCIÓN
    def domain_from_template(self,
                             id_template,
                             id_new,
                             user,
                             category,
                             group,
                             name,
                             description,
                             cpu,
                             ram,
                             current_ram=-1,
                             id_net=None,
                             force_server=None,
                             only_cmds=False,
                             path_to_disk_dir=None,
                             disk_filename=None,
                             create_domain_in_db=True):

        # INFO TO DEVELOPER: falta verificar que el id no existe y si existe salir enseguida, ya que si no haríamos updates y
        # creaciónes de disco peligrosas
        dict_domain_template = get_domain(id_template)
        dict_domain_new = dict_domain_template.copy()
        dict_domain_new['id'] = id_new
        dict_domain_new['user'] = user
        dict_domain_new['category'] = category
        dict_domain_new['group'] = group
        dict_domain_new['kind'] = 'desktop'
        dict_domain_new['name'] = name
        dict_domain_new['description'] = description
        dict_domain_new['status'] = 'CreatingDisk'
        dict_domain_new['detail'] = 'Defining new domain'

        if force_server == True:
            dict_domain_new['server'] = True
        elif force_server == False:
            dict_domain_new['server'] = False
        else:
            dict_domain_new['server'] = dict_domain_template['server']

        x = DomainXML(dict_domain_template['xml'])
        if x.parser is False:
            log.error('error when parsing xml')
            dict_domain_new['status'] = 'FailedCreatingDomain'
            dict_domain_new['detail'] = 'XML Parser have failed, xml with errors'
            return False

        x.set_name(id_new)
        x.set_title(name)
        x.set_description(description)

        old_path_disk = dict_domain_template['hardware']['disks'][0]['file']
        old_path_dir = extract_dir_path(old_path_disk)

        #DEFAULT_GROUP_DIR = CONFIG_DICT['REMOTEOPERATIONS']['default_group_dir']

        if path_to_disk_dir is None:
            path_to_disk_dir = DEFAULT_GROUP_DIR + '/' + \
                               dict_domain_template['category'] + '/' + \
                               dict_domain_template['group'] + '/' + \
                               dict_domain_template['user']

        if len(old_path_disk[len(old_path_dir) + 1:-1].split('.')) > 1:
            extension = old_path_disk[len(old_path_dir) + 1:-1].split('.')[1]
        else:
            extension = 'qcow'

        if disk_filename is None:
            disk_filename = id_new + '.' + extension

        new_path_disk = path_to_disk_dir + '/' + disk_filename

        x.set_vcpu(cpu)
        x.set_memory(ram,current=current_ram)
        x.set_vdisk(new_path_disk)
        x.randomize_vm()

        dict_domain_new['hardware'] = x.vm_dict
        dict_domain_new['xml'] = x.return_xml()

        cmds = create_cmds_disk_from_base(old_path_disk, new_path_disk, )

        if only_cmds is True:
            dict_domain_new['status'] = 'Crashed'
            dict_domain_new['detail'] = 'Disk not created, only for testing ui purpose, create command is not launched'
            return dict_domain_new, cmds


        else:
            action = {}
            action['type'] = 'create_disk'
            action['disk_path'] = new_path_disk
            action['domain'] = id_new
            action['ssh_commands'] = cmds
            if hasattr(self.pool, 'queue_disk_operation'):
                self.pool.queue_disk_operation.put(action)
                # err,out = create_disk_from_base(old_path_disk,new_path_disk)
                dict_domain_new['status'] = 'CreatingDisk'
                dict_domain_new['detail'] = 'Creating disk operation is launched ({} operations in queue)'.format(
                    self.pool.queue_disk_operation.qsize())
                # list_backing_chain = backing_chain(new_path_disk)

                # dict_domain_new['backing_chain'] = list_backing_chain
            else:
                log.error('queue disk operation is not created')
                dict_domain_new['status'] = 'Crashed'
                dict_domain_new['detail'] = 'Disk not created, queue for disk creation does not exist'

            if create_domain_in_db is True:
                insert_domain(dict_domain_new)

            return dict_domain_new

    def ferrary_from_domain(self,
                            id_domain,
                            num_domains,
                            start_index=0,
                            dir_to_ferrary_disks=None,
                            prefix=None):

        if dir_to_ferrary_disks is None:
            dir_to_ferrary_disks = CONFIG_DICT['FERRARY']['DIR_TO_FERRARY_DISKS'.lower()]
        if prefix is None:
            prefix = CONFIG_DICT['FERRARY']['PREFIX'.lower()]
        ferrary = []
        for i in range(start_index, num_domains + start_index):
            d = dict()
            d['index'] = str(i).zfill(3)
            d['id'] = prefix + id_domain + d['index']
            d['dict_domain'], d['cmd'] = self.domain_from_template(id_template=id_domain,
                                                                   id_new=d['id'],
                                                                   only_cmds=True,
                                                                   path_to_disk_dir=dir_to_ferrary_disks)
            ferrary.append(d)

        cmds = []
        cmds.append(ferrary[0]['cmd'][0])
        cmds = cmds + list(itertools.chain([d['cmd'][1] for d in ferrary]))

        before = time.time()

        cmds_result = exec_remote_list_of_cmds(VDESKTOP_DISK_OPERATINOS, cmds)
        after = time.time()
        duration = after - before
        log.debug('FERRARY: {} disks created in {} with name in {} seconds'.format(num_domains, dir_to_ferrary_disks,
                                                                                   prefix + id_domain + 'XXX',
                                                                                   duration))

        for dict_domain_new in [d['dict_domain'] for d in ferrary]:
            insert_domain(dict_domain_new)

        return ferrary

    def start_ferrary(self, ferrary):
        ids = [f['id'] for f in ferrary]
        for id in ids:
            hyp = self.start_domain_from_id(id)
            update_domain_hyp_started(id, hyp)

    def stop_ferrary(self, ferrary):
        ids = [f['id'] for f in ferrary]
        for id in ids:
            hyp_id = get_domain_hyp_started(id)
            self.stop_domain(id, hyp_id)
            update_domain_hyp_stopped(id)

    def delete_ferrary(self, ferrary):
        cmds = ['rm -f ' + f['dict_domain']['hardware']['disks'][0]['file'] for f in ferrary]

        before = time.time()

        cmds_result = exec_remote_list_of_cmds(VDESKTOP_DISK_OPERATINOS, cmds)

        after = time.time()
        duration = after - before

        ids = [f['id'] for f in ferrary]
        for id in ids:
            delete_domain(id)

        first_disk = ferrary[0]['dict_domain']['hardware']['disks'][0]['file']
        last_disk = ferrary[-1]['dict_domain']['hardware']['disks'][0]['file']
        log.debug('FERRARY: {} disks deleted from {} to {} in {} seconds'.format(len(cmds),
                                                                                 first_disk,
                                                                                 last_disk,
                                                                                 duration))

        return cmds_result

        ## FERRARY

        ### Hypers

        # def set_default_hyper(self,hyp_id):
        #     return change_hyp_disk_operations(hyp_id)

