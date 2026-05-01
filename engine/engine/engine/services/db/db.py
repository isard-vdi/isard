# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import json
import queue
import threading
from contextlib import contextmanager
from functools import wraps

from rethinkdb import r

from engine.config import (
    MAX_QUEUE_DOMAINS_STATUS,
    RETHINK_DB,
    RETHINK_HOST,
    RETHINK_PORT,
)
from engine.services.log import *

MAX_LEN_PREV_STATUS_HYP = 10


def new_rethink_connection():
    """Acquire a connection from the engine's pool.

    Legacy callsites still use the ``new_rethink_connection()`` /
    ``close_rethink_connection()`` shape; rather than rewrite them
    all in one go, route both functions through the existing
    ``connection_pool``. The pool pre-allocates ``RETHINKDB_POOL_SIZE``
    sockets at startup; per-call cost drops from a TCP/TLS handshake
    to a queue.get(). The caller MUST release the connection via
    ``close_rethink_connection`` so the slot returns to the pool.

    The bare ``r.connect(...)`` form previously used here meant every
    call opened a fresh socket the rdb server then had to terminate.
    Under load (50+ concurrent engine threads) that thrashed the
    server's connection budget and blocked on the handshake.
    """
    return connection_pool.get_connection()


def close_rethink_connection(r_conn):
    """Release a connection back to the engine's pool.

    Mirrors ``new_rethink_connection`` above: this used to do
    ``r_conn.close()``, now it returns the slot to the pool so the
    next caller reuses it. Returns ``True`` for source compatibility
    with callers that propagate the legacy return value.
    """
    if r_conn is not None:
        connection_pool.release_connection(r_conn)
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
        self._in_use = 0

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
            logs.main.error(f"RethinkDB connection failed: {e}")
            raise

    def get_connection(self):
        """Retrieve a connection from the pool."""
        try:
            conn = self._pool.get(timeout=60)
            with self._lock:
                self._in_use += 1
            logs.main.debug(
                f"rethinkdb connection acquired (in_use={self._in_use}, idle={self._pool.qsize()}, pool_size={self._pool_size})"
            )
            return conn
        except queue.Empty:
            raise RuntimeError("No available connections in the pool.")

    def release_connection(self, conn):
        """Return a connection to the pool."""
        if conn and conn.is_open():
            self._pool.put(conn)
        else:
            try:
                self._pool.put(self._create_connection())
                logs.main.warning("Replaced dead RethinkDB connection in pool")
            except Exception as e:
                logs.main.error(f"Failed to replace dead connection in pool: {e}")
        with self._lock:
            self._in_use = max(0, self._in_use - 1)
        logs.main.debug(
            f"rethinkdb connection released (in_use={self._in_use}, idle={self._pool.qsize()}, pool_size={self._pool_size})"
        )

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


import os

_pool_size = int(os.environ.get("RETHINKDB_POOL_SIZE", "50"))
connection_pool = RethinkDBConnectionPool(pool_size=_pool_size)


@contextmanager
def rethink_conn():
    with PooledConnection(connection_pool) as conn:
        yield conn


def get_dict_from_item_in_table(table, id):
    with rethink_conn() as conn:
        return r.table(table).get(id).run(conn)


def get_hyp_viewer_info(hyp_id):
    with rethink_conn() as r_conn:
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
    return {"viewer": h["viewer"], "tls": hp["viewer"]}


def update_domain_viewer_passwd(domain_id, passwd):
    with rethink_conn() as r_conn:
        r.table("domains").get(domain_id).update({"viewer": {"passwd": passwd}}).run(
            r_conn
        )


def update_domain_viewer_started_values(
    domain_id,
    hyp_id,
    hyp_viewer,
    hyp_tls,
    spice=False,
    spice_tls=False,
    vnc=False,
    vnc_websocket=False,
    viewer_passwd="",
    status=None,
    detail=None,
):
    try:
        update_dict = {
            "viewer": {
                "passwd": viewer_passwd,
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
        with rethink_conn() as r_conn:
            r.table("domains").get(domain_id).update(update_dict).run(r_conn)
    except Exception as e:
        log.error(
            f"exception in update_domain_viewer_started_values for domain {domain_id}: {e}"
        )


def get_interface(id):
    rtable = r.table("interfaces")

    try:
        with rethink_conn() as r_conn:
            dict_domain = rtable.get(id).run(r_conn)
    except:
        log.error(f"interface with id {id} not defined in database table interfaces")
        dict_domain = None

    return dict_domain


def create_list_buffer_history_domain(
    new_status, when, history_domain, detail="", hyp_id=""
):
    d = {"when": when, "status": new_status, "detail": detail, "hyp_id": hyp_id}

    new_history_domain = [d] + history_domain[:MAX_QUEUE_DOMAINS_STATUS]
    return new_history_domain


def insert_table_dict(table, d_new, ignore_if_exists=False):
    rtable = r.table(table)

    with rethink_conn() as r_conn:
        rtable.insert(d_new).run(r_conn)


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
        with rethink_conn() as r_conn:
            return rtable.get(id_item).pluck(fields).run(r_conn)
    except Exception as e:
        return None


def delete_table_item(table, id_item):
    rtable = r.table(table)

    with rethink_conn() as r_conn:
        rtable.get(id_item).delete().run(r_conn)


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
    rtable = r.table("media")

    with rethink_conn() as r_conn:
        rtable.get(id).delete().run(r_conn)


def get_media_with_status(status):
    """
    get media with status
    :param status
    :return: list id_domains
    """
    rtable = r.table("media")
    try:
        with rethink_conn() as r_conn:
            results = rtable.get_all(status, index="status").pluck("id").run(r_conn)
    except:
        return []
    return [d["id"] for d in results]


def get_graphics_types(id_graphics="default"):
    """
    get spice graphics options like compression, audio...
    :param id_graphics:
    :return:
    """
    rtable = r.table("graphics")
    try:
        with rethink_conn() as r_conn:
            types = rtable.get(id_graphics).pluck("types").run(r_conn)
        d_types = types["types"]
    except:
        d_types = None

    return d_types


def get_isardvdi_secret():
    with rethink_conn() as r_conn:
        return (
            r.table("secrets")
            .get("isardvdi")
            .pluck("secret")
            .default({"secret": os.environ["API_ISARDVDI_SECRET"]})
            .run(r_conn)["secret"]
        )


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
    rtable = r.table("hypervisors")

    with rethink_conn() as r_conn:
        d = rtable.get(hyp_id).pluck("hypervisors_pools").run(r_conn)

    return d["hypervisors_pools"]


def get_pool(id_pool):
    rtable = r.table("hypervisors_pools")
    with rethink_conn() as r_conn:
        return rtable.get(id_pool).run(r_conn)


def get_domains_from_classroom(classroom):
    return []


def get_domains_running_hypervisor(hyp_id):
    return []


def get_domains_from_template_origin():
    return []


def get_user(id):
    rtable = r.table("users")

    with rethink_conn() as r_conn:
        return rtable.get(id).run(r_conn)
