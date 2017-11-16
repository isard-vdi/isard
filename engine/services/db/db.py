# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import json
import sys
import time
from pprint import pprint, pformat

# coding=utf-8
import rethinkdb as r

from engine.config import RETHINK_HOST, RETHINK_PORT, RETHINK_DB, TRANSITIONAL_STATUS, MAX_QUEUE_DOMAINS_STATUS
from engine.services.log import *

##INFO TO DEVELOPER => TODO: PASAR A config populate => se leerá del rethink
## alberto => lo he de hacer independientemente de josep maria
MAX_LEN_PREV_STATUS_HYP = 10


# r_conn_global = r.connect("localhost", 28015, db='isard')
#
# def new_rethink_connection():
#     global r_conn_global
#
#     if r_conn_global.is_open():
#         return r_conn_global
#
#     else:
#         r_conn_global = r.connect("localhost", 28015, db='isard')
#         return r_conn_global

def new_rethink_connection():
    r_conn = r.connect(RETHINK_HOST, RETHINK_PORT, db=RETHINK_DB)
    # r_conn = r.connect("localhost", 28015, db='isard')
    return r_conn


# def close_rethink_connection(r_conn):
#     #r_conn.close()
#     #del r_conn
#     return True

def close_rethink_connection(r_conn):
    r_conn.close()
    del r_conn
    return True


def get_hyp_hostnames():
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    l = list(rtable. \
             filter({'enabled': True}). \
             pluck('id', 'hostname'). \
             run(r_conn))
    close_rethink_connection(r_conn)

    hyps_hostnames = {d['id']: d['hostname'] for d in l}

    return hyps_hostnames


def table_config_created_and_populated():
    r_conn_test = r.connect(RETHINK_HOST, RETHINK_PORT)
    if not r.db_list().contains(RETHINK_DB).run(r_conn_test):
        return False
    else:
        r_conn = new_rethink_connection()

        out = False
        if r.table_list().contains('config').run(r_conn):
            rtable = r.table('config')
            out = rtable.get(1).run(r_conn)

        close_rethink_connection(r_conn)
        if out is not False:
            if out is not None:
                return True
            else:
                return False
        else:
            return False


def get_hyps_to_test():
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    l = list(rtable. \
             filter({'enabled': True, 'status': 'ReadyToStart'}). \
             pluck('id', 'hostname'). \
             run(r_conn))
    close_rethink_connection(r_conn)

    hyps_hostnames = {d['id']: d['hostname'] for d in l}

    return hyps_hostnames


def get_hyps_ready_to_start():
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    l = list(rtable. \
             filter({'enabled': True, 'status': 'ReadyToStart'}). \
             pluck('id', 'hostname', 'hypervisors_pools'). \
             run(r_conn))
    close_rethink_connection(r_conn)

    hyps_hostnames = {d['id']: d['hostname'] for d in l}

    return hyps_hostnames


def insert_event_in_db(self, dict_event):
    log.debug(pprint(dict_event))
    r_conn = new_rethink_connection()
    r.table('hypervisors_events').insert(dict_event).run(r_conn)
    close_rethink_connection(r_conn)


def get_hypers_disk_operations():
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    hypers_ids = [d['id'] for d in list(
        rtable.filter({'enabled': True, 'capabilities': {'disk_operations': True}}).pluck('id').run(r_conn))]

    close_rethink_connection(r_conn)

    return hypers_ids

    pass


def update_hyp_status(id, status, detail='', uri=''):
    # INFO TO DEVELOPER: TODO debería pillar el estado anterior del hypervisor y ponerlo en un campo,
    # o mejor aún, guardar un histórico con los tiempos de cambios en un diccionario que
    # en python puede ser internamente una cola de X elementos (número de elementos de configuración)
    # como una especie de log de cuando cambio de estado

    # INFO TO DEVELOPER: pasarlo a una función en functions
    defined_status = ['Offline',
                      'TryConnection',
                      'ReadyToStart',
                      'StartingThreads',
                      'Error',
                      'Online',
                      'Blocked',
                      'DestroyingDomains',
                      'StoppingThreads']
    if status in defined_status:
        r_conn = new_rethink_connection()
        rtable = r.table('hypervisors')
        if len(uri) > 0:
            dict_update = {'status': status, 'uri': uri}
        else:
            dict_update = {'status': status}

        d = rtable.get(id).pluck('status',
                                 'status_time',
                                 'prev_status',
                                 'detail').run(r_conn)

        if 'status' in d.keys():
            if 'prev_status' not in d.keys():
                dict_update['prev_status'] = []

            else:
                if type(d['prev_status']) is list:
                    dict_update['prev_status'] = d['prev_status']
                else:
                    dict_update['prev_status'] = []

            d_old_status = {}
            d_old_status['status'] = d['status']
            if 'detail' in d.keys():
                d_old_status['detail'] = d['detail']
            else:
                d_old_status['detail'] = ''
            if 'status_time' in d.keys():
                d_old_status['status_time'] = d['status_time']

            dict_update['prev_status'].insert(0, d_old_status)
            dict_update['prev_status'] = dict_update['prev_status'][:MAX_LEN_PREV_STATUS_HYP]

        now = time.time()
        dict_update['status_time'] = now

        # if len(detail) == 0:
        #     rtable.filter({'id':id}).\
        #           update(dict_update).\
        #           run(r_conn)
        #     # rtable.filter({'id':id}).\
        #     #       replace(r.row.without('detail')).\
        #     #       run(r_conn)
        #     close_rethink_connection(r_conn)
        #
        # else:
        dict_update['detail'] = str(detail)
        rtable.filter({'id': id}). \
            update(dict_update). \
            run(r_conn)
        close_rethink_connection(r_conn)

    else:
        log.error('hypervisor status {} is not defined'.format(status))
        return False


def get_id_hyp_from_uri(uri):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')
    l = list(rtable. \
             filter({'uri': uri}). \
             pluck('id'). \
             run(r_conn))
    close_rethink_connection(r_conn)
    if len(l) > 0:
        return l[0]['id']
    else:
        log.error('function: {} uri {} not defined in hypervisors table'.format(str(__name__), uri))


def get_hyp_hostnames_online():
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')
    l = list(rtable. \
             filter({'enabled': True, 'status': 'Online'}). \
             pluck('id', 'hostname'). \
             run(r_conn))
    close_rethink_connection(r_conn)
    log.debug(l)
    if len(l) > 0:
        hyps_hostnames = {d['id']: d['hostname'] for d in l}

        return hyps_hostnames
    else:
        return dict()


def update_hyp_enable(hyp_id, enable=True):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')
    # out={}
    # for hyp_id in argv:
    #     o = rtable.get(hyp_id).\
    #          update({'enabled':enable}).\
    #          run(r_conn)
    #     out[hyp_id] = o
    out = rtable.get(hyp_id). \
        update({'enabled': enable}). \
        run(r_conn)
    close_rethink_connection(r_conn)
    return out


def update_hyp_capability(hyp_id, capability, enable=True):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    out = rtable.get(hyp_id). \
        update({'capabilities': {capability: enable}}). \
        run(r_conn)
    close_rethink_connection(r_conn)
    return out


def update_uri_hyp(hyp_id, uri):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')
    out = rtable.get(hyp_id). \
        update({'uri': uri}). \
        run(r_conn)
    close_rethink_connection(r_conn)
    return out


def change_hyp_disk_operations(hyp_id):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')
    rtable. \
        replace(r.row.without('disk_operations')). \
        run(r_conn)
    o = rtable.get(hyp_id). \
        update({'disk_operations': True}). \
        run(r_conn)
    close_rethink_connection(r_conn)
    return o


def get_last_hyp_status(id):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors_status')

    l = list(rtable. \
             filter({'id': 'vdesktop1'}). \
             order_by(r.desc('when')). \
             limit(1). \
             run(r_conn))
    close_rethink_connection(r_conn)
    if len(l) == 0:
        return None
    else:
        return l[0]


def get_last_hyp_status(id):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors_status')

    l = list(rtable. \
             filter({'hyp_id': id}). \
             order_by(r.desc('when')). \
             limit(1). \
             run(r_conn))
    close_rethink_connection(r_conn)
    if len(l) == 0:
        return None
    else:
        return l[0]


def delete_domain(id):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    results = rtable.get(id).delete().run(r_conn)
    close_rethink_connection(r_conn)
    return results


def update_domain_progress(id_domain, percent):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    results = rtable.get(id_domain).update({'progress': {'percent': percent,
                                                         'when': time.time()}}).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def update_domain_status(status, id_domain, hyp_id=None, detail=''):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    # INFO TO DEVELOPER TODO: verificar que el estado que te ponen es realmente un estado válido
    # INFO TO DEVELOPER TODO: si es stopped puede interesar forzar resetear hyp_started no??
    # INFO TO DEVELOPER TODO: MOLARÍA GUARDAR UN HISTÓRICO DE LOS ESTADOS COMO EN HYPERVISORES

    # INFO TO DEVELOPER: OJO CON hyp_started a None... peligro si alguien lo chafa, por eso estos if/else

    if hyp_id is None:
        # print('ojojojo')
        results = rtable.get_all(id_domain, index='id').update({
            'status': status,
            'hyp_started': '',
            'detail': json.dumps(detail)}).run(r_conn)
    else:
        results = rtable.get_all(id_domain, index='id').update({'hyp_started': hyp_id,
                                                                'hyp_started2': hyp_id,
                                                                'status': status,
                                                                'detail': json.dumps(detail)}).run(r_conn)
    if status == 'Stopped':
        stop_last_domain_status(id_domain)

    close_rethink_connection(r_conn)
    # if results_zero(results):
    #
    #     log.debug('id_domain {} in hyperviros {} does not exist in domain table'.format(id_domain,hyp_id))

    return results


def get_hyp_id_from_hostname(hostname):
    r_conn = new_rethink_connection()
    l = r.table('hypervisors').filter({'hostname': hostname}).pluck('id').run(r_conn)
    close_rethink_connection(r_conn)
    if len(l) > 0:
        return l['id']
    else:
        return l


def get_dict_from_item_in_table(table, id):
    r_conn = new_rethink_connection()
    d = r.table(table).get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return d


def get_hyp(id):
    r_conn = new_rethink_connection()
    l = r.table('hypervisors').get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return l


def get_hyp_hostname_from_id(id):
    r_conn = new_rethink_connection()
    l = r.table('hypervisors').get(id).pluck('hostname', 'port', 'user').run(r_conn)
    close_rethink_connection(r_conn)
    if len(l) > 0:
        if l.__contains__('user') and l.__contains__('port'):
            return l['hostname'], l['port'], l['user']
        else:
            log.error('hypervisor {} does not contain user or port in database'.format(id))
            return False
    else:
        return False


def get_hyp_hostname_user_port_from_id(id):
    r_conn = new_rethink_connection()
    l = r.table('hypervisors').get(id).pluck('hostname', 'user', 'port').run(r_conn)
    close_rethink_connection(r_conn)

    if len(l) > 0:
        if l.__contains__('user') and l.__contains__('port'):
            return l
        else:
            log.error('hypervisor {} does not contain user or port in database'.format(id))
            return False
    else:
        return False


def results_zero(results):
    return reduce(lambda a, b: a + b, results.values())


def update_all_domains_status(reset_status='Stopped',
                              from_status=['Starting', 'Stopping', 'Started']):
    r_conn = new_rethink_connection()
    if from_status is None:
        results = r.table('domains').update({'status': reset_status}).run(r_conn)

    for initial_status in from_status:
        results = r.table('domains').get_all(initial_status, index='status').update({'status': reset_status}).run(
            r_conn)
    close_rethink_connection(r_conn)
    return results


def update_all_hyps_status(reset_status='Offline'):
    r_conn = new_rethink_connection()
    results = r.table('hypervisors').update({'status': reset_status}).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def update_domain_hyp_started(domain_id, hyp_id, detail='', status='Started'):
    results = update_domain_status(status, domain_id, hyp_id, detail=detail)
    return results


def update_domain_hyp_stopped(id_domain, status='Stopped'):
    hyp_id = get_domain_hyp_started(id_domain)
    results = update_domain_status(status, id_domain, hyp_id)
    return results


def get_domain_hyp_started(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    results = rtable.get(id_domain).pluck('hyp_started').run(r_conn)
    close_rethink_connection(r_conn)
    if results is None:
        return ''

    return results['hyp_started']


def get_domain_hyp_started_and_status_and_detail(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    try:
        results = rtable.get(id_domain).pluck('hyp_started', 'detail', 'status').run(r_conn)
        close_rethink_connection(r_conn)
    except:
        # if results is None:
        return {}
    return results


def get_domains_with_disks():
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    try:
        l = list(rtable.pluck('id', {'disks_info': ['filename']}).run(r_conn))
        results = [{'id': d['id'], 'filename': d['disks_info'][0]['filename']} for d in l if 'disks_info' in d.keys()]
        close_rethink_connection(r_conn)
    except:
        # if results is None:
        close_rethink_connection(r_conn)
        return []
    return results


def get_domains_with_status(status):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    try:
        results = rtable.get_all(status, index='status').pluck('id').run(r_conn)
        close_rethink_connection(r_conn)
    except:
        # if results is None:
        close_rethink_connection(r_conn)
        return []
    return [d['id'] for d in results]


def get_domains_with_transitional_status(list_status=TRANSITIONAL_STATUS):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    # ~ l = list(rtable.filter(lambda d: r.expr(list_status).
    # ~ contains(d['status'])).pluck('status', 'id', 'hyp_started').
    # ~ run
    l = list(rtable.get_all(r.args(list_status), index='status').pluck('status', 'id', 'hyp_started').run(r_conn))
    close_rethink_connection(r_conn)
    return l


def get_xml_from_virt_viewer(id_virt_viewer):
    r_conn = new_rethink_connection()
    rtable = r.table('domains_virt_install')

    dict_domain = rtable.get(id_virt_viewer).run(r_conn)
    close_rethink_connection(r_conn)
    return dict_domain['xml']


def change_status_to_all_domains_with_status(oldstatus, newstatus):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    try:
        results = rtable.get_all(oldstatus, index='status').pluck('id').run(r_conn)
        result = rtable.get_all(oldstatus, index='status').update({'status': newstatus}).run(r_conn)
        close_rethink_connection(r_conn)

    except:
        # if results is None:
        close_rethink_connection(r_conn)
        return []
    return [d['id'] for d in results]


def insert_ferrary(id, ferrary_list):
    r_conn = new_rethink_connection()

    results = rtable.get(id).delete().run(r_conn)
    results = rtable.insert({'id': id, 'ferrary': ferrary_list}).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def get_ferrary(id):
    r_conn = new_rethink_connection()
    rtable = r.table('ferrarys')

    results = rtable.get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return results['ferrary']


def update_domain_dict_hardware(id, domain_dict, xml=False):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    if xml is False:
        results = rtable.get(id).update({'hardware': domain_dict}).run(r_conn)

    else:
        results = rtable.get(id).update({'hardware': domain_dict, 'xml': xml}).run(r_conn)

    # if results_zero(results):
    #     log.debug('id_domain {} does not exist in domain table'.format(id))

    close_rethink_connection(r_conn)
    return results


def remove_domain_viewer_values(id):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    results = rtable.get(id).replace(r.row.without('viewer')).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def update_domain_viewer_started_values(id, hyp_id=False, port=False, tlsport=False, passwd=False):
    #
    # dict_event = {'domain':dom.name(),
    #               'hyp_id':hyp_id,
    #                'event':domEventToString(event),
    #               'detail':domDetailToString(event, detail),
    #                 'when':now}

    r_conn = new_rethink_connection()

    if hyp_id is not False:
        rtable = r.table('hypervisors')
        d = rtable.get(hyp_id).pluck('viewer_hostname', 'hostname', 'id').run(r_conn)
        if 'viewer_hostname' in d.keys():
            if len(d['viewer_hostname']) > 0:
                hostname = d['viewer_hostname']
            else:
                hostname = d['hostname']
        else:
            hostname = d['hostname']
    else:
        hostname = None

    dict_viewer = {}
    if hostname is not None:
        dict_viewer['hostname'] = hostname
    else:
        dict_viewer['hostname'] = False

    dict_viewer['tlsport'] = tlsport
    dict_viewer['port'] = port
    if passwd is not False:
        dict_viewer['passwd'] = passwd

    # event spice graph update these fields
    dict_viewer['client_addr'] = False
    dict_viewer['client_since'] = False

    rtable = r.table('domains')
    results = rtable.get(id).update({'viewer': dict_viewer}).run(r_conn)

    close_rethink_connection(r_conn)
    return results


#
# INFO TO DEVELOPER, ELIMINAR ESTA FUNCION
# def update_domain_backing_chain(id_domain,index_disk,list_backing_chain):
#
#     r_conn = new_rethink_connection()
#     rtable=r.table('domains')
#
#     dict_hardware = rtable.get(id_domain).pluck('hardware').run(r_conn)
#     results = rtable.get(id_domain).update({'hardware':dict_hardware).run(r_conn)
#     close_rethink_connection(r_conn)
#     return results

def update_disk_backing_chain(id_domain, index_disk, path_disk, list_backing_chain, new_template=False,
                              list_backing_chain_template=[]):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    domain = rtable.get(id_domain).run(r_conn)

    if new_template == True:
        domain['create_dict']['template_dict']['disks_info'] = list_backing_chain_template

    domain['disks_info'] = list_backing_chain
    results = rtable.replace(domain).run(r_conn)

    #
    # if new_template == True:
    #     dict_disks = rtable.get(id_domain).pluck({'create_dict':{'template_dict':{'hardware':{'disks':{'file':True}}}}}).run(r_conn)['create_dict']['template_dict]']
    # else:
    #     dict_disks = rtable.get(id_domain).pluck({'hardware':{'disks':{'file':True}}}).run(r_conn)
    #
    #
    # if path_disk == dict_disks['hardware']['disks'][index_disk]['file']:
    #     # INFO TO DEVELOPER: BACKING CHAIN NOT IN HARDWARE DICT
    #     # dict_disks['template_json']['hardware']['disks'][index_disk]['backing_chain'] = list_backing_chain
    #     if 'disks_info' not in dict_disks.keys():
    #         dict_disks['disks_info']={}
    #     dict_disks['disks_info']['path_disk'] = list_backing_chain
    #
    #     if new_template == True:
    #         results = rtable.get(id_domain).update({'template_json':dict_disks}).run(r_conn)
    #     else:
    #         results = rtable.get(id_domain).update(dict_disks).run(r_conn)

    close_rethink_connection(r_conn)
    return results

    # else:
    #     log.error('update_disk_backing_chain FAILED: there is not path {} in disk_index {} in domain {}'.format(path_disk,index_disk,id_domain))
    #     return


def update_disk_template_created(id_domain, index_disk):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    dict_disk_templates = rtable.get(id_domain).pluck('disk_template_created').run(r_conn)
    dict_disk_templates['disk_template_created'][index_disk] = 1
    results = rtable.get(id_domain).update(dict_disk_templates).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def remove_disk_template_created_list_in_domain(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    results = rtable.get(id_domain).replace(r.row.without('disk_template_created')).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def remove_dict_new_template_from_domain(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    results = rtable.get(id_domain).replace(r.row.without({'create_dict': 'template_dict'})).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def get_if_all_disk_template_created(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    dict_disk_templates = rtable.get(id_domain).pluck('disk_template_created').run(r_conn)
    created = len(dict_disk_templates['disk_template_created']) == sum(dict_disk_templates['disk_template_created'])
    close_rethink_connection(r_conn)
    return created


def create_disk_template_created_list_in_domain(id_domain):
    dict_domain = get_domain(id_domain)
    created_disk_finalished_list = [0 for a in range(len(dict_domain['hardware']['disks']))]

    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    results = rtable.get(id_domain).update({'disk_template_created': created_disk_finalished_list}).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def set_unknown_domains_not_in_hyps(hyps):
    # find domains in status Started,Paused,Unknown
    # that are not in hypervisors
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    status_to_unknown = ['Started', 'Paused', 'Unknown']

    l = list(rtable.filter(lambda d: r.expr(status_to_unknown).contains(d['status'])).
             filter(lambda d: r.not_(r.expr(hyps).contains(d['hyp_started']))).
             update({'status': 'Unknown'}).
             run(r_conn)
             )

    status_to_stopped = ['Starting', 'CreatingTemplate']

    l = list(rtable.filter(lambda d: r.expr(status_to_stopped).contains(d['status'])).
             filter(lambda d: r.not_(r.expr(hyps).contains(d['hyp_started']))).
             update({'status': 'Stopped'}).
             run(r_conn)
             )
    close_rethink_connection(r_conn)
    return l


def get_hyps_with_status(list_status, not_=False, empty=False):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')
    if not_ == True:
        l = list(rtable.filter({'enabled': True}).filter(lambda d: r.not_(r.expr(list_status).
                                                                          contains(d['status']))).
                 run(r_conn))
    else:
        l = list(rtable.filter({'enabled': True}).filter(lambda d: r.expr(list_status).
                                                         contains(d['status'])).
                 run(r_conn))

    if empty == True:
        nostatus = list(rtable.filter({'enabled': True}).filter(lambda n: ~n.has_fields('status')).run(r_conn))
        l = l + nostatus

    close_rethink_connection(r_conn)
    return l


def get_pool(id_pool):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors_pools')
    pool = rtable.get(id_pool).run(r_conn)
    close_rethink_connection(r_conn)
    return pool


def get_pool_from_domain(domain_id):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    try:
        d = rtable.get(domain_id).pluck('pool', 'kind').run(r_conn)
        if d['kind'] == 'desktop':
            if 'pool' not in d.keys():
                pool = 'default'
            else:
                if type(d['pool']) is unicode or type(d['pool']) is str:
                    rtable = r.table('hypervisors_pools')
                    d_pool = rtable.get(d['pool']).run(r_conn)
                    if len(d_pool.keys()) > 0:
                        pool = d['pool']
                    else:
                        pool = 'default'
        else:
            pool = False
    except r.ReqlNonExistenceError:
        log.error('domain_id {} does not exist in domains table'.format(domain_id))
        log.debug('function: {}'.format(sys._getframe().f_code.co_name))
        pool = False

    close_rethink_connection(r_conn)
    return pool


def get_domains_started_in_hyp(hyp_id):
    # TODO, ASEGURARNOS QUE LOS status DE LOS DOMINIOS ESTÁN EN start,unknown,paused
    # no deberían tener hypervisor activo en otro estado, pero por si las moscas
    # y ya de paso quitar eh hyp_started si queda alguno
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    list_domain = list(rtable.get_all(hyp_id, index='hyp_started').pluck('id').run(r_conn))

    l = [d['id'] for d in list_domain]
    close_rethink_connection(r_conn)
    return l


def update_domains_started_in_hyp_to_unknown(hyp_id):
    # TODO, ASEGURARNOS QUE LOS status DE LOS DOMINIOS ESTÁN EN start,unknown,paused
    # no deberían tener hypervisor activo en otro estado, pero por si las moscas
    # y ya de paso quitar eh hyp_started si queda alguno
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    result = rtable.get_all(hyp_id, index='hyp_started').update({'status': 'Unknown'}).run(r_conn)
    close_rethink_connection(r_conn)
    return result


# def update_domain_hyp_started(domain_id,hyp_id,detail=''):
#     r_conn = new_rethink_connection()
#     rtable=r.table('domains')
#
#     result = rtable.filter({'id':domain_id}).update({'hyp_started':hyp_id,'detail':detail}).run(r_conn, durability="soft", noreply=True)
#     close_rethink_connection(r_conn)
#     return result

def get_interface(id):
    r_conn = new_rethink_connection()
    rtable = r.table('interfaces')

    try:
        dict_domain = rtable.get(id).run(r_conn)
    except:
        log.error('interface with id {} not defined in database table interfaces')
        dict_domain = None

    close_rethink_connection(r_conn)
    return dict_domain


def get_domain(id):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    dict_domain = rtable.get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return dict_domain


def get_domain_status(id):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    domain_status = rtable.get(id).pluck('status').run(r_conn)
    close_rethink_connection(r_conn)
    return domain_status['status']


def get_disks_all_domains():
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    domains_info_disks = rtable.pluck('id', {'hardware': [{'disks': ['file']}]}).run(r_conn)
    tuples_id_disk = [(d['id'], d['hardware']['disks'][0]['file']) for d in domains_info_disks]
    close_rethink_connection(r_conn)
    return tuples_id_disk


def exist_domain(id):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    l = list(rtable.get(id).run(r_conn))
    close_rethink_connection(r_conn)
    if len(l) > 0:
        return True
    else:
        return False


def insert_domain(dict_domain):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    result = rtable.insert(dict_domain).run(r_conn)
    close_rethink_connection(r_conn)
    return result


def remove_domain(id):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    result = rtable.get(id).delete().run(r_conn)
    close_rethink_connection(r_conn)
    return result


def get_last_domain_status(name):
    r_conn = new_rethink_connection()
    rtable = r.table('domains_status')
    try:
        return rtable. \
            get_all(name, index='name'). \
            nth(-1). \
            run(r_conn)
        # ~ filter({'name':name}).\
        # ~ order_by(r.desc('when')).\
        # ~ limit(1).\
        close_rethink_connection(r_conn)
    except:
        close_rethink_connection(r_conn)
        return None
        # ~ if len(l) == 0:
        # ~ return None
        # ~ else:
        # ~ return l  #[0]


def stop_last_domain_status(name):
    r_conn = new_rethink_connection()
    rtable = r.table('domains_status')
    try:
        return rtable. \
            get_all(name, index='name'). \
            nth(-1).update({'state': 'stopped', 'state_reason': 'not running'}). \
            run(r_conn)
        close_rethink_connection(r_conn)
    except:

        close_rethink_connection(r_conn)
        return None


def update_hypervisor_failed_connection(id, fail_connected_reason=''):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')
    rtable.get(id).update({'detail': str(fail_connected_reason)}).run(r_conn)
    # if len(fail_connected_reason) > 0:
    #     rtable.get(id).update({'detail':fail_connected_reason}).run(r_conn)
    # else:
    #     rtable.get(id).replace(r.row.without('fail_connected_reason')).run(r_conn)
    close_rethink_connection(r_conn)


def initialize_db_status_hyps():
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    # all hyps to offline
    rtable.filter({'enabled': False}). \
        update({'status': 'Offline'}). \
        run(r_conn)
    rtable.filter({'enabled': True}). \
        update({'status': 'Offline'}). \
        run(r_conn)
    # return only enabled
    l = list(rtable.filter({'enabled': True}). \
             pluck(['id', 'hostname']).
             run(r_conn))

    close_rethink_connection(r_conn)
    if len(l) > 0:
        hyps_hostnames = {d['id']: d['hostname'] for d in l}

        return hyps_hostnames
    else:
        return dict()


def update_domain_history_from_id_domain(domain_id, new_status, new_detail, date_now):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    # domain_fields = rtable.get(domain_id).pluck('status','history_domain','detail','hyp_started').run(r_conn)
    domain_fields = rtable.get(domain_id).pluck('history_domain', 'hyp_started').run(r_conn)
    close_rethink_connection(r_conn)

    if 'history_domain' in domain_fields:
        history_domain = domain_fields['history_domain']
    else:
        history_domain = []

    if new_detail is None:
        new_detail = ''

    if 'hyp_started' in domain_fields:
        hyp_started = domain_fields['hyp_started']
    else:
        hyp_started = ''

    now = date_now.strftime("%Y-%b-%d %H:%M:%S.%f")

    update_domain_history_status(domain_id=domain_id,
                                 new_status=new_status,
                                 when=now,
                                 history_domain=history_domain,
                                 detail=new_detail,
                                 hyp_id=hyp_started)


def update_domain_history_status(domain_id, new_status, when, history_domain, detail='', hyp_id=''):
    list_history_domain = create_list_buffer_history_domain(new_status, when, history_domain, detail, hyp_id)

    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    results = rtable.get(domain_id).update({'history_domain': list_history_domain}).run(r_conn)

    close_rethink_connection(r_conn)
    return results


def create_list_buffer_history_domain(new_status, when, history_domain, detail='', hyp_id=''):
    d = {'when': when,
         'status': new_status,
         'detail': detail,
         'hyp_id': hyp_id}

    new_history_domain = [d] + history_domain[:MAX_QUEUE_DOMAINS_STATUS]
    return new_history_domain

    # buffer_history_domain = deque(maxlen=MAX_QUEUE_DOMAINS_STATUS)
    # buffer_history_domain.extend(reversed(history_domain))
    # buffer_history_domain.appendleft(d)
    # return list(buffer_history_domain)


def insert_place(id_place,
                 name,
                 rows,
                 cols,
                 network=None,
                 enabled=True,
                 description='',
                 ssh_enable=False,
                 ssh_user='',
                 ssh_pwd=None,
                 ssh_port=22,
                 ssh_key_path=''):
    r_conn = new_rethink_connection()
    rtable = r.table('places')

    rtable.insert({'id': id_place,
                   'name': name,
                   'description': description,
                   'enabled': enabled,
                   'status': 'Unmanaged',  # Unmanaged / Managed
                   'detail': 'new place created',
                   'events_pending': [],
                   'events_processed': [],
                   'managed_by_user': None,
                   'dimensions': {
                       'w': cols,
                       'h': rows
                   },
                   'network': network,
                   'ssh': {
                       'enabled': ssh_enable,
                       'user': ssh_user,
                       'pwd': ssh_pwd,
                       'port': ssh_port,
                       'ssh_key': ssh_key_path
                   },
                   'stats': {
                       'total_hosts': 0,
                       'total_ping': 0,
                       'total_login': 0,
                       'total_desktops': 0,
                       'total_viewers': 0,
                       'total_vcpus': 0,
                       'total_memory': 0
                   }
                   }). \
        run(r_conn)

    close_rethink_connection(r_conn)


def insert_host_viewer(hostname,
                       description,
                       place_id,
                       ip,
                       row,
                       col,
                       mac=None,
                       enabled=True):
    r_conn = new_rethink_connection()
    rtable = r.table('hosts_viewers')

    rtable.insert({'hostname': hostname,
                   'place_id': place_id,
                   'id': ip,
                   'position': {'row': row,
                                'col': col,
                                'size_x': 1,
                                'size_y': 1},
                   'description': description,
                   'mac': mac,
                   'enabled': enabled,
                   'status': 'Offline',  # Offline, online, ready_to_launch_ssh_commands
                   'logged_user': None,
                   'desktops_running': [],
                   'status_time': time.time()}). \
        run(r_conn)

    close_rethink_connection(r_conn)


def insert_hyp(id,
               hostname,
               enable=True,
               status='Offline',
               hypervisors_pools=['default'],
               user='root',
               port='22'):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    rtable.insert({'id': id,
                   'hostname': hostname,
                   'enabled': enable,
                   'status': status,
                   'hypervisors_pools': pools,
                   'user': user,
                   'port': port,
                   'detail': 'new hypervisor created'}). \
        run(r_conn)
    close_rethink_connection(r_conn)


def get_pools_from_hyp(hyp_id):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    d = rtable.get(hyp_id).pluck('hypervisors_pools').run(r_conn)

    close_rethink_connection(r_conn)
    return d['hypervisors_pools']


def add_hypers_to_pool(id_pool, *id_hypers):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')
    return_operations = []
    for id_hyp in id_hypers:
        old_pool = rtable.get(id_hyp).pluck('hypervisors_pools').run(r_conn)
        if len(old_pool) == 0:
            pools = [id_pool]
        else:
            pools = old_pool['hypervisors_pools']
        if id_pool not in pools:
            pools.append(id_pool)
        return_operations.append(rtable.filter({'id': id_hyp}). \
                                 update({'hypervisors_pools': pools}). \
                                 run(r_conn))

    close_rethink_connection(r_conn)
    return return_operations


def del_hypers_from_pool(id_pool, *id_hypers):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')
    return_operations = []
    for id_hyp in id_hypers:
        old_pool = rtable.get(id_hyp).pluck('hypervisors_pools').run(r_conn)
        if len(old_pool) == 0:
            pools = [id_pool]
        else:
            pools = old_pool['hypervisors_pools']
            if id_pool in pools:
                pools.remove(id_pool)
                return_operations.append(rtable.filter({'id': id_hyp}). \
                                         update({'hypervisors_pools': pools}). \
                                         run(r_conn))

    close_rethink_connection(r_conn)
    return return_operations


def get_hypers_in_pool(id_pool='default', ready_to_start=False, enable=True):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')
    return_operations = []

    l = list(rtable.filter(r.row['hypervisors_pools'].contains(id_pool)). \
             filter({'status': 'Online'}).pluck('id').run(r_conn))

    hyp_ids = [a['id'] for a in l]

    close_rethink_connection(r_conn)
    return hyp_ids


def delete_hyp(hyp_id):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    results = rtable.get(hyp_id).delete().run(r_conn)
    close_rethink_connection(r_conn)


def list_all_hyps():
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    results = rtable.run(r_conn)
    l = list(results)
    close_rethink_connection(r_conn)
    return l


def update_db_hyp_info(id, hyp_info):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    rtable.filter({'id': id}). \
        update({'info': hyp_info}). \
        run(r_conn)
    close_rethink_connection(r_conn)


def get_config_branch(key):
    r_conn = new_rethink_connection()
    rtable = r.table('config')

    d_config = rtable.get(1)[key].run(r_conn)
    close_rethink_connection(r_conn)
    return d_config


def insert_db_hyp_status(dict_hyp_status):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors_status')

    rtable.insert(dict_hyp_status). \
        run(r_conn, durability="soft", noreply=True)
    close_rethink_connection(r_conn)


def insert_db_domain_status(dict_domain_status):
    r_conn = new_rethink_connection()
    rtable = r.table('domains_status')

    rtable.insert(dict_domain_status). \
        run(r_conn, durability="soft", noreply=True)
    close_rethink_connection(r_conn)


def insert_disk_operation(dict_disk_operation):
    r_conn = new_rethink_connection()
    rtable = r.table('disk_operations')

    result = rtable.insert(dict_disk_operation). \
        run(r_conn)
    close_rethink_connection(r_conn)

    id = result['generated_keys']

    return id


def insert_action(id_action, parameters, debug=False):
    r_conn = new_rethink_connection()
    rtable = r.table('actions')

    d = {'action': id_action,
         'parameters': parameters,
         'debug': debug,
         'when': time.time()
         }
    result = rtable.insert(d). \
        run(r_conn)
    close_rethink_connection(r_conn)

    return result


def get_config():
    r_conn = new_rethink_connection()
    rtable = r.table('config')
    config = rtable.get(1).run(r_conn)
    return config


def update_disk_operation(id, dict_fields_update):
    r_conn = new_rethink_connection()
    rtable = r.table('disk_operations')

    results = rtable.get(id).update(dict_fields_update).run(r_conn)
    close_rethink_connection(r_conn)
    return results


def get_domain_spice(id_domain):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    domain = rtable.get(id).run(r_conn)
    close_rethink_connection(r_conn)
    if 'viewer' not in domain.keys():
        return False
    if 'tlsport' not in domain['viewer'].keys(): domain['viewer']['tlsport'] = False
    if 'port' not in domain['viewer'].keys(): domain['viewer']['port'] = False
    return {'host': domain['viewer']['hostname'],
            'kind': domain['hardware']['graphics']['type'],
            'port': domain['viewer']['port'],
            'tlsport': domain['viewer']['tlsport'],
            'passwd': domain['viewer']['passwd']}


def get_domains_from_classroom(classroom):
    return []


def get_domains_from_group(group, kind='desktop'):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    l = list(r.table('domains').eq_join('user', r.table('users')).without({'right': 'id'}).without(
        {'right': 'kind'}).zip().filter(
        {'group': group, 'kind': kind}).order_by('id').pluck('status', 'id', 'kind',
                                                             {'hardware': [{'disks': ['file']}]}).run(r_conn))
    close_rethink_connection(r_conn)
    return [{'kind': s['kind'], 'id': s['id'], 'status': s['status'], 'disk': s['hardware']['disks'][0]['file']} for s
            in l]


def get_domains_running_hypervisor(hyp_id):
    return []


def get_domains_from_template_origin():
    return []


def get_all_domains_with_id_and_status(status=None, kind='desktop'):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    if status is None:
        l = list(rtable.filter({'kind': kind}).pluck('id', 'status').run(r_conn))
    else:
        l = list(rtable.filter({'kind': kind, 'status': status}).pluck('id', 'status').run(r_conn))
    close_rethink_connection(r_conn)
    return l


def get_domains_from_user(user, kind='desktop'):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')
    l = list(rtable.filter({'user': user, 'kind': kind}).pluck('status', 'id', 'kind',
                                                               {'hardware': [{'disks': ['file']}]}).run(r_conn))
    close_rethink_connection(r_conn)
    return [{'kind': s['kind'], 'id': s['id'], 'status': s['status'], 'disk': s['hardware']['disks'][0]['file']} for s
            in l]


def start_all_domains_from_user(user):
    l = get_domains_from_user(user)
    for d in l:
        domain_id = d['id']
        if get_domain_status(domain_id) == 'Stopped':
            update_domain_status('Starting', domain_id)


def stop_all_domains_from_user(user):
    l = get_domains_from_user(user)
    for d in l:
        domain_id = d['id']
        if get_domain_status(domain_id) == 'Started':
            update_domain_status('Stopping', domain_id)


def update_domain_createing_template(id_domain, template_field, status='CreatingTemplate'):
    r_conn = new_rethink_connection()
    rtable = r.table('domains')

    rtable.get(id_domain).update(
        {'template_json': template_field, 'status': status}).run(r_conn)
    close_rethink_connection(r_conn)


def update_table_field(table, id_doc, field, value, merge_dict=True):
    r_conn = new_rethink_connection()
    rtable = r.table(table)
    print(id_doc)
    print(field)
    if merge_dict is True:
        result = rtable.get(id_doc).update(
            {field: value}).run(r_conn)
    else:
        result = rtable.get(id_doc).update(
            {field: r.literal(value)}).run(r_conn)
    close_rethink_connection(r_conn)
    return result


class RethinkHypEvent(object):
    def __init__(self):
        pass

    def insert_event_in_db(self, dict_event):

        log.debug(pformat(dict_event))
        r_conn = new_rethink_connection()
        try:
            r.table('hypervisors_events').insert(dict_event).run(r_conn)
            close_rethink_connection(r_conn)
        except Exception as e:
            log.error('rethink insert hyp event fail: {}'.format(e))

    def update_viewer_client(self, domain_id, phase, ip_client=False, when=False):

        dict_viewer = {}
        r_conn = new_rethink_connection()

        # PHASE == 0 => CONNECTED
        if phase == 0:
            dict_viewer['client_addr'] = ip_client
            dict_viewer['client_since'] = when

        # PHASE == 1 => DISCONNECT
        if phase > 1:
            dict_viewer['client_addr'] = False
            dict_viewer['client_since'] = False

        rtable = r.table('domains')
        results = rtable.get(domain_id).update({'viewer': dict_viewer}).run(r_conn)

        close_rethink_connection(r_conn)
        return results

# ~ {
# ~ "id":  "014d0ca3-10b1-44c1-921f-4d20873c27b1" ,
# ~ "name":  "wifislax-clone" ,
# ~ "status": {
# ~ "cpu_usage": 0.009960226519167989 ,
# ~ "disk_rw": {
# ~ "block_r_bytes_per_sec": 0 ,
# ~ "block_r_reqs_per_sec": 0 ,
# ~ "block_w_bytes_per_sec": 0 ,
# ~ "block_w_reqs_per_sec": -4941.498376058712
# ~ } ,
# ~ "hyp":  "127.0.0.1" ,
# ~ "net_rw": {
# ~ "net_r_bytes_per_sec": 0 ,
# ~ "net_r_drop_per_sec": 0 ,
# ~ "net_r_errs_per_sec": 0 ,
# ~ "net_r_pkts_per_sec": 0 ,
# ~ "net_w_bytes_per_sec": 0 ,
# ~ "net_w_drop_per_sec": 0 ,
# ~ "net_w_errs_per_sec": 0 ,
# ~ "net_w_pkts_per_sec": 0
# ~ } ,
# ~ "procesed_stats": {
# ~ "block_r_bytes": 4814060 ,
# ~ "block_r_reqs": 2201 ,
# ~ "block_w_bytes": 4096 ,
# ~ "block_w_reqs": 1 ,
# ~ "cpu_time": 17.380056 ,
# ~ "net_r_bytes": 28338 ,
# ~ "net_r_drop": 0 ,
# ~ "net_r_errs": 0 ,
# ~ "net_r_pkts": 521 ,
# ~ "net_w_bytes": 0 ,
# ~ "net_w_drop": 0 ,
# ~ "net_w_errs": 0 ,
# ~ "net_w_pkts": 0 ,
# ~ "ram_current": 1048576 ,
# ~ "ram_defined": 1048576 ,
# ~ "state": 1 ,
# ~ "vcpus": 2
# ~ } ,
# ~ "raw_stats": {
# ~ "balloon.current": 1048576 ,
# ~ "balloon.maximum": 1048576 ,
# ~ "block.0.allocation": 0 ,
# ~ "block.0.capacity": 1172387840 ,
# ~ "block.0.fl.reqs": 0 ,
# ~ "block.0.fl.times": 0 ,
# ~ "block.0.name":  "hda" ,
# ~ "block.0.path":  "/libvirt/isos/wifislax-4-11-1-final.iso" ,
# ~ "block.0.physical": 1172393984 ,
# ~ "block.0.rd.bytes": 4329708 ,
# ~ "block.0.rd.reqs": 2111 ,
# ~ "block.0.rd.times": 1004989488 ,
# ~ "block.0.wr.bytes": 0 ,
# ~ "block.0.wr.reqs": 0 ,
# ~ "block.0.wr.times": 0 ,
# ~ "block.1.allocation": 396800 ,
# ~ "block.1.capacity": 10737418240 ,
# ~ "block.1.fl.reqs": 0 ,
# ~ "block.1.fl.times": 0 ,
# ~ "block.1.name":  "hdb" ,
# ~ "block.1.path":  "/libvirt/qcows/wifislax-clone.qcow2" ,
# ~ "block.1.physical": 5120466944 ,
# ~ "block.1.rd.bytes": 484352 ,
# ~ "block.1.rd.reqs": 90 ,
# ~ "block.1.rd.times": 189293051 ,
# ~ "block.1.wr.bytes": 4096 ,
# ~ "block.1.wr.reqs": 1 ,
# ~ "block.1.wr.times": 2123723 ,
# ~ "block.count": 2 ,
# ~ "cpu.system": 2490000000 ,
# ~ "cpu.time": 17380056284 ,
# ~ "cpu.user": 3130000000 ,
# ~ "net.0.name":  "vnet0" ,
# ~ "net.0.rx.bytes": 28338 ,
# ~ "net.0.rx.drop": 0 ,
# ~ "net.0.rx.errs": 0 ,
# ~ "net.0.rx.pkts": 521 ,
# ~ "net.0.tx.bytes": 0 ,
# ~ "net.0.tx.drop": 0 ,
# ~ "net.0.tx.errs": 0 ,
# ~ "net.0.tx.pkts": 0 ,
# ~ "net.count": 1 ,
# ~ "state.reason": 1 ,
# ~ "state.state": 1 ,
# ~ "vcpu.0.state": 1 ,
# ~ "vcpu.0.time": 5200000000 ,
# ~ "vcpu.1.state": 1 ,
# ~ "vcpu.1.time": 2000000000 ,
# ~ "vcpu.current": 2 ,
# ~ "vcpu.maximum": 2
# ~ } ,
# ~ "state":  "running" ,
# ~ "state_reason":  "booted"
# ~ } ,
# ~ "when": 1459290773.018546
