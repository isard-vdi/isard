# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import json
import queue
import threading
from contextlib import contextmanager
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


class RethinkDBConnectionPool:
    def __init__(self, pool_size):
        """Initialize the connection pool."""
        self._pool_size = pool_size
        self._pool = queue.Queue(maxsize=pool_size)
        self._lock = threading.Lock()

        # Pre-create connections to fill the pool
        for _ in range(pool_size):
            self._pool.put(self._create_connection())

    def _create_connection(self):
        """Create a new RethinkDB connection."""
        try:
            return r.connect(
                host=RETHINK_HOST,
                port=RETHINK_PORT,
                db=RETHINK_DB,
            )
        except r.errors.ReqlDriverError as e:
            print(f"RethinkDB connection failed: {e}")
            raise

    def get_connection(self):
        """Retrieve a connection from the pool."""
        try:
            return self._pool.get(timeout=60)  # Wait up to 60 seconds for a connection
        except queue.Empty:
            raise RuntimeError("No available connections in the pool.")

    def release_connection(self, conn):
        """Return a connection to the pool."""
        if conn and conn.is_open():
            self._pool.put(conn)

    def close_all_connections(self):
        """Close all connections in the pool."""
        with self._lock:
            while not self._pool.empty():
                conn = self._pool.get()
                if conn.is_open():
                    conn.close()


class PooledConnection:
    def __init__(self, pool):
        self.pool = pool
        self.connection = None

    def __enter__(self):
        self.connection = self.pool.get_connection()
        return self.connection

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pool.release_connection(self.connection)


connection_pool = RethinkDBConnectionPool(pool_size=10)


@contextmanager
def rethink_conn():
    with PooledConnection(connection_pool) as conn:
        yield conn


def get_dict_from_item_in_table(table, id):
    with rethink_conn() as conn:
        return r.table(table).get(id).run(conn)


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
    try:
        with rethink_conn() as conn:
            result = r.table(table).get(id_item).pluck(field).run(conn)
    except Exception as e:
        return None

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
    if merge_dict is True:
        with rethink_conn() as conn:
            return (
                r.table(table)
                .get(id_doc)
                .update({field: value}, durability=durability)
                .run(conn)
            )
    else:
        with rethink_conn() as conn:
            return (
                r.table(table)
                .get(id_doc)
                .update({field: r.literal(value)}, durability=durability)
                .run(conn)
            )


def update_table_dict(table, id_doc, dict, soft=False):
    durability = "hard" if soft is False else "soft"
    with rethink_conn() as conn:
        return r.table(table).get(id_doc).update(dict, durability=durability).run(conn)


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
    with rethink_conn() as conn:
        physical_devs = list(
            r.table("vgpus")
            .filter({"hyp_id": hyp_id})["id"]
            .coerce_to("array")
            .run(conn)
        )
    if len(physical_devs) != 0:
        with rethink_conn() as conn:
            r.table("gpus").filter(
                lambda gpu: r.expr(physical_devs).contains(gpu["physical_device"])
            ).update({"physical_device": None}).run(conn)
            r.table("vgpus").filter({"hyp_id": hyp_id}).delete().run(conn)


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
