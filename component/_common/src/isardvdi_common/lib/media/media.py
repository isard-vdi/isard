from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.schemas.domains import DesktopStatusEnum
from rethinkdb import r

from ...helpers.desktop_events import DesktopEvents
from ..domains.domains import DomainsProcessed


class MediaProcessed(RethinkSharedConnection):

    _rdb_table = "media"

    @classmethod
    def get_info(cls, media_id):
        """
        Get Media object from RethinkDB.
        """
        with cls._rdb_context():
            media = (
                r.table(cls._rdb_table)
                .get(media_id)
                .pluck(
                    "name",
                    "id",
                    "category",
                    "allowed",
                    "description",
                    "status",
                    "user",
                    "username",
                    "kind",
                )
                .run(cls._rdb_connection)
            )
        return media

    @classmethod
    def get_media_user_group_and_category_name(cls, media_id):
        """
        Get Media group and category name from RethinkDB.
        """
        # The merge lambdas below used `.get(id).pluck("name")["name"]`
        # which raises ReqlNonExistenceError if any referenced row is
        # missing (orphan media whose user/group/category was deleted)
        # or lacks the `name` field. `.default({"name": ""})` ensures
        # a stable empty-string on missing data instead of a 500.
        with cls._rdb_context():
            media = (
                r.table(cls._rdb_table)
                .get(media_id)
                .pluck("user", "group", "category")
                .merge(
                    {
                        "group_name": r.table("groups")
                        .get(r.row["group"])
                        .default({"name": ""})["name"],
                        "category_name": r.table("categories")
                        .get(r.row["category"])
                        .default({"name": ""})["name"],
                        "user_name": r.table("users")
                        .get(r.row["user"])
                        .default({"name": ""})["name"],
                    }
                )
                .run(cls._rdb_connection)
            )
        return media

    @classmethod
    def get_user_media(cls, user_id):
        """From api/libv2/api_media ApiMedia.Media()"""
        with cls._rdb_context():
            media = list(
                r.table(cls._rdb_table)
                .get_all(user_id, index="user")
                .filter(lambda m: m["status"].ne("deleted"))
                .run(cls._rdb_connection)
            )
        return [{**m, "editable": True} for m in media]

    @classmethod
    def get_desktops_with_media(cls, media_id):
        """From api/libv2/api_media ApiMedia.DesktopList()"""
        with cls._rdb_context():
            return list(
                r.table("domains")
                .filter(
                    lambda dom: dom["create_dict"]["hardware"]["isos"].contains(
                        lambda media: media["id"].eq(media_id)
                    )
                )
                .merge(lambda d: {"user_name": r.table("users").get(d["user"])["name"]})
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "status",
                    "user",
                    "user_name",
                    {"create_dict": {"hardware": {"isos"}}},
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def remove_from_desktops(cls, media_id):
        """From api/libv2/api_media ApiMedia.DeleteDesktops()"""
        for desktop in cls.get_desktops_with_media(media_id):
            if desktop["status"] in [
                DesktopStatusEnum.starting.value,
                DesktopStatusEnum.started.value,
                DesktopStatusEnum.shutting_down.value,
            ]:
                try:
                    DesktopEvents.desktop_stop(
                        desktop["id"], force=True, wait_seconds=30
                    )
                except Exception:
                    pass

        DomainsProcessed.unassign_resource_from_desktops_and_deployments(
            "media", {"id": media_id}
        )
        for desktop in cls.get_desktops_with_media(media_id):
            DesktopEvents.desktop_updating(desktop["id"])

    @classmethod
    def admin_get_media(cls, status=None, category_id=None):
        """From api/libv2/api_media get_media()"""
        query = r.table("media")
        if status:
            if category_id:
                query = query.get_all([status, category_id], index="status_category")
            else:
                query = query.get_all(status, index="status")
        elif category_id:
            query = query.get_all(category_id, index="category")

        query = query.merge(
            lambda media: {
                "domains": r.table("domains")
                .get_all(media["id"], index="media_ids")
                .count(),
                "category_name": r.table("categories").get(media["category"])["name"],
                "group_name": r.table("groups").get(media["group"])["name"],
                "user_name": r.table("users").get(media["user"])["name"],
            }
        )

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def admin_get_media_status_count(cls, category_id=None):
        """From api/libv2/api_media get_status()"""
        query = r.table("media")

        if category_id:
            query = query.get_all(category_id, index="category")

        query = query.pluck("status", "user", "category")
        query = (
            query.group("status")
            .count()
            .ungroup()
            .map(lambda doc: {"status": doc["group"], "count": doc["reduction"]})
        )

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def get_media_domains(cls, media_ids):
        """_From /api/libv2/api_storage.py get_media_domains()_"""
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(media_ids, index="media_ids")
                .eq_join("user", r.table("users"))
                .pluck(
                    {
                        "left": {
                            "name": True,
                            "kind": True,
                            "id": True,
                            "user": True,
                        },
                        "right": {
                            "id": True,
                            "group": True,
                            "category": True,
                            "role": True,
                            "name": True,
                            "username": True,
                        },
                    }
                )
                .map(
                    lambda doc: {
                        "id": doc["left"]["id"],
                        "name": doc["left"]["name"],
                        "kind": doc["left"]["kind"],
                        "user": doc["left"]["user"],
                        "user_data": {
                            "role_id": doc["right"]["role"],
                            "category_id": doc["right"]["category"],
                            "group_id": doc["right"]["group"],
                            "user_id": doc["right"]["id"],
                            "user_name": doc["right"]["name"],
                            "username": doc["right"]["username"],
                        },
                    }
                )
                .merge(
                    lambda doc: {
                        "category_name": r.table("categories").get(
                            doc["user_data"]["category_id"]
                        )["name"],
                        "group_name": r.table("groups").get(
                            doc["user_data"]["group_id"]
                        )["name"],
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_medias_names(cls, media_ids: list[str]):
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .get_all(r.args(media_ids))
                .pluck("id", "name")
                .run(cls._rdb_connection)
            )

    @classmethod
    def list_domain_attached_media(cls, domain_id):
        """_From /api/libv2/api_media.py ApiMedia.List()_

        Return the list of media items (isos + floppies) currently attached
        to the given domain's create_dict.hardware. Each entry is
        ``{"id", "name", "kind", "size"}`` where ``size`` comes from the
        downloaded media progress total. Media entries that no longer exist
        in the media table are skipped.
        """
        with cls._rdb_context():
            hardware = (
                r.table("domains")
                .get(domain_id)
                .pluck({"create_dict": "hardware"})
                .run(cls._rdb_connection)
            )
        hardware = (hardware or {}).get("create_dict", {}).get("hardware", {}) or {}
        attached = []
        for kind, field in (("iso", "isos"), ("floppy", "floppies")):
            for entry in hardware.get(field, []) or []:
                try:
                    with cls._rdb_context():
                        media = (
                            r.table(cls._rdb_table)
                            .get(entry["id"])
                            .pluck("id", "name", {"progress": "total"})
                            .run(cls._rdb_connection)
                        )
                except Exception:
                    continue
                if not media:
                    continue
                attached.append(
                    {
                        "id": media["id"],
                        "name": media["name"],
                        "kind": kind,
                        "size": (media.get("progress") or {}).get("total"),
                    }
                )
        return attached
