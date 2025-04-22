#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback

from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from cachetools import TTLCache, cached

from .caches import get_user_client_ip
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


@cached(
    cache=TTLCache(maxsize=128, ttl=10),
    key=lambda kind, client_ip, remote_ip=None, remote_port=None, status=False: (
        str(kind),
        str(client_ip),
        str(remote_ip) if remote_ip is not None else "",
        str(remote_port) if remote_port is not None else "",
        str(status),
    ),
)
def active_client(
    kind,
    client_ip,
    remote_ip=None,
    remote_port=None,
    status=False,
):
    # NOTE: Kind will be users/hypers as this are the only two wireguard
    #       interfaces. Remotevpn are handled in users wg interface.
    if kind not in ["users", "hypers"]:
        raise Error(
            "not_found",
            "Active client vpn connection: Vpn kind " + str(kind) + " not found",
            traceback.format_exc(),
            description_code="vpn_kind_not_found",
        )

    connection_data = {
        "connected": status,
        "remote_ip": remote_ip,
        "remote_port": remote_port,
    }

    # Find ip
    if kind == "users":
        with app.app_context():
            if len(
                list(
                    r.table("remotevpn")
                    .get_all(client_ip, index="wg_client_ip")
                    .run(db.conn)
                )
            ):
                r.table("remotevpn").get_all(client_ip, index="wg_client_ip").update(
                    {"vpn": {"wireguard": connection_data}}
                ).run(db.conn)
                return True
        user_id = get_user_client_ip().get(client_ip)
        if user_id is None:
            return False
        with app.app_context():
            r.table("users").get(user_id).update(
                {"vpn": {"wireguard": connection_data}}
            ).run(db.conn)
        return True
    else:  # kind = hypers
        with app.app_context():
            r.table("hypervisors").get_all(client_ip, index="wg_client_ip").update(
                {"vpn": {"wireguard": connection_data}}
            ).run(db.conn)
        return True


def reset_connection_status(
    kind,
):
    if kind not in ["users", "hypers", "all"]:
        raise Error(
            "not_found",
            "Reset vpn connection: Vpn kind " + str(kind) + " not found",
            traceback.format_exc(),
            description_code="vpn_kind_not_found",
        )
    connection_data = {"connected": False, "remote_ip": None, "remote_port": None}

    # Find ip
    if kind in ["users", "all"]:
        with app.app_context():
            r.table("users").has_fields({"vpn": {"wireguard": "Address"}}).update(
                {"vpn": {"wireguard": connection_data}}
            ).run(db.conn)
    if kind in ["remotevpn", "all"]:
        with app.app_context():
            r.table("remotevpn").has_fields({"vpn": {"wireguard": "Address"}}).update(
                {"vpn": {"wireguard": connection_data}}
            ).run(db.conn)
    if kind in ["hypers", "all"]:
        with app.app_context():
            r.table("hypervisors").has_fields({"vpn": {"wireguard": "Address"}}).update(
                {"vpn": {"wireguard": connection_data}}
            ).run(db.conn)
    return True


def reset_connections_list_status(
    data,
):
    connection_data = {"connected": False, "remote_ip": None, "remote_port": None}
    users_vpn_ips = [d["client_ip"] for d in data if d["kind"] == "users"]
    if len(users_vpn_ips):
        with app.app_context():
            r.table("users").get_all(
                r.args(users_vpn_ips), index="wg_client_ip"
            ).update({"vpn": {"wireguard": connection_data}}).run(db.conn)
        with app.app_context():
            r.table("remotevpn").get_all(
                r.args(users_vpn_ips), index="wg_client_ip"
            ).update({"vpn": {"wireguard": connection_data}}).run(db.conn)

    hypers_vpn_ips = [d["client_ip"] for d in data if d["kind"] == "hypers"]
    if len(hypers_vpn_ips):
        with app.app_context():
            r.table("hypervisors").get_all(
                r.args(hypers_vpn_ips), index="wg_client_ip"
            ).update({"vpn": {"wireguard": connection_data}}).run(db.conn)
    return True
