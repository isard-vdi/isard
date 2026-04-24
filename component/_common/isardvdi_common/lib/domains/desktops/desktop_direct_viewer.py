#
#   Copyright © 2025 Pau Abril Iranzo
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later


import base64
import json
import logging as log
import os
import secrets
import time
import traceback
import urllib.parse
import uuid
from datetime import datetime, timedelta

import pytz
from cachetools import TTLCache, cached
from isardvdi_common.connections.redis_urls import socketio_url
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.api_notify import notify_admins, send_socket_user
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.isard_viewer import IsardViewer
from isardvdi_common.helpers.logging import Logging
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.helpers.scheduler import Scheduler
from isardvdi_common.lib.bookings.bookings import BookingsProcessed
from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed
from isardvdi_common.schemas.domains import DesktopStatusEnum
from rethinkdb import r
from socketio import RedisManager

socketio = RedisManager(socketio_url(), write_only=True)

isard_viewer = IsardViewer()


class DesktopDirectViewer(RethinkSharedConnection):

    _rdb_table = "domains"

    @classmethod
    def jumperurl_exists(cls, jumperurl):
        """
        Check if a jumperurl already exists in the database.

        Args:
            jumperurl (str): The jumperurl to check

        Returns:
            bool: True if the jumperurl exists, False otherwise
        """
        with cls._rdb_context():
            existing = (
                r.table(cls._rdb_table)
                .filter({"jumperurl": jumperurl})
                .count()
                .run(cls._rdb_connection)
            )
        return existing > 0

    @classmethod
    def gen_jumpertoken(cls, desktop_id=None, length=32):
        """_From api/libv2/api_desktops_common.py ApiDesktopsCommon.gen_jumpertoken() and api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.api_jumperurl_gencode()_"""
        code = False
        while code == False:
            code = secrets.token_urlsafe(length)
            with cls._rdb_context():
                found = list(
                    r.table("domains")
                    .get_all(code, index="jumperurl")
                    .run(cls._rdb_connection)
                )
            if len(found) == 0:
                if desktop_id is None:
                    return code

                with cls._rdb_context():
                    r.table("domains").get(desktop_id).update({"jumperurl": code}).run(
                        cls._rdb_connection
                    )
                return code
        raise Error(
            "internal_server",
            "Unable to generate jumpertoken",
            traceback.format_exc(),
            description_code="generic_error",
        )

    @classmethod
    def get_desktop_from_token(cls, token):
        """_From api/libv2/api_desktops_common.py ApiDesktopsCommon.DesktopFromToken()_"""
        domains = []
        with cls._rdb_context():
            domains = list(
                r.table("domains")
                .get_all(token, index="jumperurl")
                .run(cls._rdb_connection)
            )
        domains = [
            d
            for d in domains
            if not d.get("tag") or d.get("tag") and d.get("tag_visible")
        ]
        if len(domains) == 0:
            raise Error(
                "not_found",
                "Desktop not found or not visible",
                traceback.format_exc(),
                description_code="not_found",
            )
        if len(domains) == 1:
            return domains[0]
        raise Error(
            "internal_server",
            "Jumperviewer token duplicated",
            traceback.format_exc(),
            description_code="generic_error",
        )

    @classmethod
    def get_desktop_jumper_url(cls, desktop_id):
        with cls._rdb_context():
            share_link = (
                r.table("domains")
                .get(desktop_id)
                .pluck("jumperurl")
                .run(cls._rdb_connection)
            )
        return share_link.get("jumperurl") or None

    @classmethod
    def reset_desktop_jumper_url(cls, desktop_id, enabled=True):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.JumperUrlReset()_"""
        if enabled is False:
            try:
                with cls._rdb_context():
                    r.table("domains").get(desktop_id).update({"jumperurl": False}).run(
                        cls._rdb_connection
                    )
            except Exception:
                raise Error(
                    "not_found",
                    "Unable to reset jumperurl as domain not exists",
                    traceback.format_exc(),
                    description_code="unable_to_reset_domain_jumperurl",
                )
        else:
            code = cls.gen_jumpertoken(desktop_id=desktop_id)
            return code

    @classmethod
    def desktop_direct_viewer(cls, desktop_id, viewer_txt, protocol):
        viewer_uri = viewer_txt["viewer"][0].split("/viewer/")[0] + "/vw/"

        with cls._rdb_context():
            domain_row = (
                r.table("domains")
                .get(desktop_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        jumpertoken = (domain_row or {}).get("jumperurl") or False
        if not jumpertoken:
            jumpertoken = cls.gen_jumpertoken(desktop_id)

        return {
            "kind": protocol,
            "viewer": viewer_uri + jumpertoken + "?protocol=" + protocol,
            "cookie": False,
        }

    @classmethod
    def desktop_viewer(
        cls, desktop_id, protocol, get_cookie=False, admin_role=False, desktop=None
    ):
        if protocol in ["url", "file"]:
            direct_protocol = protocol
            protocol = "browser-vnc"
        else:
            direct_protocol = False

        viewer_txt = isard_viewer.viewer_data(
            desktop_id, protocol=protocol, admin_role=admin_role, domain=desktop
        )

        with cls._rdb_context():
            r.table("domains").get(desktop_id).update(
                {"accessed": int(time.time())}
            ).run(cls._rdb_connection)

        if not direct_protocol:
            return viewer_txt
        else:
            return cls.desktop_direct_viewer(desktop_id, viewer_txt, direct_protocol)

    @classmethod
    def desktop_from_token(cls, token):
        domains = []
        with cls._rdb_context():
            domains = list(
                r.table("domains")
                .get_all(token, index="jumperurl")
                .run(cls._rdb_connection)
            )
        domains = [
            d
            for d in domains
            if not d.get("tag") or d.get("tag") and d.get("tag_visible")
        ]
        if len(domains) == 0:
            raise Error(
                "not_found",
                "Desktop not found or not visible",
                traceback.format_exc(),
                description_code="not_found",
            )
        if len(domains) == 1:
            return domains[0]
        raise Error(
            "internal_server",
            "Jumperviewer token duplicated",
            traceback.format_exc(),
            description_code="generic_error",
        )

    @classmethod
    def desktop_viewer_from_token(cls, token, start_desktop=True, request=None):
        domain = cls.desktop_from_token(token)

        booking = DesktopsProcessed._parse_desktop_booking(domain)
        if booking.get("needs_booking"):
            if not booking.get("next_booking_start"):
                raise Error(
                    "precondition_required",
                    "Bookable desktop can't be started without a booking",
                    traceback.format_exc(),
                    "desktop_not_booked",
                )
            elif Helpers.is_future(
                {
                    "start": datetime.strptime(
                        booking.get("next_booking_start"), "%Y-%m-%dT%H:%M%z"
                    ).astimezone(pytz.UTC)
                }
            ):
                raise Error(
                    "precondition_required",
                    "The next desktop booking is at "
                    + booking.get("next_booking_start"),
                    traceback.format_exc(),
                    "desktop_not_booked_until",
                    data=None,
                    params={"start": booking.get("next_booking_start")},
                )

        scheduled = False
        if start_desktop:
            if domain["status"] in [
                DesktopStatusEnum.stopped.value,
                DesktopStatusEnum.failed.value,
            ]:
                Logging.logs_domain_start_directviewer(
                    domain["id"],
                    user_request=request,
                )
                DesktopEvents.desktop_start(domain["id"], wait_seconds=60)
                payload = Helpers.gen_payload_from_user(domain["user"])
                scheduled = Scheduler.add_desktop_timeouts(payload, domain["id"])
            else:
                Logging.logs_domain_event_directviewer(
                    domain["id"],
                    action_user=None,
                    viewer_type="directviewer-access",
                    user_request=request,
                )
        sched_src = scheduled or domain.get("scheduled")
        desktop = {
            "id": domain["id"],
            "jwt": IsardViewer.viewer_jwt(domain["category"], domain["id"], minutes=30),
            "name": domain["name"],
            "description": domain["description"],
            "status": DesktopStatusEnum.started.value,
            "scheduled": (
                sched_src if isinstance(sched_src, dict) else {"shutdown": False}
            ),
            "viewers": {},
        }
        desktop_viewers = list(domain["guest_properties"]["viewers"].keys())
        if "file_spice" in desktop_viewers:
            desktop["viewers"]["file-spice"] = cls.desktop_viewer(
                domain["id"], protocol="file-spice", get_cookie=True
            )
        if "browser_vnc" in desktop_viewers:
            desktop["viewers"]["browser-vnc"] = cls.desktop_viewer(
                domain["id"], protocol="browser-vnc", get_cookie=True
            )
        if "browser_rdp" in desktop_viewers:
            if domain.get("viewer", True) == False:
                desktop["viewers"]["browser-rdp"] = {
                    "kind": "browser",
                    "protocol": "rdp",
                }
                desktop["status"] = DesktopStatusEnum.waiting_ip.value
            elif not domain.get("viewer", {}).get("guest_ip"):
                desktop["viewers"]["browser-rdp"] = {
                    "kind": "browser",
                    "protocol": "rdp",
                }
                desktop["status"] = DesktopStatusEnum.waiting_ip.value
            else:
                desktop["viewers"]["browser-rdp"] = cls.desktop_viewer(
                    domain["id"],
                    protocol="browser-rdp",
                    get_cookie=True,
                )
        if "file_rdpgw" in desktop_viewers:
            if domain.get("viewer", True) == False:
                desktop["viewers"]["file-rdpgw"] = {"kind": "file", "protocol": "rdpgw"}
                desktop["status"] = DesktopStatusEnum.waiting_ip.value
            elif not domain.get("viewer", {}).get("guest_ip"):
                desktop["viewers"]["file-rdpgw"] = {"kind": "file", "protocol": "rdpgw"}
                desktop["status"] = DesktopStatusEnum.waiting_ip.value
            else:
                desktop["viewers"]["file-rdpgw"] = cls.desktop_viewer(
                    domain["id"],
                    protocol="file-rdpgw",
                    get_cookie=True,
                )
        return desktop

    @classmethod
    def reset_desktop(cls, token, request):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.Reset()_"""
        desktop_id = cls.get_desktop_from_token(token)["id"]
        Logging.logs_domain_event_directviewer(
            desktop_id, action_user=None, viewer_type="reset", user_request=request
        )
        DesktopEvents.desktop_reset(desktop_id)

        return desktop_id

    @classmethod
    def desktop_viewer_docs(cls):
        docs_link = os.getenv(
            "FRONTEND_VIEWERS_DOCS_URI",
            "https://isard.gitlab.io/isardvdi-docs/user/viewers/viewers/",
        )
        if not docs_link:
            raise Error(
                "not_found",
                "Direct viewer documentation not found",
                traceback.format_exc(),
                description_code="direct_viewer_docs_not_found",
            )
        return docs_link

    @classmethod
    def _check_viewer_ownership(cls, domain, user_id, category_id, role_id):
        """
        Shared ownership check for viewer-access helpers.

        ``domain`` must be a dict with ``user``, ``category`` and ``tag``
        fields. Returns True if the caller (identified by role_id /
        category_id / user_id) may access the desktop viewer; otherwise
        returns False so the caller can raise a 403 with the right
        message.
        """
        if role_id == "admin":
            return True
        if role_id == "manager" and domain.get("category") == category_id:
            return True
        if domain.get("user") == user_id:
            return True
        if domain.get("tag"):
            with cls._rdb_context():
                deployment = (
                    r.table("deployments")
                    .get(domain.get("tag"))
                    .pluck("user", "co_owners")
                    .run(cls._rdb_connection)
                )
            if deployment:
                if deployment.get("user") == user_id:
                    return True
                if user_id in deployment.get("co_owners", []):
                    return True
        return False

    @classmethod
    def owns_desktop_viewer_by_desktop_id(
        cls, desktop_id, user_id, category_id, role_id, connection_ip=None
    ):
        """
        Port of v3 ``Users.OwnsDesktopViewerDesktopId``.

        Checks that a desktop exists, is in a running state, and that the
        caller is authorised to reach its viewer. Used by rdpgw and
        websockify to validate a direct-viewer token against the running
        desktop before proxying the connection. Raises ``Error`` on any
        failure; returns ``True`` on success.
        """
        try:
            with cls._rdb_context():
                domain = r.table("domains").get(desktop_id).run(cls._rdb_connection)
        except Exception:
            raise Error(
                "forbidden",
                "Forbidden access to desktop viewer",
                traceback.format_exc(),
            )

        if not domain:
            raise Error(
                "not_found",
                f"Desktop {desktop_id} not found",
                traceback.format_exc(),
            )

        if domain.get("status") not in ["Started", "Shutting-down"]:
            raise Error(
                "precondition_required",
                f"Desktop {desktop_id} is not started",
                traceback.format_exc(),
            )

        # Validate connection target matches desktop's actual viewer IP
        if connection_ip and domain.get("viewer", {}).get("guest_ip") != connection_ip:
            raise Error(
                "forbidden",
                "Connection target does not match desktop viewer",
                traceback.format_exc(),
            )

        # Direct-viewer tokens are scoped to a specific desktop_id and
        # don't carry user_id. The token itself is proof of authorisation
        # (signed JWT generated after ownership was verified at viewer
        # request time). Desktop existence, status, and IP validation
        # above are sufficient.
        if user_id is None:
            return True

        if cls._check_viewer_ownership(domain, user_id, category_id, role_id):
            return True

        raise Error(
            "forbidden",
            f"Forbidden access to user {user_id} to desktop {desktop_id} viewer",
            traceback.format_exc(),
        )

    @classmethod
    def owns_desktop_viewer_by_ip(cls, user_id, category_id, role_id, guess_ip):
        """
        Port of v3 ``Users.OwnsDesktopViewerIP``.

        Looks up a running desktop by its viewer guest IP and checks
        caller ownership. Raises ``Error`` on any failure; returns
        ``True`` on success.
        """
        try:
            with cls._rdb_context():
                domains = list(
                    r.table("domains")
                    .get_all(guess_ip, index="guest_ip")
                    .filter(
                        lambda domain: r.expr(["Started", "Shutting-down"]).contains(
                            domain["status"]
                        )
                    )
                    .pluck("user", "category", "tag")
                    .run(cls._rdb_connection)
                )
        except Exception:
            log.error(traceback.format_exc())
            raise Error(
                "forbidden",
                "Forbidden access to desktop viewer",
                traceback.format_exc(),
            )
        if not len(domains):
            raise Error(
                "bad_request",
                f"No desktop with requested guess_ip {guess_ip} to access viewer",
                traceback.format_exc(),
            )
        if len(domains) > 1:
            log.error(traceback.format_exc())
            raise Error(
                "internal_server",
                "Two desktops with the same viewer guest_ip",
                traceback.format_exc(),
            )

        if cls._check_viewer_ownership(domains[0], user_id, category_id, role_id):
            return True

        raise Error(
            "forbidden",
            f"Forbidden access to user {user_id} to desktop {domains[0]} viewer",
            traceback.format_exc(),
        )

    @classmethod
    def owns_desktop_viewer_by_proxies(
        cls,
        user_id,
        category_id,
        role_id,
        proxy_video,
        proxy_hyper_host,
        port,
    ):
        """
        Port of v3 ``Users.OwnsDesktopViewerProxiesPort``.

        Looks up a running desktop by its (proxy_video, proxy_video_port,
        proxy_hyper_host) tuple and viewer port, then checks caller
        ownership. Raises ``Error`` on any failure; returns ``True`` on
        success.
        """
        try:
            proxy_video_parts = proxy_video.split(":")
            if len(proxy_video_parts) == 2:
                proxy_video = proxy_video_parts[0]
                proxy_video_port = proxy_video_parts[1]
            else:
                proxy_video_port = "443"
            with cls._rdb_context():
                domains = list(
                    r.table("domains")
                    .get_all(
                        [proxy_video, proxy_video_port, proxy_hyper_host],
                        index="proxies",
                    )
                    .filter(
                        lambda domain: r.expr(["Started", "Shutting-down"]).contains(
                            domain["status"]
                        )
                    )
                    .filter(r.row["viewer"]["ports"].contains(port))
                    .pluck("user", "category", "tag")
                    .run(cls._rdb_connection)
                )
        except Exception:
            raise Error(
                "forbidden",
                "Forbidden access to desktop viewer",
                traceback.format_exc(),
            )
        if not len(domains):
            raise Error(
                "bad_request",
                (
                    "No desktop with requested parameters "
                    f"(proxy_video: {proxy_video}, "
                    f"proxy_hyper_host: {proxy_hyper_host}, "
                    f"port: {port}) to access viewer"
                ),
                traceback.format_exc(),
            )
        if len(domains) > 1:
            raise Error(
                "internal_server",
                "Two desktops with the same viewer proxies",
                traceback.format_exc(),
            )

        if cls._check_viewer_ownership(domains[0], user_id, category_id, role_id):
            return True

        raise Error(
            "forbidden",
            f"Forbidden access to user {user_id} to desktop viewer",
            traceback.format_exc(),
        )
