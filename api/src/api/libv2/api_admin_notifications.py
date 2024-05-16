#
#   Copyright © 2024 Naomi Hidalgo Piñar
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

from html_sanitizer import Sanitizer
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from ..libv2.api_users import ApiUsers
from .flask_rethink import RDB


def no_sanitize_href(href):
    return href


sanitizer = Sanitizer(
    {
        "attributes": {"a": ("href", "name", "target", "title", "id", "rel", "class")},
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
        },
        "sanitize_href": no_sanitize_href,
    }
)
r = RethinkDB()
db = RDB(app)
users = ApiUsers()
db.init_app(app)


def add_notification_template(template_data):
    texts = template_data["lang"][template_data["default"]]
    template_data["lang"][template_data["default"]] = {
        "title": texts["title"],
        "body": sanitizer.sanitize(texts["body"]),
        "footer": sanitizer.sanitize(texts["footer"]),
    }
    with app.app_context():
        r.table("notification_tmpls").insert(template_data).run(db.conn)


def get_notification_templates():
    with app.app_context():
        return list(r.table("notification_tmpls").run(db.conn))


def get_notification_template(template_id):
    with app.app_context():
        try:
            return r.table("notification_tmpls").get(template_id).run(db.conn)
        except:
            raise Error(
                "not_found",
                "Notification template with ID: " + template_id + " not found",
            )


def update_notification_template(template_id, data):
    language = list(data["lang"].keys())[0]
    if (
        len(data["lang"][language]["body"]) > 0
        and len(data["lang"][language]["title"]) > 0
    ):
        texts = data["lang"][language]
        data["lang"][language] = {
            "title": texts["title"],
            "body": sanitizer.sanitize(texts["body"]),
            "footer": sanitizer.sanitize(texts["footer"]),
        }
        with app.app_context():
            r.table("notification_tmpls").get(template_id).update(data).run(db.conn)

    elif (
        len(data["lang"][language]["body"]) == 0
        and len(data["lang"][language]["title"]) == 0
    ):
        with app.app_context():
            r.table("notification_tmpls").get(template_id).replace(
                r.row.without({"lang": {language: True}})
            ).run(db.conn)
    else:
        raise Error("bad_request", "Missing title, body or footer data")


def delete_notification_template(template_id):
    with app.app_context():
        kind = (
            r.table("notification_tmpls").get(template_id).pluck("kind").run(db.conn)
        ).get("kind")
    if kind in ["disclaimer", "desktop", "password", "email"]:
        raise Error("bad request", "Unable to delete default templates")

    # TODO: check it's not being used
    r.table("notification_tmpls").get(template_id).delete().run(db.conn)


def get_notification_event_template(event, user_id, args):
    lang = users.get_lang(user_id) if user_id else None
    data = {}
    with app.app_context():
        event_data = list(
            r.table("system_events").filter({"event": event}).run(db.conn)
        )[0]
        data["channels"] = event_data["channels"]

        template = r.table("notification_tmpls").get(event_data["tmpl_id"]).run(db.conn)

        if lang in template["lang"]:
            data = template["lang"][lang]
        else:
            if template["default"] in template["lang"]:
                data = template["lang"][template["default"]]
            else:
                data = template["system"]

        data["body"] = data["body"].format(**args)
        data["footer"] = data["footer"].format(**args)

    return data
