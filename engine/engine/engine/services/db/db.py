# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import json
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


def get_hyp_viewer_info(hyp_id):
    r_conn = new_rethink_connection()
    h = (
        r.table("hypervisors")
        .get(hyp_id)
        .pluck("hypervisors_pools", "viewer", "id")
        .run(r_conn)
    )
    hp = (
        r.table("hypervisors_pools")
        .get(h["hypervisors_pools"][0])
        .pluck("viewer")
        .run(r_conn)
    )
    close_rethink_connection(r_conn)
    return {"viewer": h["viewer"], "tls": hp["viewer"]}


def update_domain_viewer_passwd(domain_id, passwd):
    r_conn = new_rethink_connection()
    r.table("domains").get(domain_id).update({"viewer": {"passwd": passwd}}).run(r_conn)
    close_rethink_connection(r_conn)


def update_domain_viewer_started_values(
    domain_id,
    hyp_id,
    hyp_viewer,
    hyp_tls,
    spice=False,
    spice_tls=False,
    vnc=False,
    vnc_websocket=False,
    status=None,
    detail=None,
):
    r_conn = new_rethink_connection()
    try:
        update_dict = {
            "viewer": {
                "static": hyp_viewer["static"],
                "proxy_video": hyp_viewer["proxy_video"],
                "html5_ext_port": hyp_viewer["html5_ext_port"],
                "spice_ext_port": hyp_viewer["spice_ext_port"],
                "proxy_hyper_host": hyp_viewer["proxy_hyper_host"],
                "base_port": int(spice),
                "ports": [int(spice), int(spice_tls), int(vnc), int(vnc_websocket)],
                "client_addr": False,
                "client_since": False,
                "tls": hyp_tls,
            }
        }
        if status is not None:
            log.info(f"status: {status}")
            update_dict["status"] = status
            update_dict["detail"] = json.dumps(detail)
            update_dict["hyp_started"] = hyp_id
        r.table("domains").get(domain_id).update(update_dict).run(r_conn)
    except Exception as e:
        log.error(
            f"exception in update_domain_viewer_started_values for domain {domain_id}: {e}"
        )
    close_rethink_connection(r_conn)


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


def insert_table_dict(table, d_new, ignore_if_exists=False):
    r_conn = new_rethink_connection()
    rtable = r.table(table)

    rtable.insert(d_new).run(r_conn)
    close_rethink_connection(r_conn)


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

    rtable.get(id_item).delete().run(r_conn)
    close_rethink_connection(r_conn)


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


def update_table_dict(table, id_doc, dict, soft=False):
    durability = "hard" if soft is False else "soft"
    r_conn = new_rethink_connection()
    result = r.table(table).get(id_doc).update(dict, durability=durability).run(r_conn)
    close_rethink_connection(r_conn)
    return result


def remove_media(id):
    r_conn = new_rethink_connection()
    rtable = r.table("media")

    rtable.get(id).delete().run(r_conn)
    close_rethink_connection(r_conn)


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


def cleanup_hypervisor_gpus(hyp_id: str):
    r_conn = new_rethink_connection()

    physical_devs = list(
        r.table("vgpus").filter({"hyp_id": hyp_id})["id"].coerce_to("array").run(r_conn)
    )
    if len(physical_devs) != 0:
        r.table("gpus").filter(
            lambda gpu: r.expr(physical_devs).contains(gpu["physical_device"])
        ).update({"physical_device": None}).run(r_conn)
        r.table("vgpus").filter({"hyp_id": hyp_id}).delete().run(r_conn)

    close_rethink_connection(r_conn)


## In unused functions


def get_pools_from_hyp(hyp_id):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors")

    d = rtable.get(hyp_id).pluck("hypervisors_pools").run(r_conn)

    close_rethink_connection(r_conn)
    return d["hypervisors_pools"]


def get_pool(id_pool):
    r_conn = new_rethink_connection()
    rtable = r.table("hypervisors_pools")
    pool = rtable.get(id_pool).run(r_conn)
    close_rethink_connection(r_conn)
    return pool


def get_domains_from_classroom(classroom):
    return []


def get_domains_running_hypervisor(hyp_id):
    return []


def get_domains_from_template_origin():
    return []


def get_user(id):
    r_conn = new_rethink_connection()
    rtable = r.table("users")

    dict_user = rtable.get(id).run(r_conn)
    close_rethink_connection(r_conn)
    return dict_user
