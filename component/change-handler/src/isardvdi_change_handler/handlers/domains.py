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
import logging as log

from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.cards import Cards
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.logging import Logging
from isardvdi_common.helpers.scheduler import Scheduler
from isardvdi_common.lib.deployments.deployment_desktops import (
    DeploymentDesktopsProcessed,
)
from isardvdi_common.lib.deployments.deployments import DeploymentsProcessed
from isardvdi_common.lib.domains.desktops.desktop_direct_viewer import (
    DesktopDirectViewer,
)
from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed
from isardvdi_common.models.deployment import Deployment
from isardvdi_common.schemas.domains import DesktopStatusEnum
from rethinkdb import r
from rethinkdb.errors import ReqlError

from .base import BaseHandler, json_dumps


class DomainsHandler(BaseHandler):
    def __init__(self, socketio_server, table):
        super().__init__(socketio_server, table)
        self.desktop_handler = DesktopDomainHandler(socketio_server)
        self.template_handler = TemplateDomainHandler(socketio_server)

    async def on_insert(self, new_val):
        return await self._delegate("on_insert", new_val=new_val)

    async def on_update(self, old_val, new_val):
        return await self._delegate("on_update", old_val=old_val, new_val=new_val)

    async def on_delete(self, old_val):
        # Delete user-uploaded card image if no other domain references it
        image = old_val.image or {}
        if isinstance(image, dict) and image.get("type") == "user":
            try:
                Cards.delete_card(image["id"])
            except (OSError, KeyError):
                log.exception("Failed to delete card image for domain %s", old_val.id)

        # Clean up empty deployments in "deleting" status. The rdb
        # work runs on a worker thread (via asyncio.to_thread) so the
        # event loop isn't frozen while we count rows + read +
        # potentially delete the deployment row. The pool connection
        # is held only for the duration of the to_thread call, not
        # across the trailing ``await self._delegate(...)``.
        tag = old_val.tag
        if tag and old_val.kind == "desktop":
            await asyncio.to_thread(self._cleanup_deployment_if_empty, tag)
        return await self._delegate("on_delete", old_val=old_val)

    @staticmethod
    def _cleanup_deployment_if_empty(tag):
        """Sync helper: best-effort cleanup of an empty deployment row.

        If ``tag`` has any remaining desktops, do nothing. Otherwise,
        when the deployment row is in ``deleting`` status, drop it.
        Errors are logged and swallowed — the caller's downstream
        delegate runs regardless of whether this cleanup succeeded.
        """
        try:
            with Deployment._rdb_context():
                remaining = (
                    r.table("domains")
                    .get_all(tag, index="tag")
                    .count()
                    .run(Deployment._rdb_connection)
                )
                if remaining:
                    return
                deployment = (
                    r.table("deployments").get(tag).run(Deployment._rdb_connection)
                )
                if deployment and deployment.get("status") == "deleting":
                    r.table("deployments").get(tag).delete().run(
                        Deployment._rdb_connection
                    )
        except ReqlError:
            log.exception(
                "Failed to clean up deployment %s after last desktop deleted", tag
            )

    async def _delegate(self, method_name, old_val=None, new_val=None):
        val = new_val or old_val
        domain_status = val.status
        kind = val.kind
        # The status filter only applies to insert/update; deletions must be
        # forwarded even when the row's last status is an engine-internal
        # transactional one (e.g. ForceDeleting), otherwise the client never
        # learns the desktop is gone. Matches main's api_socketio_domains.py.
        if method_name != "on_delete" and not Helpers._is_frontend_desktop_status(
            domain_status
        ):
            return
        handler = (
            self.desktop_handler
            if kind == "desktop"
            else self.template_handler if kind == "template" else None
        )
        if handler:
            method = getattr(handler, method_name)
            if method_name == "on_update":
                return await method(old_val, new_val)
            else:
                return await method(new_val or old_val)


class DesktopDomainHandler:
    def __init__(self, socketio_server):
        self.socketio_server = socketio_server

    async def emit(self, event, payload, namespace="/userspace", room=None):
        # room=None would broadcast to the whole namespace; refuse it.
        if room is None:
            log.warning(
                "Refusing to emit event '%s' on namespace '%s' with room=None (DesktopDomainHandler)",
                event,
                namespace,
            )
            return
        await self.socketio_server.emit(event, payload, namespace=namespace, room=room)

    async def on_insert(self, new_val):
        desktop = DesktopsProcessed._parse_desktop(
            new_val.model_dump(exclude_none=True)
        )
        await self.emit(
            "desktop_add",
            json_dumps(desktop),
            "/userspace",
            room=new_val.user,
        )
        await self.emit(
            "desktop_data",
            json_dumps(new_val),
            "/administrators",
            room=new_val.user,
        )
        await self.emit(
            "desktop_data",
            json_dumps(new_val),
            "/administrators",
            room=new_val.category,
        )
        await self.emit(
            "desktop_data",
            json_dumps(new_val),
            "/administrators",
            room="admins",
        )

        ## Deployment rooms handling
        if new_val.tag:
            # ``get_deployment_or_none`` rather than ``get_deployment`` —
            # the parent deployment row may already be gone if this
            # handler is racing a cascading delete; in that case the
            # deployment-delete event already fired upstream and there
            # is nothing left to update.
            deployment = DeploymentsProcessed.get_deployment_or_none(new_val.tag)
            if deployment is None:
                return
            deployment_owners = (deployment.get("co_owners") or []) + [
                deployment["user"]
            ]
            await self.emit(
                "deploymentdesktop_add",
                json_dumps(
                    DeploymentDesktopsProcessed._parse_deployment_desktop(
                        new_val.model_dump(exclude_none=True)
                    )
                ),
                namespace="/userspace",
                room=deployment_owners,
            )
            await self.emit(
                "deployments_update",
                json_dumps(deployment),
                namespace="/userspace",
                room=deployment_owners,
            )

    async def on_update(self, old_val, new_val):
        """Emit desktop update events.

        Caller (`DomainsHandler._delegate`) guarantees `new_val.additional_properties`
        is populated from the RethinkDB row and is a plain dict when present.
        This handler enriches it with `group_name` / `category_name` via
        `DesktopsProcessed.get_domain_group_and_category_name` and strips the
        `progress` key when unchanged to avoid client-side flicker.
        """
        old_progress = (old_val.additional_properties or {}).get("progress")
        new_progress = (new_val.additional_properties or {}).get("progress")
        extra = DesktopsProcessed.get_domain_group_and_category_name(new_val.id)

        ap = dict(new_val.additional_properties or {})
        if old_progress and new_progress and old_progress == new_progress:
            ap.pop("progress", None)
        start_logs_id = ap.pop("start_logs_id", None)
        ap.update(extra)

        new_val = new_val.model_copy()
        new_val.additional_properties = ap if ap else None

        ## User room handling

        # If the desktop owner has changed, is the equivalent to a delete (old user) and insert (new user)
        if old_val.user != new_val.user:
            await self.on_delete(old_val)
            await self.on_insert(new_val)
            return

        # If the desktop is now stopped or failed, we must remove any scheduled timeouts
        if old_val.status in [
            DesktopStatusEnum.stopping.value,
            DesktopStatusEnum.shutting_down.value,
            DesktopStatusEnum.started.value,
        ] and new_val.status in [
            DesktopStatusEnum.stopped.value,
            DesktopStatusEnum.failed.value,
        ]:
            Scheduler.remove_desktop_timeouts(new_val.id)
            # Send an event to the desktop hypervisor
            await self.emit(
                "desktop_hyp_stop",
                json_dumps({"id": new_val.id, "hyp_started": old_val.hyp_started}),
                namespace="/administrators",
                room="admins",
            )

        # If the desktop is starting and has a WireGuard MAC, we cache it
        if (
            old_val.status
            in [
                DesktopStatusEnum.starting.value,
                DesktopStatusEnum.starting_domain_disposable.value,
            ]
            and new_val.status == DesktopStatusEnum.started.value
        ):
            Caches.set_cached_domain_wg_mac(
                new_val.id,
                (new_val.create_dict or {}).get("hardware", {}).get("interfaces", [{}]),
            )
            # Send an event to the desktop hypervisor
            await self.emit(
                "desktop_hyp_start",
                json_dumps(
                    {
                        "hyp_started": new_val.hyp_started,
                        **new_val.model_dump(exclude_none=True),
                    }
                ),
                namespace="/administrators",
                room="admins",
            )
        # If the desktop is stopped, we invalidate the cached WireGuard MAC
        elif new_val.status == DesktopStatusEnum.stopped.value:
            Caches.invalidate_cached_domain_wg_mac(new_val.id)

        # Parse the desktop to return only the necessary fields in the emitted event
        desktop = DesktopsProcessed._parse_desktop(
            new_val.model_dump(exclude_none=True)
        )
        if start_logs_id:
            if old_val.status != new_val.status:
                if new_val.status == DesktopStatusEnum.started.value:
                    Logging.logs_domain_start_engine(
                        start_logs_id, new_val.id, new_val.hyp_started
                    )
                elif new_val.status in [
                    DesktopStatusEnum.stopped.value,
                    DesktopStatusEnum.failed.value,
                ]:
                    Logging.logs_domain_stop_engine(start_logs_id, new_val.status)
                    Scheduler.remove_desktop_timeouts(new_val.id)
                    if new_val.persistent is False:
                        Scheduler.add_nonpersistent_desktop_delete_timeout(new_val.id)
        else:
            if (
                new_val.status == DesktopStatusEnum.started.value
                and old_val.status != new_val.status
            ):
                Logging.logs_domain_start_engine(
                    start_logs_id, new_val.id, new_val.hyp_started
                )

        # Send the updated desktop information to the user
        await self.emit(
            "desktop_update",
            json_dumps(desktop),
            "/userspace",
            room=new_val.user,
        )
        await self.emit(
            "desktop_data",
            json_dumps(new_val),
            "/administrators",
            room=new_val.user,
        )
        await self.emit(
            "desktop_data",
            json_dumps(new_val),
            "/administrators",
            room=new_val.category,
        )
        await self.emit(
            "desktop_data",
            json_dumps(new_val),
            "/administrators",
            room="admins",
        )

        ## Direct viewer room
        jumperurl = (new_val.additional_properties or {}).get("jumperurl")
        new_viewer = (new_val.additional_properties or {}).get("viewer") or {}
        old_viewer = (old_val.additional_properties or {}).get("viewer") or {}

        if (
            jumperurl
            and (not new_val.tag or (new_val.tag and new_val.tag_visible))
            and new_val.status == DesktopStatusEnum.started.value
            and new_viewer.get("passwd")
            and old_viewer.get("guest_ip") != new_viewer.get("guest_ip")
        ):
            try:
                viewers = DesktopDirectViewer.desktop_viewer_from_token(
                    jumperurl, start_desktop=False
                )
            except Exception:
                log.exception(
                    "desktop_viewer_from_token failed for domain %s", new_val.id
                )
                return
            if viewers is not None:
                viewer_data = {
                    "id": viewers.pop("id", None),
                    "jwt": viewers.pop("jwt", None),
                    "name": viewers.pop("name", None),
                    "description": viewers.pop("description", None),
                    "status": viewers.pop("status"),
                    "scheduled": viewers.pop("scheduled", None),
                    "viewers": viewers["viewers"],
                    "needs_booking": viewers.pop("needs_booking", False),
                    "next_booking_start": viewers.pop("next_booking_start", None),
                    "next_booking_end": viewers.pop("next_booking_end", None),
                }
                await self.emit(
                    "directviewer_update",
                    json_dumps(viewer_data),
                    namespace="/userspace",
                    room=new_val.id,
                )

        ## Deployment rooms handling

        if new_val.tag:
            # If it's a visibility change is the equivalent to an insert
            if not old_val.tag_visible and new_val.tag_visible:
                await self.emit(
                    "desktop_add",
                    json_dumps(
                        DesktopsProcessed._parse_desktop(
                            new_val.model_dump(exclude_none=True)
                        )
                    ),
                    "/userspace",
                    room=new_val.user,
                )

            # If the desktop is not visible anymore, is the equivalent to a delete
            if not new_val.tag_visible:
                await self.emit(
                    "desktop_delete",
                    json_dumps({"id": old_val.id}),
                    namespace="/userspace",
                    room=old_val.user,
                )

            deployment = DeploymentsProcessed.get_deployment_or_none(new_val.tag)
            if deployment is None:
                return
            deployment_owners = (deployment.get("co_owners") or []) + [
                deployment["user"]
            ]
            await self.emit(
                "deploymentdesktop_update",
                json_dumps(
                    DeploymentDesktopsProcessed._parse_deployment_desktop(
                        new_val.model_dump(exclude_none=True)
                    )
                ),
                namespace="/userspace",
                room=deployment_owners,
            )

            await self.emit(
                "deployments_update",
                json_dumps(deployment),
                namespace="/userspace",
                room=deployment_owners,
            )

            # Notify the desktop owner (participant) when a desktop starts or stops
            started_statuses = {
                DesktopStatusEnum.started.value,
                DesktopStatusEnum.waiting_ip.value,
            }
            old_started = old_val.status in started_statuses
            new_started = new_val.status in started_statuses
            if old_started != new_started:
                event = (
                    "shared_deployment_desktop_start"
                    if new_started
                    else "shared_deployment_desktop_stop"
                )
                await self.emit(
                    event,
                    json_dumps({"id": new_val.tag}),
                    namespace="/userspace",
                    room=new_val.user,
                )

    async def on_delete(self, old_val):
        delete_payload = json_dumps({"id": old_val.id, "name": old_val.name})
        await self.emit(
            "desktop_delete", delete_payload, "/userspace", room=old_val.user
        )
        await self.emit(
            "desktop_delete", delete_payload, "/administrators", room=old_val.user
        )
        await self.emit(
            "desktop_delete",
            delete_payload,
            "/administrators",
            room=old_val.category,
        )
        await self.emit(
            "desktop_delete", delete_payload, "/administrators", room="admins"
        )

        if old_val.tag:
            deployment = DeploymentsProcessed.get_deployment_or_none(old_val.tag)
            if deployment is None:
                return
            deployment_owners = (deployment.get("co_owners") or []) + [
                deployment["user"]
            ]
            await self.emit(
                "deploymentdesktop_delete",
                json_dumps({"id": old_val.id}),
                namespace="/userspace",
                room=deployment_owners,
            )
            await self.emit(
                "deployments_update",
                json_dumps(deployment),
                namespace="/userspace",
                room=deployment_owners,
            )


class TemplateDomainHandler:
    def __init__(self, socketio_server):
        self.socketio_server = socketio_server

    async def emit(self, event, payload, namespace="/userspace", room=None):
        # room=None would broadcast to the whole namespace; refuse it.
        if room is None:
            log.warning(
                "Refusing to emit event '%s' on namespace '%s' with room=None (TemplateDomainHandler)",
                event,
                namespace,
            )
            return
        await self.socketio_server.emit(event, payload, namespace=namespace, room=room)

    async def on_insert(self, new_val):
        await self.emit(
            "template_add", json_dumps(new_val), "/userspace", room=new_val.user
        )
        await self.emit(
            "template_data",
            json_dumps(new_val),
            "/administrators",
            room=new_val.user,
        )
        await self.emit(
            "template_data",
            json_dumps(new_val),
            "/administrators",
            room=new_val.category,
        )
        await self.emit(
            "template_data",
            json_dumps(new_val),
            "/administrators",
            room="admins",
        )

    async def on_update(self, old_val, new_val):
        await self.emit(
            "template_update", json_dumps(new_val), "/userspace", room=new_val.user
        )
        await self.emit(
            "template_data",
            json_dumps(new_val),
            "/administrators",
            room=new_val.user,
        )
        await self.emit(
            "template_data",
            json_dumps(new_val),
            "/administrators",
            room=new_val.category,
        )
        await self.emit(
            "template_data",
            json_dumps(new_val),
            "/administrators",
            room="admins",
        )

    async def on_delete(self, old_val):
        delete_payload = json_dumps({"id": old_val.id, "name": old_val.name})
        await self.emit(
            "template_delete", delete_payload, "/userspace", room=old_val.user
        )
        await self.emit(
            "template_delete", delete_payload, "/administrators", room=old_val.user
        )
        await self.emit(
            "template_delete",
            delete_payload,
            "/administrators",
            room=old_val.category,
        )
        await self.emit(
            "template_delete", delete_payload, "/administrators", room="admins"
        )
