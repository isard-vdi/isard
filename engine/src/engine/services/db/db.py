# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import json
import os
from contextlib import contextmanager
from functools import wraps

from isardvdi_common.connections.rethink_shared_connection import make_query_observer
from rethinkdb import r
from rethinkdb.connection_pool import ThreadSafeConnectionPool

from engine.config import (
    MAX_QUEUE_DOMAINS_STATUS,
    RETHINK_DB,
    RETHINK_HOST,
    RETHINK_PORT,
)
from engine.services.log import *

MAX_LEN_PREV_STATUS_HYP = 10

# Bound on how long ``acquire`` may block waiting for a free pool slot
# before raising ``PoolExhaustedError`` (a ``ReqlDriverError`` subclass).
# Engine paths used to block on ``queue.get(timeout=60)`` and surface
# pool exhaustion as an opaque ``RuntimeError`` no caller could
# distinguish from a generic bug. The new fast-fail mirrors what
# ``_common``'s shared pool already does for apiv4 / change-handler /
# scheduler / webapp / vpn.
_ACQUIRE_TIMEOUT_S = float(os.environ.get("RETHINKDB_ACQUIRE_TIMEOUT_SEC", "30"))

# Engine has long-lived worker threads (ThreadHypEvents,
# manager_pooling, hypervisor workers) that go quiet for 10+ minutes
# between queries. The default 300s eviction would
# make every cold-path query pay a TCP/TLS handshake; bump to keep
# steady-state warm without holding sockets open forever after a
# real traffic drop.
_MAX_IDLE_TIME_S = float(os.environ.get("RETHINKDB_POOL_IDLE_SEC", "1800"))


_pool_size = int(os.environ.get("RETHINKDB_POOL_SIZE", "50"))


def _connection_factory():
    """Build a fresh blocking RethinkDB connection for the engine pool.

    Wires the slow-/failed-query observer so engine queries surface
    in the ``rdb_query_slow`` / ``rdb_query_failed`` log stream the
    rest of the monorepo grep'd by Loki. The observer is built via
    ``make_query_observer(connection_pool)`` so its enrichment
    fields carry *engine's* pool size / in_use / idle / max_size,
    not `_common`'s shared pool — the two are distinct instances.
    """
    try:
        conn = r.connect(
            host=RETHINK_HOST,
            port=RETHINK_PORT,
            db=RETHINK_DB,
        )
    except r.errors.ReqlDriverError as e:
        logs.main.error(f"RethinkDB connection failed: {e}")
        raise
    conn.add_query_observer(on_end=_query_observer_on_end)
    return conn


# The fork's pool grows on demand up to ``max_size`` and evicts idle
# connections after ``max_idle_time`` — no eager pre-create. The
# legacy hand-rolled pool opened all 50 sockets at module import,
# which both delayed boot and pinned 50 server-side slots regardless
# of actual concurrency.
connection_pool = ThreadSafeConnectionPool(
    connection_factory=_connection_factory,
    max_size=_pool_size,
    max_idle_time=_MAX_IDLE_TIME_S,
)

# Build the observer AFTER the pool exists so it can capture
# pool-stats from the engine pool on every emitted line. The
# factory function takes a closure over ``connection_pool`` — the
# rdb driver's observer-list snapshot makes this safe to register
# once per connection at factory time.
_query_observer_on_end = make_query_observer(connection_pool)


def new_rethink_connection():
    """Acquire a connection from the engine's pool.

    Legacy callsites still use the ``new_rethink_connection()`` /
    ``close_rethink_connection()`` shape; rather than rewrite the
    ~93 historical callsites in one go, route both functions through
    the fork's ``ThreadSafeConnectionPool``. The pool grows on demand
    up to ``RETHINKDB_POOL_SIZE`` (default 50). On exhaustion this
    raises ``PoolExhaustedError`` (a ``ReqlDriverError`` subclass)
    after ``RETHINKDB_ACQUIRE_TIMEOUT_SEC`` instead of the legacy
    opaque ``RuntimeError``. The caller MUST release the connection
    via ``close_rethink_connection`` so the slot returns to the pool.
    """
    return connection_pool.acquire(timeout=_ACQUIRE_TIMEOUT_S)


def close_rethink_connection(r_conn):
    """Release a connection back to the engine's pool.

    Mirrors ``new_rethink_connection`` above: returns the slot to
    the pool so the next caller reuses it. The fork's pool validates
    ``is_open()`` on release and silently drops dead connections
    (with a warning log via ``_is_usable``); the next acquire grows
    a fresh socket if needed. Returns ``True`` for source compat
    with callers that propagate the legacy return value.
    """
    if r_conn is not None:
        connection_pool.release(r_conn)
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


@contextmanager
def rethink_conn():
    conn = connection_pool.acquire(timeout=_ACQUIRE_TIMEOUT_S)
    try:
        yield conn
    finally:
        connection_pool.release(conn)


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
            affected = (
                r.table("gpus")
                .filter(
                    lambda gpu: r.expr(physical_devs).contains(gpu["physical_device"])
                )
                .concat_map(lambda gpu: gpu["profiles_enabled"].default([]))
                .distinct()
                .run(conn)
            )
            r.table("gpus").filter(
                lambda gpu: r.expr(physical_devs).contains(gpu["physical_device"])
            ).update({"physical_device": None}).run(conn)
            r.table("vgpus").filter({"hyp_id": hyp_id}).delete().run(conn)
            # Detached cards have no hardware -> recompute capacity so
            # reservables_vgpus.total_units stops counting them (mirrors the API
            # ResourceItemsGpus.recompute_total_units; profiles_enabled and
            # bookings are preserved so capacity recovers if the host returns).
            for reservable_id in affected:
                surv = r.table("reservables_vgpus").get(reservable_id).run(conn)
                if not surv:
                    continue
                cards = (
                    r.table("gpus")
                    .filter(
                        lambda g: g["profiles_enabled"].contains(reservable_id)
                        & g["physical_device"].default(None).ne(None)
                    )
                    .count()
                    .run(conn)
                )
                r.table("reservables_vgpus").get(reservable_id).update(
                    {"total_units": cards * (surv.get("units") or 0)}
                ).run(conn)


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
