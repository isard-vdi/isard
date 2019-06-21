# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import time
from pprint import pprint

# coding=utf-8
import rethinkdb as r

from engine.config import RETHINK_HOST, RETHINK_PORT, RETHINK_DB, MAX_QUEUE_DOMAINS_STATUS
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


def insert_event_in_db(self, dict_event):
    log.debug(pprint(dict_event))
    r_conn = new_rethink_connection()
    r.table('hypervisors_events').insert(dict_event).run(r_conn)
    close_rethink_connection(r_conn)



def get_dict_from_item_in_table(table, id):
    r_conn = new_rethink_connection()
    d = r.table(table).get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return d


def results_zero(results):
    return reduce(lambda a, b: a + b, results.values())


def get_xml_from_virt_viewer(id_virt_viewer):
    r_conn = new_rethink_connection()
    rtable = r.table('domains_virt_install')

    dict_domain = rtable.get(id_virt_viewer).run(r_conn)
    close_rethink_connection(r_conn)
    return dict_domain['xml']


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


def update_domain_viewer_started_values(id, hyp_id=False,
                                        spice=False,
                                        spice_tls=False,
                                        vnc=False,
                                        vnc_websocket=False,
                                        passwd=False):
    #
    # dict_event = {'domain':dom.name(),
    #               'hyp_id':hyp_id,
    #                'event':domEventToString(event),
    #               'detail':domDetailToString(event, detail),
    #                 'when':now}

    r_conn = new_rethink_connection()
    hostname_external = False

    if hyp_id is not False:
        rtable = r.table('hypervisors')
        d = rtable.get(hyp_id).pluck('viewer_hostname', 'viewer_nat_hostname','hostname', 'id').run(r_conn)
        if 'viewer_hostname' in d.keys():
            if len(d['viewer_hostname']) > 0:
                hostname = d['viewer_hostname']
            else:
                hostname = d['hostname']
        else:
            hostname = d['hostname']

        if 'viewer_nat_hostname' in d.keys():
            if len(d['viewer_nat_hostname']) > 0:
                hostname_external = d['viewer_nat_hostname']
            else:
                hostname_external = False
        else:
            hostname_external = False
    else:
        hostname = False
        hostname_external = False

    dict_viewer = {}
    if hostname is not None:
        dict_viewer['hostname'] = hostname
    else:
        dict_viewer['hostname'] = False

    dict_viewer['hostname_external'] = hostname_external
    dict_viewer['tlsport'] = spice_tls
    dict_viewer['port'] = spice
    dict_viewer['port_spice'] = spice
    dict_viewer['port_spice_ssl'] = spice_tls
    dict_viewer['port_vnc'] = vnc
    dict_viewer['port_vnc_websocket'] = vnc_websocket
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


def get_engine():
    r_conn = new_rethink_connection()
    rtable = r.table('engine')
    engine = list(rtable.run(r_conn))[0]
    close_rethink_connection(r_conn)
    return engine

def get_pool(id_pool):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors_pools')
    pool = rtable.get(id_pool).run(r_conn)
    close_rethink_connection(r_conn)
    return pool


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


def get_pools_from_hyp(hyp_id):
    r_conn = new_rethink_connection()
    rtable = r.table('hypervisors')

    d = rtable.get(hyp_id).pluck('hypervisors_pools').run(r_conn)

    close_rethink_connection(r_conn)
    return d['hypervisors_pools']


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


def get_domains_from_classroom(classroom):
    return []


def get_domains_running_hypervisor(hyp_id):
    return []


def get_domains_from_template_origin():
    return []


def update_table_field(table, id_doc, field, value, merge_dict=True):
    r_conn = new_rethink_connection()
    rtable = r.table(table)
    if merge_dict is True:
        result = rtable.get(id_doc).update(
            {field: value}).run(r_conn)
    else:
        result = rtable.get(id_doc).update(
            {field: r.literal(value)}).run(r_conn)
    close_rethink_connection(r_conn)
    return result

def get_user(id):
    r_conn = new_rethink_connection()
    rtable = r.table('users')

    dict_user = rtable.get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return dict_user

def update_quota_user(id_user,running_desktops, quota_desktops,quota_templates,mem_max,num_cpus):
    r_conn = new_rethink_connection()
    rtable = r.table('users')

    d = { 'quota': {'domains': {'desktops': quota_desktops,
                               'running': running_desktops,
                               'templates': quota_templates},
                              'hardware': {'memory': mem_max, 'vcpus': num_cpus}}}

    result = rtable.get(id_user).update(d).run(r_conn)

    close_rethink_connection(r_conn)
    return result

def remove_media(id):
    r_conn = new_rethink_connection()
    rtable = r.table('media')

    result = rtable.get(id).delete().run(r_conn)
    close_rethink_connection(r_conn)
    return result

def get_media_with_status(status):
    """
    get media with status
    :param status
    :return: list id_domains
    """
    r_conn = new_rethink_connection()
    rtable = r.table('media')
    try:
        results = rtable.get_all(status, index='status').pluck('id').run(r_conn)
        close_rethink_connection(r_conn)
    except:
        # if results is None:
        close_rethink_connection(r_conn)
        return []
    return [d['id'] for d in results]

def get_graphics_types(id_graphics='default'):
    """
    get spice graphics options like compression, audio...
    :param id_graphics:
    :return:
    """
    r_conn = new_rethink_connection()
    rtable = r.table('graphics')
    try:
        types = rtable.get(id_graphics).pluck('types').run(r_conn)
        d_types = types['types']
    except:
        d_types = None
    close_rethink_connection(r_conn)

    return d_types