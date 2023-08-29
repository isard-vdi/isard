# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import time
from functools import wraps

from engine.config import (
    MAX_QUEUE_DOMAINS_STATUS,
    RETHINK_DB,
    RETHINK_HOST,
    RETHINK_PORT,
)
from engine.services.log import *
from rethinkdb import r

MAX_LEN_PREV_STATUS_HYP = 10


def new_rethink_connection():
    r_conn = r.connect(RETHINK_HOST, RETHINK_PORT, db=RETHINK_DB)
    # r_conn = r.connect("localhost", 28015, db='isard')
    return r_conn


def close_rethink_connection(r_conn):
    r_conn.close()
    del r_conn
    return True


def rethink(function):
    @wraps(function)
    def decorate(*args, **kwargs):
        connection = new_rethink_connection()
        try:
            result = function(connection, *args, **kwargs)
        finally:
            close_rethink_connection(connection)
        return result

    return decorate


def get_dict_from_item_in_table(table, id):
    r_conn = new_rethink_connection()
    d = r.table(table).get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return d


def get_xml_from_virt_viewer(id_virt_viewer):
    r_conn = new_rethink_connection()
    rtable = r.table("domains_virt_install")

    dict_domain = rtable.get(id_virt_viewer).run(r_conn)
    close_rethink_connection(r_conn)
    return dict_domain["xml"]


def get_ferrary(id):
    r_conn = new_rethink_connection()
    rtable = r.table("ferrarys")

    results = rtable.get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return results["ferrary"]


def update_domain_viewer_started_values(
    id,
    hyp_id=False,
    spice=False,
    spice_tls=False,
    vnc=False,
    vnc_websocket=False,
    passwd=False,
):
    #
    # dict_event = {'domain':dom.name(),
    #               'hyp_id':hyp_id,
    #                'event':domEventToString(event),
    #               'detail':domDetailToString(event, detail),
    #                 'when':now}

    r_conn = new_rethink_connection()
    hostname_external = False

    if hyp_id is False:
        dict_viewer = {
            "static": False,
            "proxy_video": False,
            "proxy_hyper_host": False,
            "base_port": spice if spice is not False else False,
            "ports": [],
            "passwd": passwd if passwd is not False else False,
            "client_addr": False,
            "client_since": False,
            "tls": False,
        }
        # ~ dict_viewer = { 'base_port':    spice if spice is not False else False,
        # ~ 'passwd':       passwd if passwd is not False else False,
        # ~ }
    else:
        rtable = r.table("hypervisors")
        try:
            h = (
                rtable.get(hyp_id)
                .pluck("hypervisors_pools", "viewer", "id")
                .run(r_conn)
            )

            rtable = r.table("hypervisors_pools")
            hp = rtable.get(h["hypervisors_pools"][0]).pluck("viewer").run(r_conn)
            dict_viewer = {
                "static": h["viewer"]["static"],
                "proxy_video": h["viewer"]["proxy_video"],
                "html5_ext_port": h["viewer"]["html5_ext_port"],
                "spice_ext_port": h["viewer"]["spice_ext_port"],
                "proxy_hyper_host": h["viewer"]["proxy_hyper_host"],
                "base_port": int(spice),
                "ports": [int(spice), int(spice_tls), int(vnc), int(vnc_websocket)],
                # ~ 'passwd':       passwd,
                "client_addr": False,
                "client_since": False,
                "tls": hp["viewer"],
            }
        except Exception as e:
            logs.exception_id.debug("0040")
            log.error("hypervisor withouth viewer dict or pool withough viewer dict")
            log.error(e)
            dict_viewer = {
                "static": False,
                "proxy_video": False,
                "proxy_hyper_host": False,
                "base_port": spice if spice is not False else False,
                "passwd": passwd if passwd is not False else False,
                "client_addr": False,
                "client_since": False,
                "tls": False,
            }
    if passwd is not False:
        dict_viewer["passwd"] = passwd
    results = r.table("domains").get(id).update({"viewer": dict_viewer}).run(r_conn)

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
    rtable = r.table("engine")
    engine = list(rtable.run(r_conn))[0]
    close_rethink_connection(r_conn)
    return engine


def get_pool(id_pool):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors_pools")
    pool = rtable.get(id_pool).run(r_conn)
    close_rethink_connection(r_conn)
    return pool


def update_pool_round_robin(round_robin_index, type_path, id_pool="default"):
    r_conn = new_rethink_connection()
    rtable = r.table("storage_pool")
    result = (
        rtable.get(id_pool)
        .update({"round_robin_indexes": {type_path: round_robin_index}})
        .run(r_conn)
    )
    close_rethink_connection(r_conn)


# def update_domain_hyp_started(domain_id,hyp_id,detail=''):
#     r_conn = new_rethink_connection()
#     rtable=r.table('domains')
#
#     result = rtable.filter({'id':domain_id}).update({'hyp_started':hyp_id,'detail':detail}).run(r_conn, durability="soft", noreply=True)
#     close_rethink_connection(r_conn)
#     return result


def get_interface(id):
    r_conn = new_rethink_connection()
    rtable = r.table("interfaces")

    try:
        dict_domain = rtable.get(id).run(r_conn)
    except:
        log.error(f"interface with id {id} not defined in database table interfaces")
        dict_domain = None

    close_rethink_connection(r_conn)
    return dict_domain


def create_list_buffer_history_domain(
    new_status, when, history_domain, detail="", hyp_id=""
):
    d = {"when": when, "status": new_status, "detail": detail, "hyp_id": hyp_id}

    new_history_domain = [d] + history_domain[:MAX_QUEUE_DOMAINS_STATUS]
    return new_history_domain

    # buffer_history_domain = deque(maxlen=MAX_QUEUE_DOMAINS_STATUS)
    # buffer_history_domain.extend(reversed(history_domain))
    # buffer_history_domain.appendleft(d)
    # return list(buffer_history_domain)


def insert_place(
    id_place,
    name,
    rows,
    cols,
    network=None,
    enabled=True,
    description="",
    ssh_enable=False,
    ssh_user="",
    ssh_pwd=None,
    ssh_port=22,
    ssh_key_path="",
):
    r_conn = new_rethink_connection()
    rtable = r.table("places")

    rtable.insert(
        {
            "id": id_place,
            "name": name,
            "description": description,
            "enabled": enabled,
            "status": "Unmanaged",  # Unmanaged / Managed
            "detail": "new place created",
            "events_pending": [],
            "events_processed": [],
            "managed_by_user": None,
            "dimensions": {"w": cols, "h": rows},
            "network": network,
            "ssh": {
                "enabled": ssh_enable,
                "user": ssh_user,
                "pwd": ssh_pwd,
                "port": ssh_port,
                "ssh_key": ssh_key_path,
            },
            "stats": {
                "total_hosts": 0,
                "total_ping": 0,
                "total_login": 0,
                "total_desktops": 0,
                "total_viewers": 0,
                "total_vcpus": 0,
                "total_memory": 0,
            },
        }
    ).run(r_conn)

    close_rethink_connection(r_conn)


def insert_host_viewer(
    hostname, description, place_id, ip, row, col, mac=None, enabled=True
):
    r_conn = new_rethink_connection()
    rtable = r.table("hosts_viewers")

    rtable.insert(
        {
            "hostname": hostname,
            "place_id": place_id,
            "id": ip,
            "position": {"row": row, "col": col, "size_x": 1, "size_y": 1},
            "description": description,
            "mac": mac,
            "enabled": enabled,
            "status": "Offline",  # Offline, online, ready_to_launch_ssh_commands
            "logged_user": None,
            "desktops_running": [],
            "status_time": int(time.time()),
        }
    ).run(r_conn)

    close_rethink_connection(r_conn)


def get_pools_from_hyp(hyp_id):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")

    d = rtable.get(hyp_id).pluck("hypervisors_pools").run(r_conn)

    close_rethink_connection(r_conn)
    return d["hypervisors_pools"]


def insert_action(id_action, parameters, debug=False):
    r_conn = new_rethink_connection()
    rtable = r.table("actions")

    d = {
        "action": id_action,
        "parameters": parameters,
        "debug": debug,
        "when": int(time.time()),
    }
    result = rtable.insert(d).run(r_conn)
    close_rethink_connection(r_conn)

    return result


def get_domains_from_classroom(classroom):
    return []


def get_domains_running_hypervisor(hyp_id):
    return []


def get_domains_from_template_origin():
    return []


def insert_table_dict(table, d_new, ignore_if_exists=False):
    r_conn = new_rethink_connection()
    rtable = r.table(table)

    result = rtable.insert(d_new).run(r_conn)
    close_rethink_connection(r_conn)

    if result["inserted"] > 0:
        return True
    if result["errors"] > 0:
        if (
            ignore_if_exists is True
            and result["first_error"].find("Duplicate primary key") == 0
        ):
            return True
        else:
            print(result["first_error"])
    return False


def get_table_item(table, id_item):
    r_conn = new_rethink_connection()
    rtable = r.table(table)

    result = rtable.get(id_item).run(r_conn)
    close_rethink_connection(r_conn)
    return result


def get_table_field(table, id_item, field):
    r_conn = new_rethink_connection()
    rtable = r.table(table)

    try:
        result = rtable.get(id_item).pluck(field).run(r_conn)
    except Exception as e:
        close_rethink_connection(r_conn)
        return None
    close_rethink_connection(r_conn)
    if type(field) is dict and type(result) is dict:
        return result
    if type(result) is dict:
        return result.get(field, None)
    return None


def get_table_fields(table, id_item, fields):
    rtable = r.table(table)
    try:
        r_conn = new_rethink_connection()
        result = rtable.get(id_item).pluck(fields).run(r_conn)
        close_rethink_connection(r_conn)
        return result
    except Exception as e:
        close_rethink_connection(r_conn)
        return None


def delete_table_item(table, id_item):
    r_conn = new_rethink_connection()
    rtable = r.table(table)

    result = rtable.get(id_item).delete().run(r_conn)
    close_rethink_connection(r_conn)
    if result["deleted"] > 0:
        return True
    if result["errors"] > 0:
        print(result["first_error"])
    return False


def update_table_field(table, id_doc, field, value, merge_dict=True, soft=False):
    durability = "hard" if soft is False else "soft"
    r_conn = new_rethink_connection()
    rtable = r.table(table)
    if merge_dict is True:
        result = (
            rtable.get(id_doc).update({field: value}, durability=durability).run(r_conn)
        )
    else:
        result = (
            rtable.get(id_doc)
            .update({field: r.literal(value)}, durability=durability)
            .run(r_conn)
        )
    close_rethink_connection(r_conn)
    return result


def update_table_dict(table, id_doc, dict):
    r_conn = new_rethink_connection()
    result = r.table(table).get(id_doc).update(dict).run(r_conn)
    close_rethink_connection(r_conn)
    return result


def get_user(id):
    r_conn = new_rethink_connection()
    rtable = r.table("users")

    dict_user = rtable.get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return dict_user


def update_quota_user(
    id_user, running_desktops, quota_desktops, quota_templates, mem_max, num_cpus
):
    r_conn = new_rethink_connection()
    rtable = r.table("users")

    d = {
        "quota": {
            "domains": {
                "desktops": quota_desktops,
                "running": running_desktops,
                "templates": quota_templates,
            },
            "hardware": {"memory": mem_max, "vcpus": num_cpus},
        }
    }

    result = rtable.get(id_user).update(d).run(r_conn)

    close_rethink_connection(r_conn)
    return result


def remove_media(id):
    r_conn = new_rethink_connection()
    rtable = r.table("media")

    result = rtable.get(id).delete().run(r_conn)
    close_rethink_connection(r_conn)
    return result


def get_video_model_profile(video_id):
    r_conn = new_rethink_connection()
    rtable = r.table("videos")

    result = rtable.get(video_id).pluck("model", "profile").run(r_conn)
    close_rethink_connection(r_conn)
    if result is None:
        return None, None
    else:
        return result.get("model", None), result.get("profile", None)


def get_media_with_status(status):
    """
    get media with status
    :param status
    :return: list id_domains
    """
    r_conn = new_rethink_connection()
    rtable = r.table("media")
    try:
        results = rtable.get_all(status, index="status").pluck("id").run(r_conn)
        close_rethink_connection(r_conn)
    except:
        # if results is None:
        close_rethink_connection(r_conn)
        return []
    return [d["id"] for d in results]


def get_graphics_types(id_graphics="default"):
    """
    get spice graphics options like compression, audio...
    :param id_graphics:
    :return:
    """
    r_conn = new_rethink_connection()
    rtable = r.table("graphics")
    try:
        types = rtable.get(id_graphics).pluck("types").run(r_conn)
        d_types = types["types"]
    except:
        d_types = None
    close_rethink_connection(r_conn)

    return d_types


def get_isardvdi_secret():
    r_conn = new_rethink_connection()
    d = (
        r.table("secrets")
        .get("isardvdi")
        .pluck("secret")
        .default({"secret": os.environ["API_ISARDVDI_SECRET"]})
        .run(r_conn)["secret"]
    )
    close_rethink_connection(r_conn)
    return d
