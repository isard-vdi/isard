#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import logging
import threading
import traceback
from time import time
from uuid import uuid4

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from rethinkdb import r

log = logging.getLogger(__name__)

# Apiv3 parity: ``main:api/src/api/libv2/api_logging.py:437``. The
# directviewer/proxy reconnect loop fires this path on every WebSocket
# resume — without dedup the ``logs_desktops.events`` array balloons
# with hundreds of duplicate rows per session. 60s TTL matches apiv3.
_directviewer_event_cache: SynchronizedTTLCache = SynchronizedTTLCache(
    maxsize=1000, ttl=60
)


class Logging(RethinkSharedConnection):

    @classmethod
    def action_owner(cls, action_owner, item_owner, direct_viewer=False):
        if action_owner == "isard-scheduler":
            return "isard-scheduler"
        if direct_viewer:
            return "desktop-directviewer"
        if not action_owner:
            return "isard-engine"
        if str(action_owner) == str(item_owner):
            return "desktop-owner"
        return "system-admins"

    @classmethod
    def action_owner_deploy(
        cls, action_owner, item_owner, tag=None, direct_viewer=False
    ):
        if action_owner == "isard-scheduler":
            return "isard-scheduler", None
        if direct_viewer:
            return "desktop-directviewer", None
        if not action_owner:
            return "isard-engine", None
        if action_owner == item_owner:
            return "desktop-owner", action_owner
        if tag:
            deploy = Caches.get_document(
                "deployments", tag, ["user", "name", "co_owners"]
            )
            if deploy is None:
                log.warning("Unable to fetch deployment owner for logs")
                log.debug(traceback.format_exc())
                return None, None
            if deploy["user"] == action_owner:
                return "deployment-owner", deploy["name"]
            elif action_owner in deploy["co_owners"]:
                return "deployment-co-owner", deploy["name"]
        return "system-admins", action_owner

    @classmethod
    def parse_user_request(cls, user_request=None):
        if user_request:
            # Check if it's a Starlette request
            if hasattr(user_request, "headers") and hasattr(user_request, "client"):
                # Starlette/FastAPI request
                return {
                    "request_ip": user_request.headers.get("x-forwarded-for")
                    or (user_request.client.host if user_request.client else None),
                    "request_agent_browser": cls._parse_user_agent(
                        user_request.headers.get("user-agent", "")
                    ).get("browser"),
                    "request_agent_platform": cls._parse_user_agent(
                        user_request.headers.get("user-agent", "")
                    ).get("platform"),
                    "request_agent_version": cls._parse_user_agent(
                        user_request.headers.get("user-agent", "")
                    ).get("version"),
                }
            # Flask request
            elif hasattr(user_request, "headers") and hasattr(
                user_request, "user_agent"
            ):
                return {
                    "request_ip": user_request.headers.environ.get(
                        "HTTP_X_FORWARDED_FOR"
                    ),
                    "request_agent_browser": user_request.user_agent.browser,
                    "request_agent_platform": user_request.user_agent.platform,
                    "request_agent_version": user_request.user_agent.version,
                }

        return {
            "request_ip": None,
            "request_agent_browser": None,
            "request_agent_platform": None,
            "request_agent_version": None,
        }

    @classmethod
    def _parse_user_agent(cls, user_agent_string):
        """Parse user agent string for Starlette requests"""
        # Use user-agents library only if available. This way it's not a hard dependency.
        try:
            from user_agents import parse

            user_agent = parse(user_agent_string)
            return {
                "browser": user_agent.browser.family,
                "platform": user_agent.os.family,
                "version": user_agent.browser.version_string,
            }
        except ImportError:
            # Fallback if user-agents library is not available
            return {"browser": None, "platform": None, "version": None}

    # START DESKTOP
    @classmethod
    def logs_domain_start_api(cls, dom_id, action_user=None, user_request=None):
        cls._logs_domain_start(
            dom_id,
            user_request=cls.parse_user_request(user_request),
            action_user=action_user,
        )

    @classmethod
    def logs_domain_start_directviewer(cls, dom_id, user_request=None):
        cls._logs_domain_start(
            dom_id,
            user_request=cls.parse_user_request(user_request),
            direct_viewer=True,
        )

    @classmethod
    def _logs_domain_start(
        cls,
        dom_id,
        user_request,
        action_user=None,
        direct_viewer=False,
        server_hyp_started=False,
    ):
        # Who can start a desktop:
        # - User: desktop-owner|deployment-owner|deployment-co-owner|system-admins
        # - Desktop direct viewer access: desktop-directviewer
        start_logs_id = str(uuid4())
        try:
            with cls._rdb_context():
                domain = (
                    r.table("domains")
                    .get(dom_id)
                    .update(
                        {"start_logs_id": start_logs_id},
                        return_changes="always",
                        durability="soft",
                    )
                    .run(cls._rdb_connection)["changes"][0]["old_val"]
                )
        except Exception:
            log.warning("Unable to update domain with start log id")
            log.debug(traceback.format_exc())
            return
        if domain.get("tag"):
            action_by, deployment_name = cls.action_owner_deploy(
                action_user, domain["user"], domain.get("tag"), direct_viewer
            )
            if not action_by or not deployment_name:
                return
        else:
            action_by = cls.action_owner(action_user, domain["user"], direct_viewer)
        try:
            user = Caches.get_cached_user_with_names(domain["user"])
        except Exception:
            log.warning("Unable to fetch user data for start logs id")
            log.debug(traceback.format_exc())
            return
        try:
            data = {
                "id": start_logs_id,
                "starting_time": r.epoch_time(time()),
                "starting_by": action_by,
                "starting_user": action_user,
                "desktop_id": dom_id,
                "desktop_name": domain.get("name"),
                "desktop_template_hierarchy": domain.get("parents"),
                "owner_user_id": domain.get("user"),
                "owner_user_name": domain.get("username"),
                "owner_category_id": domain.get("category"),
                "owner_category_name": user["category_name"],
                "owner_group_id": domain.get("group"),
                "owner_group_name": user["group_name"],
                "owner_role_id": user["role"],
                "hardware_vcpus": domain.get("create_dict", {})
                .get("hardware", {})
                .get("vcpus"),
                "hardware_memory": domain.get("create_dict", {})
                .get("hardware", {})
                .get("memory"),
                "events": [],
            }
            if domain.get("tag"):
                data["deployment_id"] = domain.get("tag")
                data["deployment_name"] = deployment_name
            if server_hyp_started:
                data["started_time"] = r.epoch_time(time())
                data["hyp_started"] = server_hyp_started
            data = {**data, **user_request}
        except Exception:
            log.warning("Unable to fetch log data for start logs id")
            log.debug(traceback.format_exc())
            return
        if ((domain.get("create_dict") or {}).get("reservables") or {}).get("vgpus"):
            data["hardware_bookables_vgpus"] = domain["create_dict"]["reservables"][
                "vgpus"
            ]
            if domain.get("booking_id"):
                try:
                    booking = Caches.get_document(
                        "bookings", domain["booking_id"], ["start", "end"]
                    )
                    data["booking_id"] = domain["booking_id"]
                    data["booking_start"] = booking["start"]
                    data["booking_end"] = booking["end"]
                except Exception:
                    log.warning("Unable to fetch booking data for start logs id")
                    log.debug(traceback.format_exc())
        if domain.get("forced_hyp"):
            data["hyp_forced"] = domain["forced_hyp"]
        if domain.get("favourite_hyp"):
            data["hyp_favourite"] = domain["favourite_hyp"]
        with cls._rdb_context():
            r.table("logs_desktops").insert(data, durability="soft").run(
                cls._rdb_connection
            )

    @classmethod
    def logs_domain_start_engine(cls, start_logs_id, dom_id, hyp_started=None):
        asyncio.create_task(
            cls._logs_domain_start_engine(
                start_logs_id,
                dom_id,
                hyp_started=hyp_started,
            )
        )

    @classmethod
    async def _logs_domain_start_engine(cls, start_logs_id, dom_id, hyp_started=None):
        # Whole body is sync RethinkDB writes; spawned via
        # ``asyncio.create_task`` from the public method, so we own
        # the event loop here. Offload the sync work to a thread so
        # log-write latency doesn't pile up on the loop while
        # change-handler events fire in bursts.
        def _sync_body():
            if not start_logs_id:
                # It could be a server desktop started by engine
                cls._logs_domain_start(
                    dom_id, cls.parse_user_request(), server_hyp_started=hyp_started
                )
                return
            # It has a logs_desktops id, try to update it
            # When user started, it will have a valid uuid and update should work
            # When engine started, it could fail because of old id. There is no way to know
            # if it is and old id or a current id. So we try to update it and if it fails
            # we add it as a new log
            result = {}
            try:
                with cls._rdb_context():
                    result = (
                        r.table("logs_desktops")
                        .get(start_logs_id)
                        .update(
                            {
                                "started_time": r.epoch_time(time()),
                                "hyp_started": hyp_started,
                            },
                            durability="soft",
                        )
                        .run(cls._rdb_connection)
                    )
            except Exception:
                log.warning("Unable to update start time in logs")
                log.debug(traceback.format_exc())
            if result.get("skipped"):
                cls._logs_domain_start(
                    dom_id, cls.parse_user_request(), server_hyp_started=hyp_started
                )

        await asyncio.to_thread(_sync_body)

    # STOP DESKTOP
    @classmethod
    def logs_domain_stop_api(cls, dom_id, action_user=None, user_request=None):
        # Apiv3 parity: ``main:api/src/api/libv2/api_logging.py:287-339``
        # accepted ``user_request`` and recorded ``stopping_ip`` /
        # ``stopping_agent_browser`` / ``stopping_agent_platform``. The
        # apiv4 port silently dropped the parameter so every
        # ``logs_desktops`` row written after the cutover lost the
        # session-forensics fields. Restore the contract.
        cls._logs_domain_stop_api(
            dom_id,
            action_user=action_user,
            user_request=cls.parse_user_request(user_request),
        )

    @classmethod
    def _logs_domain_stop_api(cls, desktop_id, action_user, user_request=None):
        domain = Caches.get_document(
            "domains", desktop_id, ["start_logs_id", "tag", "user"]
        )
        if domain is None:
            log.warning("Unable to get desktop start_logs_id")
            log.debug(traceback.format_exc())
            return
        if not domain.get("start_logs_id"):
            log.warning("User stop domain without start_logs_id")
            return
        if domain.get("tag"):
            action_by, deployment_name = cls.action_owner_deploy(
                action_user, domain["user"], domain.get("tag")
            )
            if not action_by or not deployment_name:
                return
        else:
            action_by = cls.action_owner(action_user, domain["user"])
        update = {
            "stopping_time": r.epoch_time(time()),
            "stopping_by": action_by,
            "stopping_user": action_user,
        }
        if user_request:
            update["stopping_ip"] = user_request.get("request_ip")
            update["stopping_agent_browser"] = user_request.get("request_agent_browser")
            update["stopping_agent_platform"] = user_request.get(
                "request_agent_platform"
            )
        try:
            with cls._rdb_context():
                r.table("logs_desktops").get(domain.get("start_logs_id")).update(
                    update,
                    durability="soft",
                ).run(cls._rdb_connection)
        except Exception:
            log.warning("Unable to update event stop in logs")
            log.debug(traceback.format_exc())

    @classmethod
    def logs_domain_stop_engine(cls, start_logs_id, new_status=""):
        asyncio.create_task(
            cls._logs_domain_stop_engine(start_logs_id, new_status=new_status)
        )

    @classmethod
    async def _logs_domain_stop_engine(cls, start_logs_id, new_status=""):
        # Two sequential sync RethinkDB writes — offload as a unit so
        # the event loop stays free during burst stop events.
        def _sync_body():
            if not start_logs_id:
                log.warning("Engine stop domain without start_logs_id")
                return
            try:
                with cls._rdb_context():
                    desktop = (
                        r.table("logs_desktops")
                        .get(start_logs_id)
                        .update(
                            r.branch(
                                r.row.has_fields("stopping_time"),
                                {
                                    "stopped_time": r.epoch_time(time()),
                                    "stopped_status": new_status,
                                },
                                {
                                    "stopped_time": r.epoch_time(time()),
                                    "stopped_by": "isard-engine",
                                    "stopped_status": new_status,
                                },
                            ),
                            return_changes="always",
                            durability="soft",
                        )
                        .run(cls._rdb_connection)
                    )
                if not desktop:
                    log.warning(
                        "Unable to update stopped time at desktop: "
                        + str(desktop_id)
                        + " as it does not exist anymore"
                    )
                    return
                desktop_id = desktop["changes"][0]["new_val"]["desktop_id"]
            except Exception:
                log.warning("Unable to update stopped time for desktop")
                log.debug(traceback.format_exc())
                return
            try:
                with cls._rdb_context():
                    r.table("domains").get(desktop_id).update(
                        {"start_logs_id": None}, durability="soft"
                    ).run(cls._rdb_connection)
            except Exception:
                log.warning("Unable to remove start_logs_id from domain")
                log.debug(traceback.format_exc())

        await asyncio.to_thread(_sync_body)

    # UPDATE EVENTS (unused now)

    @classmethod
    def logs_domain_event_viewer(
        cls, domain_id, action_user, viewer_type, user_request=None
    ):
        # Called from asyncio.to_thread workers with no event loop bound; fall back to a daemon thread to keep fire-and-forget. See logs_domain_event_directviewer.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            threading.Thread(
                target=lambda: asyncio.run(
                    cls._logs_domain_event_viewer(
                        domain_id,
                        action_user,
                        viewer_type,
                        user_request=user_request,
                    )
                ),
                daemon=True,
            ).start()
            return
        asyncio.create_task(
            cls._logs_domain_event_viewer(
                domain_id,
                action_user,
                viewer_type,
                user_request=user_request,
            )
        )

    @classmethod
    async def _logs_domain_event_viewer(
        cls, domain_id, action_user, viewer_type, user_request=None
    ):
        start_logs_id = Caches.get_document("domains", domain_id, ["start_logs_id"])
        if start_logs_id is None:
            log.warning(
                "Unable to update viewer event logs for domain: " + str(domain_id)
            )
            log.debug(traceback.format_exc())
            return
        await cls._logs_domain_event(
            start_logs_id,
            "viewer",
            action_user,
            viewer_type=viewer_type,
            user_request=cls.parse_user_request(user_request),
        )

    @classmethod
    def logs_domain_event_directviewer(
        cls, domain_id, action_user, viewer_type=None, user_request=None
    ):
        # Route handlers offload the direct-viewer service calls via
        # asyncio.to_thread, so this sync wrapper is reached from a
        # worker thread with no event loop bound — asyncio.create_task
        # would raise RuntimeError and the route would swallow it as a
        # generic 404. Detect that case and run the coroutine on a
        # short-lived daemon thread to preserve fire-and-forget.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            threading.Thread(
                target=lambda: asyncio.run(
                    cls._logs_domain_event_directviewer(
                        domain_id,
                        action_user,
                        viewer_type,
                        user_request=user_request,
                    )
                ),
                daemon=True,
            ).start()
            return
        asyncio.create_task(
            cls._logs_domain_event_directviewer(
                domain_id,
                action_user,
                viewer_type,
                user_request=user_request,
            )
        )

    @classmethod
    async def _logs_domain_event_directviewer(
        cls, domain_id, action_user, viewer_type=None, user_request=None
    ):
        # Dedup window: skip if we already wrote a directviewer event
        # for the same (domain, viewer_type, ip) tuple within the last
        # 60s. Apiv3 parity, see module-level
        # ``_directviewer_event_cache``.
        request_ip = ""
        if user_request is not None:
            parsed = cls.parse_user_request(user_request)
            request_ip = parsed.get("request_ip") or ""
        cache_key = f"{domain_id}:{viewer_type}:{request_ip}"
        if cache_key in _directviewer_event_cache:
            return
        _directviewer_event_cache[cache_key] = True

        start_logs_id = Caches.get_document("domains", domain_id, ["start_logs_id"])
        if start_logs_id is None:
            log.warning(
                "Unable to update directviewer event logs for domain: " + str(domain_id)
            )
            log.debug(traceback.format_exc())
            return
        await cls._logs_domain_event(
            start_logs_id,
            "directviewer",
            action_user,
            viewer_type=viewer_type,
            user_request=cls.parse_user_request(user_request),
        )

    @classmethod
    async def _logs_domain_event(
        cls,
        start_logs_id,
        event,
        action_user=None,
        viewer_type="",
        user_request=None,
    ):
        # Sync RethinkDB write — offload so per-event logging
        # latency doesn't compound on the asyncio loop. Bursts of
        # viewer-open events from rapid client reconnects routinely
        # land here in chunks.
        def _sync_body():
            try:
                with cls._rdb_context():
                    r.table("logs_desktops").get(start_logs_id).update(
                        {
                            "events": r.row["events"].append(
                                {
                                    **user_request,
                                    **{
                                        "event": event,
                                        "time": r.epoch_time(time()),
                                        "action_user": action_user,
                                        "viewer_type": viewer_type,
                                    },
                                }
                            )
                        },
                        durability="soft",
                    ).run(cls._rdb_connection)
            except Exception:
                log.warning("Unable to update " + str(event) + " event logs")
                log.debug(traceback.format_exc())

        await asyncio.to_thread(_sync_body)
