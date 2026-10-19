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


from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.isard_viewer import IsardViewer
from isardvdi_common.lib.domains.desktops.desktop_direct_viewer import (
    DesktopDirectViewer,
)
from isardvdi_common.lib.domains.desktops.desktop_viewers import DesktopViewers
from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed
from isardvdi_common.schemas.domains import DesktopStatusEnum
from rethinkdb import r

isard_viewer = IsardViewer()


class DeploymentDesktopsProcessed(RethinkSharedConnection):

    _rdb_table = "domains"

    @classmethod
    def get_with_tag_dict(cls, tag):
        """
        Get domains with specific deployment tag
        """
        with cls._rdb_context():
            desktops = list(
                r.table(cls._rdb_table)
                .get_all(tag, index="tag")
                .filter(lambda domain: domain["kind"] == "desktop")
                .pluck(
                    "status",
                    "user",
                    "viewer",
                    "tag_visible",
                    "id",
                    "viewers",
                    "name",
                    "username",
                    "accessed",
                    "booking_id",
                )
                .run(cls._rdb_connection)
            )

        # TODO: do this at once with all viewers, like in the old api
        # see `api/libv2/isardViewer.py` for reference
        for desktop in desktops:
            # TODO(separate-common-classes): move get_novnc_data to a DesktopHelpers class
            desktop["viewer"] = DesktopViewers.get_novnc_data(desktop)
        return desktops

    @classmethod
    def get_deployment_user_desktops(cls, deployment_id, user_id, only_visible=False):
        """
        Get the deployment for a specific user
        """
        query = (
            r.table(cls._rdb_table)
            .get_all(deployment_id, index="tag")
            .filter(lambda domain: (domain["user"].eq(user_id)))
        )
        if only_visible:
            query = query.filter({"tag_visible": True})
        with cls._rdb_context():
            desktops = (
                query.merge(
                    lambda lab: {
                        "total_desktops": r.table("domains")
                        .get_all(lab["tag"], index="tag")
                        .count()
                    }
                )
                .pluck(
                    "image",
                    "name",
                    "id",
                    "status",
                    "ip",
                    "description",
                    "accessed",
                    "total_desktops",
                    "tag_visible",
                    {"viewer": {"guest_ip", "passwd", "rdp", "rdp_last"}},
                    "guest_properties",
                    # Needed by ``parse_frontend_desktop_status`` to tell a
                    # wireguard desktop still waiting for its guest IP apart
                    # from a fully started one.
                    {"create_dict": {"hardware": "interfaces"}},
                )
                .run(cls._rdb_connection)
            )
        return list(desktops)

    @classmethod
    def user_has_visible_desktops(cls, deployment_id, user_id):
        """Whether the owner made any of this user's desktops visible to them."""
        with cls._rdb_context():
            return (
                r.table(cls._rdb_table)
                .get_all(["desktop", user_id, deployment_id], index="kind_user_tag")
                .filter({"tag_visible": True})
                .count()
                .gt(0)
                .run(cls._rdb_connection)
            )

    @classmethod
    def _visibility_selection(
        cls,
        deployment_id,
        users=None,
        tag_desktop_ids=None,
        desktop_ids=None,
        legacy_tag_desktop_id=None,
    ):
        """Build the narrowest indexed selection for a visibility scope.

        Index choice, most selective first:

        * ``desktop_ids``     -> primary key, then a ``tag`` filter so a caller
          can never reach outside the deployment.
        * ``users``           -> ``kind_user_tag``; one key per user, each
          yielding that user's |desktops| rows. A ``tag_desktop_ids`` residual
          is applied over those few rows -- cheaper than the reverse, which
          would read |users| rows to keep one.
        * ``tag_desktop_ids`` -> ``tag_tag_desktop_id``; one key per desktop.
        * neither             -> ``tag``.
        """
        if desktop_ids:
            return (
                r.table(cls._rdb_table)
                .get_all(r.args(desktop_ids))
                .filter({"tag": deployment_id, "kind": "desktop"})
            )

        # Legacy rows (pre release-184) carry ``tag_desktop_id: False``, and
        # upgrade.py backfilled them from ``create_dict[0]``. So targeting the
        # first desktop must also match rows that never got the field.
        desktop_keys = list(tag_desktop_ids) if tag_desktop_ids else None
        if (
            desktop_keys
            and legacy_tag_desktop_id
            and legacy_tag_desktop_id in desktop_keys
        ):
            desktop_keys = desktop_keys + [False]

        if users:
            selection = r.table(cls._rdb_table).get_all(
                r.args([["desktop", user, deployment_id] for user in users]),
                index="kind_user_tag",
            )
            if desktop_keys is not None:
                selection = selection.filter(
                    lambda domain: r.expr(desktop_keys).contains(
                        domain["tag_desktop_id"].default(False)
                    )
                )
            return selection

        if desktop_keys is not None:
            return r.table(cls._rdb_table).get_all(
                r.args([[deployment_id, key] for key in desktop_keys]),
                index="tag_tag_desktop_id",
            )

        return (
            r.table(cls._rdb_table)
            .get_all(deployment_id, index="tag")
            .filter({"kind": "desktop"})
        )

    @classmethod
    def set_desktops_visibility(
        cls,
        deployment_id,
        visible,
        users=None,
        tag_desktop_ids=None,
        desktop_ids=None,
        stop_started_domains=False,
    ):
        """Idempotently set ``tag_visible`` over a scoped subset.

        Returns the recomputed deployment aggregate so the caller needs no
        follow-up read.
        """
        from isardvdi_common.models.deployment import Deployment

        legacy_tag_desktop_id = Deployment.first_tag_desktop_id(deployment_id)

        selection = cls._visibility_selection(
            deployment_id,
            users=users,
            tag_desktop_ids=tag_desktop_ids,
            desktop_ids=desktop_ids,
            legacy_tag_desktop_id=legacy_tag_desktop_id,
        )

        # Only the rows that actually differ, so ``updated`` is a true change
        # count and the stop list never targets an already hidden desktop.
        with cls._rdb_context():
            changing = list(
                selection.filter(
                    lambda domain: domain["tag_visible"].default(False).ne(visible)
                )
                .pluck("id", "status")
                .run(cls._rdb_connection)
            )

        changing_ids = [domain["id"] for domain in changing]
        if changing_ids:
            with cls._rdb_context():
                r.table(cls._rdb_table).get_all(r.args(changing_ids)).update(
                    {"tag_visible": visible}
                ).run(cls._rdb_connection)

        # The master flag is derived from the desktops, never set independently.
        aggregate = Deployment.recompute_tag_visible(deployment_id, fallback=visible)

        # Feeds ``visible_desktops`` on the deployments LIST view (1s TTL).
        Caches.clear_get_cached_deployment_desktops_cache()

        stopped = []
        if stop_started_domains and not visible and changing_ids:
            stoppable = {
                DesktopStatusEnum.started.value,
                DesktopStatusEnum.starting.value,
                DesktopStatusEnum.starting_paused.value,
                DesktopStatusEnum.shutting_down.value,
            }
            stopped = [
                domain["id"] for domain in changing if domain.get("status") in stoppable
            ]
            if stopped:
                DesktopEvents.desktops_stop(stopped, force=True)

        return {
            "id": deployment_id,
            "updated": len(changing_ids),
            "stopped": stopped,
            **aggregate,
        }

    @classmethod
    def get_deployment_desktops_visibility_matrix(
        cls, deployment_id, legacy_tag_desktop_id=None
    ):
        """One row per deployment desktop, keyed by (user, tag_desktop_id).

        Feeds both the per-user aggregate (statuses / last access / "any
        visible") and the per-desktop visibility matrix from a single pass.
        """
        fallback = legacy_tag_desktop_id if legacy_tag_desktop_id is not None else False
        with cls._rdb_context():
            rows = list(
                r.table(cls._rdb_table)
                .get_all(deployment_id, index="tag")
                .filter({"kind": "desktop"})
                .map(
                    lambda domain: {
                        "user": domain["user"],
                        # Legacy rows carry ``tag_desktop_id: False``; bucket
                        # them under the first desktop, the same convention
                        # upgrade.py used to backfill the field.
                        "tag_desktop_id": r.branch(
                            domain["tag_desktop_id"].default(False).eq(False),
                            r.expr(fallback),
                            domain["tag_desktop_id"],
                        ),
                        "desktop_id": domain["id"],
                        "name": domain["name"],
                        "visible": domain["tag_visible"].default(False),
                        "status": domain["status"],
                        "accessed": domain["accessed"].default(None),
                    }
                )
                .run(cls._rdb_connection)
            )
        return rows

    @classmethod
    def update_desktops_visibility(cls, desktop_ids, visible):
        """
        Update the visibility of desktops by a list of IDs.
        """
        with cls._rdb_context():
            return (
                r.table(cls._rdb_table)
                .get_all(r.args(desktop_ids))
                .update(lambda desktop: {"tag_visible": visible})
                .run(cls._rdb_connection)
            )

    @classmethod
    def _parse_deployment_desktop(cls, desktop):
        # TODO(separate-common-classes): move this to a desktop helpers class
        if desktop["status"] in [
            DesktopStatusEnum.started.value,
            DesktopStatusEnum.waiting_ip.value,
        ] and desktop.get("viewer", {}).get("static"):
            try:
                viewer = isard_viewer.viewer_data(
                    desktop["id"],
                    "browser-vnc",
                )
            except Exception:
                viewer = False
        else:
            viewer = False
        user_photo = desktop.get("user_photo")
        desktop = DesktopsProcessed._parse_desktop(desktop)
        desktop["viewer"] = viewer
        desktop["user_photo"] = user_photo
        desktop["user_name"] = Caches.get_document("users", desktop["user"], ["name"])
        desktop["group_name"] = Caches.get_document(
            "groups", desktop["group"], ["name"]
        )
        return desktop

    @classmethod
    def jumper_url_reset(cls, deployment_id):
        with cls._rdb_context():
            deployment_desktops = list(
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck("id", "user", "jumperurl")
                .run(cls._rdb_connection)
            )

        for deployment_desktop in deployment_desktops:
            DesktopDirectViewer.gen_jumpertoken(deployment_desktop["id"])

    @classmethod
    def get_deployment_user_desktop(cls, user_id, deployment_id):
        """_From api/libv2/api_desktops_persistent.py get_deployment_user_desktop()_

        Retrieve the user desktop associated with a deployment.

        :param user_id: The ID of the user.
        :param deployment_id: The deployment ID.
        :return: The user desktop associated with the deployment.
        :rtype: dict
        """
        with cls._rdb_context():
            return (
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .filter({"user": user_id})
                .pluck(
                    "id",
                    "name",
                    "description",
                    "user",
                    "category",
                    "group",
                    "status",
                    "accessed",
                    "tag_visible",
                )
                .nth(0)
                .default(None)
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_user_desktop_ids(cls, deployment_id: str, user_id: str):
        """
        Get the all the desktop ids of a user in a deployment
        """
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(["desktop", user_id, deployment_id], index="kind_user_tag")
                .pluck("id")["id"]
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_desktop_ids(cls, deployment_id: str):
        """
        Get the all the desktop ids of a deployment
        """
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck("id")["id"]
                .run(cls._rdb_connection)
            )
