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
