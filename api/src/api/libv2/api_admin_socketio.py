#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import os
import time
from datetime import datetime, timedelta
from pprint import pprint

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import json
import traceback

from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError

from .api_exceptions import Error
from .flask_rethink import RDB
from .log import log

db = RDB(app)
db.init_app(app)

import threading

from flask import request
from flask_socketio import (
    SocketIO,
    close_room,
    disconnect,
    emit,
    join_room,
    leave_room,
    rooms,
    send,
)

from .. import socketio

threads = {}

from flask import Flask, _request_ctx_stack, jsonify, request

from ..auth.tokens import get_token_payload
from .helpers import _parse_deployment_desktop, _parse_desktop
from .quotas_process import QuotasProcess

quotas = QuotasProcess()

from .api_admin import ApiAdmin

admins = ApiAdmin()

## Domains Threading
class DomainsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("domains")
                        .without(
                            "xml",
                            "xml_to_start",
                            "hardware",
                            "hardware_from_xml",
                            "history_domain",
                        )
                        .changes(include_initial=False)
                        .run(db.conn)
                    ):
                        # ~ .pluck('id','kind','hyp_started','name','description','icon','status','user')
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            data = c["old_val"]
                            event = (
                                "desktop_delete"
                                if data["kind"] == "desktop"
                                else "template_delete"
                            )
                        else:
                            data = c["new_val"]
                            if data["kind"] == "desktop":
                                event = "desktop_data"
                                # if data['status'] == 'Started' and 'viewer' in data.keys() and 'guest_ip' in data['viewer'].keys():
                                #    if 'viewer' not in c['old_val'] or 'guest_ip' not in c['old_val']:
                                #        event='desktop_guestip'
                            else:
                                event = "template_data"
                                try:
                                    data = admins.GetTemplate(c["new_val"]["id"])
                                    # New threaded events in ds.py toggles status before it can be processed here.
                                except:
                                    continue

                        original_event = event

                        socketio.emit(
                            "user_quota",
                            json.dumps(quotas.get(data["user"])),
                            namespace="/administrators",
                            room=data["user"],
                        )
                        socketio.emit(
                            original_event,
                            json.dumps(data),
                            namespace="/administrators",
                            room=data["user"],
                        )
                        ## Manager update
                        socketio.emit(
                            original_event,
                            json.dumps(data),
                            namespace="/administrators",
                            room=data["category"],
                        )
                        # All admins
                        socketio.emit(
                            original_event,
                            json.dumps(data),
                            namespace="/administrators",
                            room="admins",
                        )

            except ReqlDriverError:
                print("DomainsThread: Rethink db connection lost!")
                log.error("DomainsThread: Rethink db connection lost!")
                time.sleep(0.5)
            except Exception as e:
                print("DomainsThread internal error: \n" + traceback.format_exc())
                log.error("DomainsThread internal error: \n" + traceback.format_exc())

        print("DomainsThread ENDED!!!!!!!")
        log.error("DomainsThread ENDED!!!!!!!")


def start_domains_thread():
    global threads
    if "domains" not in threads:
        threads["domains"] = None
    if threads["domains"] == None:
        threads["domains"] = DomainsThread()
        threads["domains"].daemon = True
        threads["domains"].start()
        log.info("DomainsThread Started")


## MEDIA Threading
class MediaThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("domains")
                        .get_all(
                            r.args(
                                [
                                    "Downloaded",
                                    "DownloadFailed",
                                    "DownloadStarting",
                                    "Downloading",
                                    "DownloadAborting",
                                    "ResetDownloading",
                                ]
                            ),
                            index="status",
                        )
                        .pluck(
                            "id",
                            "name",
                            "description",
                            "icon",
                            "progress",
                            "status",
                            "user",
                            "category",
                        )
                        .merge({"table": "domains"})
                        .changes(include_initial=False)
                        .union(
                            r.table("media")
                            .get_all(
                                r.args(
                                    [
                                        "Deleting",
                                        "Deleted",
                                        "Downloaded",
                                        "DownloadFailed",
                                        "DownloadStarting",
                                        "Downloading",
                                        "Download",
                                        "DownloadAborting",
                                        "ResetDownloading",
                                    ]
                                ),
                                index="status",
                            )
                            .merge({"table": "media"})
                            .changes(include_initial=False)
                        )
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            data = c["old_val"]
                            event = c["old_val"]["table"] + "_delete"
                        else:
                            data = c["new_val"]
                            event = c["new_val"]["table"] + "_data"

                        socketio.emit(
                            "user_quota",
                            json.dumps(quotas.get(data["user"])),
                            namespace="/administrators",
                            room=data["user"],
                        )
                        socketio.emit(
                            event,
                            json.dumps(data),
                            namespace="/administrators",
                            room=data["user"],
                        )
                        socketio.emit(
                            event,
                            json.dumps(data),
                            namespace="/administrators",
                            room=data["category"],
                        )
                        socketio.emit(
                            event,
                            json.dumps(data),
                            namespace="/administrators",
                            room="admins",
                        )
            except ReqlDriverError:
                print("MediaThread: Rethink db connection lost!")
                log.error("MediaThread: Rethink db connection lost!")
                time.sleep(5)
            except Exception as e:
                print("MediaThread internal error: \n" + traceback.format_exc())
                log.error("MediaThread internal error: \n" + traceback.format_exc())

        print("MediaThread ENDED!!!!!!!")
        log.error("MediaThread ENDED!!!!!!!")


def start_media_thread():
    global threads
    if "media" not in threads:
        threads["media"] = None
    if threads["media"] == None:
        threads["media"] = MediaThread()
        threads["media"].daemon = True
        threads["media"].start()
        log.info("MediaThread Started")


## RESOURCES Threading
class ResourcesThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("graphics")
                        .merge({"table": "graphics"})
                        .changes(include_initial=False)
                        .union(
                            r.table("videos")
                            .merge({"table": "videos"})
                            .changes(include_initial=False)
                            .union(
                                r.table("interfaces")
                                .merge({"table": "interfaces"})
                                .changes(include_initial=False)
                                .union(
                                    r.table("qos_net")
                                    .merge({"table": "qos_net"})
                                    .changes(include_initial=False)
                                    .union(
                                        r.table("qos_disk")
                                        .merge({"table": "qos_disk"})
                                        .changes(include_initial=False)
                                        .union(
                                            r.table("remotevpn")
                                            .merge({"table": "remotevpn"})
                                            .changes(include_initial=False)
                                            .union(
                                                r.table("boots")
                                                .merge({"table": "boots"})
                                                .changes(include_initial=False)
                                            )
                                        )
                                    )
                                )
                            )
                        )
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            data = {
                                "table": c["old_val"]["table"],
                                "data": c["old_val"],
                            }
                            event = "delete"
                        else:
                            data = {
                                "table": c["new_val"]["table"],
                                "data": c["new_val"],
                            }
                            event = "data"
                        ## Admins should receive all updates on /isard-admin/admin namespace
                        socketio.emit(
                            event,
                            json.dumps(data),  # app.isardapi.f.flatten_dict(data)),
                            namespace="/administrators",
                            room="admins",
                        )
            except ReqlDriverError:
                print("ResourcesThread: Rethink db connection lost!")
                log.error("ResourcesThread: Rethink db connection lost!")
                time.sleep(6)
            except Exception as e:
                print("ResourcesThread internal error: \n" + traceback.format_exc())
                log.error("ResourcesThread internal error: \n" + traceback.format_exc())


def start_resources_thread():
    global threads
    if "resources" not in threads:
        threads["resources"] = None
    if threads["resources"] == None:
        threads["resources"] = ResourcesThread()
        threads["resources"].daemon = True
        threads["resources"].start()
        log.info("ResourcesThread Started")


## Users Threading
class UsersThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("users")
                        .merge({"table": "users"})
                        .without("password", {"vpn": {"wireguard": "keys"}})
                        .changes(include_initial=False)
                        .union(
                            r.table("categories")
                            .merge({"table": "categories"})
                            .changes(include_initial=False)
                            .union(
                                r.table("groups")
                                .merge({"table": "groups"})
                                .changes(include_initial=False)
                            )
                        )
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            data = c["old_val"]
                            table = c["old_val"]["table"]
                            event = table + "_delete"
                        else:
                            data = c["new_val"]
                            table = c["new_val"]["table"]
                            event = table + "_data"

                        # Admins receive all events
                        socketio.emit(
                            event,
                            json.dumps(data),
                            namespace="/administrators",
                            room="admins",
                        )

                        # Managers only get it's own category events
                        ## Get the table category
                        if table == "users":
                            category = data["category"]
                        elif table == "categories":
                            category = data["id"]
                        else:
                            category = (
                                data["parent_category"]
                                if "parent_category" in data.keys()
                                else False
                            )

                        if category:
                            socketio.emit(
                                event,
                                json.dumps(data),
                                namespace="/administrators",
                                room=category,
                            )

                        socketio.emit(
                            "user_quota",
                            json.dumps(quotas.get(False, admin=True)),
                            namespace="/administrators",
                            room=category,
                        )

                        ## Admins should receive all updates on /isard-admin/admin namespace
                        socketio.emit(
                            "user_quota",
                            json.dumps(quotas.get(False, admin=True)),
                            namespace="/administrators",
                            room="admins",
                        )

            except ReqlDriverError:
                print("UsersThread: Rethink db connection lost!")
                log.error("UsersThread: Rethink db connection lost!")
                time.sleep(2)
            except Exception as e:
                print("UsersThread internal error: \n" + traceback.format_exc())
                log.error("UsersThread internal error: \n" + traceback.format_exc())


def start_users_thread():
    global threads
    if "users" not in threads:
        threads["users"] = None
    if threads["users"] == None:
        threads["users"] = UsersThread()
        threads["users"].daemon = True
        threads["users"].start()
        log.info("UsersThread Started")


## Hypervisors Threading
class HypervisorsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("hypervisors")
                        .changes(include_initial=False)
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            socketio.emit(
                                "hyper_deleted",
                                json.dumps(c["old_val"]["id"]),
                                namespace="/administrators",
                                room="admins",
                            )
                        else:
                            socketio.emit(
                                "hyper_data",
                                json.dumps(c["new_val"]),
                                namespace="/administrators",
                                room="admins",
                            )
            except ReqlDriverError:
                print("HypervisorsThread: Rethink db connection lost!")
                log.error("HypervisorsThread: Rethink db connection lost!")
                time.sleep(2)
            except Exception as e:
                print("HypervisorsThread internal error: \n" + traceback.format_exc())
                log.error(
                    "HypervisorsThread internal error: \n" + traceback.format_exc()
                )


def start_hypervisors_thread():
    global threads
    if "hypervisors" not in threads:
        threads["hypervisors"] = None
    if threads["hypervisors"] == None:
        threads["hypervisors"] = HypervisorsThread()
        threads["hypervisors"].daemon = True
        threads["hypervisors"].start()
        log.info("HypervisorsThread Started")


## Config Threading
class ConfigThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("backups")
                        .merge({"table": "backups"})
                        .changes(include_initial=False)
                        .union(
                            r.table("scheduler_jobs")
                            .has_fields("name")
                            .without("job_state")
                            .merge({"table": "scheduler_jobs"})
                            .changes(include_initial=False)
                        )
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            event = "_deleted"
                            socketio.emit(
                                c["old_val"]["table"] + event,
                                json.dumps(c["old_val"]),
                                namespace="/administrators",
                                room="admins",
                            )
                        else:
                            event = "_data"
                            if (
                                c["new_val"]["table"] == "scheduler_jobs"
                                and c["new_val"].get("kind") == "date"
                            ):
                                continue
                            socketio.emit(
                                c["new_val"]["table"] + event,
                                json.dumps(c["new_val"]),
                                namespace="/administrators",
                                room="admins",
                            )

                            # ~ event= 'backup_deleted' if c['old_val']['table']=='backups' else 'sch_deleted'
                            # ~ socketio.emit(event,
                            # ~ json.dumps(c['old_val']),
                            # ~ namespace='/administrators',
                            # ~ room='config')
                        # ~ else:
                        # ~ event='backup_data' if c['new_val']['table']=='backups' else 'sch_data'
                        # ~ if event=='sch_data' and 'name' not in c['new_val'].keys():
                        # ~ continue
                        # ~ socketio.emit(event,
                        # ~ json.dumps(c['new_val']),
                        # ~ namespace='/administrators',
                        # ~ room='config')
            except ReqlDriverError:
                print("ConfigThread: Rethink db connection lost!")
                log.error("ConfigThread: Rethink db connection lost!")
                time.sleep(15)
            except Exception as e:
                print("ConfigThread internal error: \n" + traceback.format_exc())
                log.error("ConfigThread internal error: \n" + traceback.format_exc())


def start_config_thread():
    global threads
    if "config" not in threads:
        threads["config"] = None
    if threads["config"] == None:
        threads["config"] = ConfigThread()
        threads["config"].daemon = True
        threads["config"].start()
        log.info("ConfigThread Started")


## Admin namespace CONNECT
@socketio.on("connect", namespace="/administrators")
def socketio_admins_connect():
    try:
        log.debug(request.args)
        payload = get_token_payload(request.args.get("jwt"))
    except Exception as e:
        log.error(traceback.format_exc())
    try:
        join_room(payload["user_id"])
        if payload["role_id"] == "admin":
            join_room("admins")
            log.debug("USER: " + payload["user_id"] + " JOINED ADMIN ROOM")
        if payload["role_id"] == "manager":
            join_room(payload["category_id"])
            log.debug(
                "USER: "
                + payload["user_id"]
                + " JOINED MANAGER "
                + payload["category_id"]
                + "ROOM"
            )
        socketio.emit(
            "user_quota",
            json.dumps(quotas.get(payload["user_id"])),
            namespace="/administrators",
            room=payload["user_id"],
        )
    except Exception as e:
        log.error(traceback.format_exc())


@socketio.on("disconnect", namespace="/administrators")
def socketio_admins_disconnect():
    leave_room("admins")
    try:
        log.debug("Here we should leave rooms...")
        # leave_room("user_" + current_user.id)
    except Exception as e:
        log.debug(e)
        log.debug("USER leaved without disconnect")
