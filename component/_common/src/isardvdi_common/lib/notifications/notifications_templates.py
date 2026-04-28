#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Josep Maria Viñolas Auquer, Miriam Melina Gamboa Valdez
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

from cachetools import TTLCache, cached
from html_sanitizer import Sanitizer
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.users.users.user import UsersProcessed
from isardvdi_common.lib.users.users.user_policies import UserPolicies
from rethinkdb import r


def sanitize_href(href):
    if href:
        scheme = href.strip().lower().split(":")[0] if ":" in href else ""
        if scheme in ("javascript", "data", "vbscript"):
            return None
    return href


class NotificationTemplatesProcessed(RethinkSharedConnection):

    _rdb_table = "notification_tmpls"
    sanitizer = Sanitizer(
        {
            "attributes": {
                "a": ("href", "name", "target", "title", "id", "rel", "class"),
                "img": ("src", "alt", "title", "width", "height"),
            },
            "tags": {
                "a",
                "h1",
                "h2",
                "h3",
                "h4",
                "strong",
                "em",
                "p",
                "ul",
                "ol",
                "li",
                "br",
                "sub",
                "sup",
                "hr",
                "img",
            },
            "sanitize_href": sanitize_href,
            "empty": {"img"},
        }
    )

    @classmethod
    def add_notification_template(cls, template_data):
        default_lang = template_data.get("default")
        lang_data = template_data.get("lang") or {}
        if not default_lang or default_lang not in lang_data:
            raise Error(
                "bad_request",
                "Template must include 'default' and matching 'lang' entry",
                description_code="template_missing_default_lang",
            )
        texts = lang_data[default_lang]
        template_data["lang"][template_data["default"]] = {
            "title": texts["title"],
            "body": cls.sanitizer.sanitize(texts["body"]),
            "footer": cls.sanitizer.sanitize(texts["footer"]),
        }
        with cls._rdb_context():
            r.table(cls._rdb_table).insert(template_data).run(cls._rdb_connection)

    @classmethod
    def get_notification_templates(cls, kind=None):
        if kind:
            if kind == "system":
                query = r.table(cls._rdb_table).has_fields("system")
            elif kind == "custom":
                query = r.table(cls._rdb_table).filter(
                    r.row.has_fields("system").not_()
                )
        else:
            query = r.table(cls._rdb_table)
        with cls._rdb_context():
            rows = list(query.run(cls._rdb_connection))
        # Guarantee the frontend-observable shape regardless of legacy row
        # state: rows missing `lang` / `default` crashed the webapp admin
        # DataTable (addDetailPannel → tmpl.lang[tmpl.default]) and the
        # edit modal (Object.keys(data.lang)).
        for row in rows:
            row.setdefault("lang", {})
            row.setdefault("default", None)
            row.setdefault("name", "")
            row.setdefault("description", "")
        return rows

    @classmethod
    def get_notification_template(cls, template_id):
        with cls._rdb_context():
            row = (
                r.table(cls._rdb_table)
                .get(template_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if row is None:
            raise Error(
                "not_found",
                "Notification template with ID: " + template_id + " not found",
            )
        # Same shape guarantee as get_notification_templates — the webapp
        # admin edit modal does Object.keys(data.lang) and would crash on
        # legacy rows.
        row.setdefault("lang", {})
        row.setdefault("default", None)
        return row

    @classmethod
    def get_notification_template_by_kind(cls, kind):
        try:
            with cls._rdb_context():
                return (
                    r.table(cls._rdb_table)
                    .filter({"kind": kind})
                    .nth(0)
                    .run(cls._rdb_connection)
                )
        except Exception:
            raise Error(
                "not_found",
                "Notification template with kind: " + kind + " not found",
            )

    @classmethod
    def update_notification_template(cls, template_id, data):
        language = list(data["lang"].keys())[0]
        if (
            len(data["lang"][language]["body"]) > 0
            and len(data["lang"][language]["title"]) > 0
        ):
            texts = data["lang"][language]
            data["lang"][language] = {
                "title": texts["title"],
                "body": cls.sanitizer.sanitize(texts["body"]),
                "footer": cls.sanitizer.sanitize(texts["footer"]),
            }
            with cls._rdb_context():
                r.table(cls._rdb_table).get(template_id).update(data).run(
                    cls._rdb_connection
                )

        elif (
            len(data["lang"][language]["body"]) == 0
            and len(data["lang"][language]["title"]) == 0
        ):
            with cls._rdb_context():
                r.table(cls._rdb_table).get(template_id).replace(
                    r.row.without({"lang": {language: True}})
                ).run(cls._rdb_connection)
        else:
            raise Error("bad_request", "Missing title, body or footer data")

    @classmethod
    def delete_notification_template(cls, template_id):
        with cls._rdb_context():
            tpl = (
                r.table(cls._rdb_table)
                .get(template_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if tpl is None:
            raise Error(
                "not_found",
                f"Notification template {template_id} not found",
                description_code="template_not_found",
            )
        kind = tpl.get("kind")
        if kind in ["disclaimer", "desktop", "password", "email"]:
            raise Error("bad_request", "Unable to delete default templates")

        with cls._rdb_context():
            uses = (
                (
                    r.table("authentication")
                    .get_all(template_id, index="disclaimer_template")
                    .count()
                    .run(cls._rdb_connection)
                )
                + r.table("config")
                .get(1)["auth"]
                .values()
                .filter(
                    lambda provider: provider["migration"]["notification_bar"][
                        "template"
                    ]
                    == template_id
                )
                .count()
                .run(cls._rdb_connection)
                + r.table("notifications")
                .filter({"template_id": template_id})
                .count()
                .run(cls._rdb_connection)
            )
        if uses > 0:
            raise Error("bad_request", "Unable to delete a template that is in use")

        with cls._rdb_context():
            r.table(cls._rdb_table).get(template_id).delete().run(cls._rdb_connection)

    @classmethod
    def get_notification_event_template(cls, event, user_id, args):
        lang = UsersProcessed.get_user_language(user_id) if user_id else None
        data = {}
        with cls._rdb_context():
            event_rows = list(
                r.table("system_events")
                .filter({"event": event})
                .run(cls._rdb_connection)
            )
        if not event_rows:
            raise Error(
                "not_found",
                f"Unknown notification event: {event}",
                description_code="event_not_found",
            )
        event_data = event_rows[0]
        data["channels"] = event_data["channels"]

        with cls._rdb_context():
            template = (
                r.table(cls._rdb_table)
                .get(event_data["tmpl_id"])
                .run(cls._rdb_connection)
            )

        if lang in template["lang"]:
            data = template["lang"][lang]
        else:
            if template["default"] in template["lang"]:
                data = template["lang"][template["default"]]
            else:
                data = template["system"]

        from isardvdi_common.helpers.safe_format import safe_format

        data["body"] = safe_format(data["body"], **args)
        data["footer"] = safe_format(data["footer"], **args)

        return data

    @classmethod
    @cached(cache=TTLCache(maxsize=10, ttl=30))
    def get_status_bar_notification_by_provider(cls, provider):
        try:
            with cls._rdb_context():
                return (
                    r.table("config")
                    .get(1)["auth"][provider]["migration"]["notification_bar"]
                    .pluck("level", "template", "enabled")
                    .run(cls._rdb_connection)
                )
        except Exception:
            raise Error("not_found", "Provider notification bar config not found")

    @classmethod
    def get_disclaimer_template(cls, user_id: str):
        with cls._rdb_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("role", "lang", "provider")
                .run(cls._rdb_connection)
            )
        template_id = UserPolicies.get_user_policy(
            "disclaimer", "all", user["role"], user["provider"], user_id
        ).get("template")
        if template_id:
            with cls._rdb_context():
                disclaimer = (
                    r.table("notification_tmpls")
                    .get(template_id)
                    .run(cls._rdb_connection)
                )

            if disclaimer["lang"].get(user.get("lang")):
                texts = disclaimer["lang"][user["lang"]]
                return {
                    "title": texts["title"],
                    "body": cls.sanitizer.sanitize(texts["body"]),
                    "footer": cls.sanitizer.sanitize(texts["footer"]),
                }
            elif disclaimer["lang"].get(disclaimer["default"]):
                texts = disclaimer["lang"][disclaimer["default"]]
                return {
                    "title": texts["title"],
                    "body": cls.sanitizer.sanitize(texts["body"]),
                    "footer": cls.sanitizer.sanitize(texts["footer"]),
                }
            raise Error("not_found", "Unable to find disclaimer template")
        else:
            return None
