#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import json
import os
import traceback
from pprint import pformat

import simple_colors as sc
from rethinkdb.errors import ReqlDriverError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import threading

from flask import request
from flask_socketio import join_room, leave_room
from jose.jwt import ExpiredSignatureError

from .. import socketio

threads = {}

from flask import request
from isardvdi_common.tokens import get_expired_user_data, get_token_payload

from .api_admin import ApiAdmin
from .api_logging import logs_domain_start_engine, logs_domain_stop_engine
from .api_scheduler import Scheduler

admins = ApiAdmin()
api_scheduler = Scheduler()


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
                        .pluck(
                            "id",
                            {
                                "create_dict": {
                                    "reservables": True,
                                    "hardware": {"vcpus": True, "memory": True},
                                }
                            },
                            "kind",
                            "server",
                            "hyp_started",
                            "name",
                            "status",
                            "username",
                            "accessed",
                            "forced_hyp",
                            "favourite_hyp",
                            "booking_id",
                            "tag",
                            "start_logs_id",
                            "user",
                            "category",
                            {"viewer": {"guest_ip": True}},
                            "image",
                            "description",
                            "progress",
                        )
                        .changes(include_initial=False, squash=0.5)
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            data = c["old_val"]
                            event = (
                                "desktop_delete"
                                if data["kind"] == "desktop"
                                else "template_delete"
                            )
                            if event == "desktop_delete" and data.get("tag"):
                                if (
                                    not r.table("domains")
                                    .get_all(data["tag"], index="tag")
                                    .count()
                                    .run(db.conn)
                                ):
                                    deployment = (
                                        r.table("deployments")
                                        .get(data["tag"])
                                        .run(db.conn)
                                    )
                                    if (
                                        deployment
                                        and deployment.get("status", "") == "deleting"
                                    ):
                                        r.table("deployments").get(
                                            data["tag"]
                                        ).delete().run(db.conn)
                            user = data.pop("user")
                            category = data.pop("category")
                            data = {"id": data["id"], "name": data["name"]}
                        else:
                            data = c["new_val"]
                            if (
                                c["old_val"]
                                and c["old_val"].get("progress")
                                and c["new_val"].get("progress")
                            ):
                                if c["old_val"]["progress"] == c["new_val"]["progress"]:
                                    data.pop("progress")
                            if c["old_val"] == None:
                                user = (
                                    r.table("users")
                                    .get(data["user"])
                                    .pluck("role", "group", "category")
                                    .merge(
                                        lambda usr: {
                                            "group_name": r.table("groups").get(
                                                usr["group"]
                                            )["name"]
                                        }
                                    )
                                    .merge(
                                        lambda usr: {
                                            "category_name": r.table("categories").get(
                                                usr["category"]
                                            )["name"]
                                        }
                                    )
                                    .run(db.conn)
                                )
                                data.update(user)
                            if data["kind"] == "desktop":
                                event = "desktop_data"
                                start_logs_id = data.pop("start_logs_id", None)
                                if start_logs_id:
                                    if c["new_val"].get("status") == "Started" and c[
                                        "old_val"
                                    ].get("status") != c["new_val"].get("status"):
                                        logs_domain_start_engine(
                                            start_logs_id,
                                            data.get("id"),
                                            data.get("hyp_started"),
                                        )
                                    if c["new_val"].get("status") in [
                                        "Stopped",
                                        "Failed",
                                    ] and c["old_val"].get("status") != c[
                                        "new_val"
                                    ].get(
                                        "status"
                                    ):
                                        logs_domain_stop_engine(
                                            start_logs_id,
                                            c["new_val"].get("status"),
                                        )
                                        api_scheduler.remove_desktop_timeouts(
                                            data.get("id")
                                        )
                                else:
                                    if c["new_val"].get("status") == "Started" and c[
                                        "old_val"
                                    ].get("status") != c["new_val"].get("status"):
                                        logs_domain_start_engine(
                                            start_logs_id,
                                            data.get("id"),
                                            data.get("hyp_started"),
                                        )
                                # if data['status'] == 'Started' and 'viewer' in data.keys() and 'guest_ip' in data['viewer'].keys():
                                #    if 'viewer' not in c['old_val'] or 'guest_ip' not in c['old_val']:
                                #        event='desktop_guestip'
                            else:
                                event = "template_data"
                            user = data.pop("user")
                            category = data["category"]
                        socketio.emit(
                            event,
                            json.dumps(data),
                            namespace="/administrators",
                            room=user,
                        )
                        ## Manager update
                        socketio.emit(
                            event,
                            json.dumps(data),
                            namespace="/administrators",
                            room=category,
                        )
                        # All admins
                        socketio.emit(
                            event,
                            json.dumps(data),
                            namespace="/administrators",
                            room="admins",
                        )

            except ReqlDriverError:
                print("DomainsThread: Rethink db connection lost!")
                app.logger.error("DomainsThread: Rethink db connection lost!")
                time.sleep(0.5)
            except Exception as e:
                print("DomainsThread internal error: \n" + traceback.format_exc())
                app.logger.error(
                    "DomainsThread internal error: \n" + traceback.format_exc()
                )

        print("DomainsThread ENDED!!!!!!!")
        app.logger.error("DomainsThread ENDED!!!!!!!")


def start_domains_thread():
    global threads
    if "domains" not in threads:
        threads["domains"] = None
    if threads["domains"] == None:
        threads["domains"] = DomainsThread()
        threads["domains"].daemon = True
        threads["domains"].start()
        app.logger.info("DomainsThread Started")


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
                        .changes(include_initial=False, squash=0.5)
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
                            .changes(include_initial=False, squash=0.5)
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
                app.logger.error("MediaThread: Rethink db connection lost!")
                time.sleep(5)
            except Exception as e:
                print("MediaThread internal error: \n" + traceback.format_exc())
                app.logger.error(
                    "MediaThread internal error: \n" + traceback.format_exc()
                )

        print("MediaThread ENDED!!!!!!!")
        app.logger.error("MediaThread ENDED!!!!!!!")


def start_media_thread():
    global threads
    if "media" not in threads:
        threads["media"] = None
    if threads["media"] == None:
        threads["media"] = MediaThread()
        threads["media"].daemon = True
        threads["media"].start()
        app.logger.info("MediaThread Started")


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
                app.logger.error("ResourcesThread: Rethink db connection lost!")
                time.sleep(6)
            except Exception as e:
                print("ResourcesThread internal error: \n" + traceback.format_exc())
                app.logger.error(
                    "ResourcesThread internal error: \n" + traceback.format_exc()
                )


def start_resources_thread():
    global threads
    if "resources" not in threads:
        threads["resources"] = None
    if threads["resources"] == None:
        threads["resources"] = ResourcesThread()
        threads["resources"].daemon = True
        threads["resources"].start()
        app.logger.info("ResourcesThread Started")


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
                        .without(
                            "password",
                            {"vpn": {"wireguard": "keys"}},
                            "photo",
                            "email",
                        )
                        .changes(include_initial=False, squash=0.5)
                        .union(
                            r.table("categories")
                            .merge({"table": "categories"})
                            .changes(include_initial=False, squash=0.5)
                            .union(
                                r.table("groups")
                                .merge({"table": "groups"})
                                .changes(include_initial=False, squash=0.5)
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

                            if table == "users":
                                data["role_name"] = (
                                    r.table("roles")
                                    .get(data["role"])
                                    .run(db.conn)["name"]
                                )
                                data["secondary_groups_data"] = (
                                    r.table("groups")
                                    .get_all(r.args(data["secondary_groups"]))
                                    .pluck("id", "name")
                                    .coerce_to("array")
                                    .run(db.conn)
                                )
                                # Add new user
                                if c["old_val"]:
                                    data["category_name"] = (
                                        r.table("categories")
                                        .get(data["category"])
                                        .run(db.conn)["name"]
                                    )
                                    data["group_name"] = (
                                        r.table("groups")
                                        .get(data["group"])
                                        .run(db.conn)["name"]
                                    )
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

            except ReqlDriverError:
                print("UsersThread: Rethink db connection lost!")
                app.logger.error("UsersThread: Rethink db connection lost!")
                time.sleep(2)
            except Exception as e:
                print("UsersThread internal error: \n" + traceback.format_exc())
                app.logger.error(
                    "UsersThread internal error: \n" + traceback.format_exc()
                )


def start_users_thread():
    global threads
    if "users" not in threads:
        threads["users"] = None
    if threads["users"] == None:
        threads["users"] = UsersThread()
        threads["users"].daemon = True
        threads["users"].start()
        app.logger.info("UsersThread Started")


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
                        .pluck(
                            [
                                "enabled",
                                "id",
                                "only_forced",
                                "stats",
                                "status",
                                "status_time",
                                {
                                    "stats": {
                                        "mem_stats": {"total": True, "available": True},
                                        "cpu_1min": {"used": True},
                                    }
                                },
                                {"vpn": {"wireguard": {"connected": True}}},
                                "min_free_mem_gb",
                                "orchestrator_managed",
                                "destroy_time",
                            ]
                        )
                        .changes(include_initial=False)
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            socketio.emit(
                                "hyper_deleted",
                                json.dumps(c["old_val"]),
                                namespace="/administrators",
                                room="admins",
                            )
                        else:
                            if c["old_val"] == None or c["old_val"].get("status") != c[
                                "new_val"
                            ].get("status"):
                                data = (
                                    r.table("hypervisors")
                                    .get(c["new_val"]["id"])
                                    .merge(
                                        lambda hyper: {
                                            "gpus": r.table("vgpus")
                                            .filter({"hyp_id": hyper["id"]})
                                            .count(),
                                            "desktops_started": r.table("domains")
                                            .get_all(hyper["id"], index="hyp_started")
                                            .count(),
                                        }
                                    )
                                    .run(db.conn)
                                )
                                socketio.emit(
                                    "hyper_data",
                                    json.dumps(data),
                                    namespace="/administrators",
                                    room="admins",
                                )
                                continue
                            if c["new_val"]["status"] != "Online":
                                data = c["new_val"]
                                data["desktops_started"] = 0
                            else:
                                data = {
                                    **c["new_val"],
                                    **{
                                        "desktops_started": r.table("domains")
                                        .get_all(
                                            c["new_val"]["id"], index="hyp_started"
                                        )
                                        .count()
                                        .run(db.conn),
                                    },
                                }
                            socketio.emit(
                                "hyper_data",
                                json.dumps(data),
                                namespace="/administrators",
                                room="admins",
                            )
            except ReqlDriverError:
                print("HypervisorsThread: Rethink db connection lost!")
                app.logger.error("HypervisorsThread: Rethink db connection lost!")
                time.sleep(2)
            except Exception as e:
                print("HypervisorsThread internal error: \n" + traceback.format_exc())
                app.logger.error(
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
        app.logger.info("HypervisorsThread Started")


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
                            .merge(
                                {
                                    "table": "scheduler_jobs",
                                    "date": r.row["date"].to_iso8601(),
                                }
                            )
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
                                json.dumps({"id": c["old_val"]["id"]}),
                                namespace="/administrators",
                                room="admins",
                            )
                        else:
                            event = "_data"
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
                app.logger.error("ConfigThread: Rethink db connection lost!")
                time.sleep(15)
            except Exception as e:
                print("ConfigThread internal error: \n" + traceback.format_exc())
                app.logger.error(
                    "ConfigThread internal error: \n" + traceback.format_exc()
                )


def start_config_thread():
    global threads
    if "config" not in threads:
        threads["config"] = None
    if threads["config"] == None:
        threads["config"] = ConfigThread()
        threads["config"].daemon = True
        threads["config"].start()
        app.logger.info("ConfigThread Started")


## Admin namespace CONNECT
@socketio.on("connect", namespace="/administrators")
def socketio_admins_connect(nothing_should_be_here=None):
    if nothing_should_be_here != None:
        app.logger.error(
            "Call to socketio_admins_connect with args, wtf? args="
            + str(nothing_should_be_here)
        )
        return

    try:
        payload = get_token_payload(request.args.get("jwt"))
    except:
        quit_admins_rooms(request.args.get("jwt"))
        return

    try:
        if payload["role_id"] == "admin":
            join_room(payload["user_id"])
            join_room("admins")
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                app.logger.debug(
                    {
                        "websocket": "join_room_admins",
                        **payload,
                    },
                )
                print(sc.green("join_room_admins", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
        elif payload["role_id"] == "manager":
            join_room(payload["user_id"])
            join_room(payload["category_id"])
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                app.logger.debug(
                    {
                        "websocket": "join_room_manager",
                        **payload,
                    },
                )
                print(sc.green("join_room_manager", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
        else:
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                app.logger.error(
                    {
                        "websocket": "join_room_admins_not_allowed",
                        **payload,
                    },
                )
                print(sc.red("join_room_admins_not_allowed", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
    except:
        payload = quit_admins_rooms(request.args.get("jwt"))
        app.logger.error(
            {
                "websocket": "join_room_admins_internal_server",
                **payload,
                **request.args,
                "error": str(traceback.format_exc()),
            },
        )


@socketio.on("disconnect", namespace="/administrators")
def socketio_admins_disconnect(data=None):
    quit_admins_rooms(request.args.get("jwt"))


def quit_admins_rooms(jwt):
    try:
        payload = get_token_payload(jwt)
    except ExpiredSignatureError:
        payload = get_expired_user_data(jwt)
        if not payload:
            return {}
        app.logger.debug(
            {
                "websocket": "leave_room_admins_expired_token",
                **payload,
            },
        )
    except:
        payload = get_expired_user_data(jwt)
        if not payload:
            return {}

    if payload.get("user_id"):
        leave_room(payload["user_id"])
        if payload["role_id"] == "admin":
            leave_room("admins")
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                app.logger.debug(
                    {
                        "websocket": "leave_room_admins",
                        **payload,
                    },
                )
                print(sc.yellow("leave_room_admins", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
        elif payload["role_id"] == "manager":
            leave_room(payload["category_id"])
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                app.logger.debug(
                    {
                        "websocket": "leave_room_manager",
                        **payload,
                    },
                )
                print(sc.yellow("leave_room_manager", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
        else:
            app.logger.error(
                {
                    "websocket": "leave_room_admins_not_allowed",
                    **payload,
                },
            )
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                print(sc.red("leave_room_admins_not_allowed", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
        return payload
    return {}
