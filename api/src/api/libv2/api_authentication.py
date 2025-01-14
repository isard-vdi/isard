#
#   Copyright © 2023 Naomi Hidalgo
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


import os

from cachetools import TTLCache, cached
from html_sanitizer import Sanitizer
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from .api_users import ApiUsers
from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)

users = ApiUsers()

provider_config_cache = TTLCache(maxsize=10, ttl=30)


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


def add_policy(data):
    if data["category"] != "all" and data["disclaimer"]:
        raise Error(
            "bad_request", "Disclaimer option only available for all categories"
        )
    if not check_duplicate_policy(data["category"], data["role"]):
        raise Error(
            "conflict",
            data["type"] + " policy for this category and role already exists",
        )

    with app.app_context():
        r.table("authentication").insert(data).run(db.conn)


def get_policies():
    with app.app_context():
        return list(
            r.table("authentication")
            .get_all("local", index="type")
            .merge(
                lambda policy: {
                    "category_name": (
                        r.branch(
                            policy["category"] == "all",
                            "all",
                            r.table("categories")
                            .get(policy["category"])
                            .default({"name": "[DELETED]"})["name"],
                        )
                    )
                }
            )
            .run(db.conn)
        )


def get_policy(policy_id):
    with app.app_context():
        return r.table("authentication").get(policy_id).run(db.conn)


def edit_policy(policy_id, data):
    with app.app_context():
        r.table("authentication").get(policy_id).update(data).run(db.conn)


def delete_policy(policy_id):
    policy = get_policy(policy_id)
    if policy["role"] == "all" and policy["category"] == "all":
        raise Error("forbidden", "Can not delete default permissions")

    with app.app_context():
        r.table("authentication").get(policy_id).delete().run(db.conn)


def check_duplicate_policy(category, role):
    with app.app_context():
        return (
            len(
                list(
                    r.table("authentication")
                    .get_all([category, role], index="category-role")
                    .run(db.conn)
                )
            )
            <= 0
        )


###


def get_providers():
    providers = {}
    providers["local"] = not (
        os.environ.get("AUTHENTICATION_AUTHENTICATION_LOCAL_ENABLED") == "false"
    )
    providers["google"] = (
        os.environ.get("AUTHENTICATION_AUTHENTICATION_GOOGLE_ENABLED") == "true"
    )
    providers["saml"] = (
        os.environ.get("AUTHENTICATION_AUTHENTICATION_SAML_ENABLED") == "true"
    )
    providers["ldap"] = (
        os.environ.get("AUTHENTICATION_AUTHENTICATION_LDAP_ENABLED") == "true"
    )
    return providers


def force_policy_at_login(policy_id, policy_field):
    policy = get_policy(policy_id)

    if policy_field == "disclaimer_acknowledged":
        query = r.table("users")
    else:
        query = r.table("users").get_all("local", index="provider")
    if policy["category"] != "all":
        query.filter({"category": policy["category"]})
    if policy["role"] != "all":
        query.filter({"role": policy["role"]})
    with app.app_context():
        query.update({policy_field: None}).run(db.conn)


def get_disclaimer_template(user_id):
    with app.app_context():
        user = r.table("users").get(user_id).pluck("role", "lang").run(db.conn)
    template_id = users.get_user_policy("disclaimer", "all", user["role"], user_id).get(
        "template"
    )
    if template_id:
        with app.app_context():
            disclaimer = r.table("notification_tmpls").get(template_id).run(db.conn)

        if disclaimer["lang"].get(user.get("lang")):
            texts = disclaimer["lang"][user["lang"]]
            return {
                "title": texts["title"],
                "body": sanitizer.sanitize(texts["body"]),
                "footer": sanitizer.sanitize(texts["footer"]),
            }
        elif disclaimer["lang"].get(disclaimer["default"]):
            texts = disclaimer["lang"][disclaimer["default"]]
            return {
                "title": texts["title"],
                "body": sanitizer.sanitize(texts["body"]),
                "footer": sanitizer.sanitize(texts["footer"]),
            }
        raise Error("not_found", "Unable to find disclaimer template")
    else:
        return None


@cached(provider_config_cache)
def get_provider_config(provider):
    try:
        with app.app_context():
            config = r.table("config").get(1)["auth"][provider].run(db.conn)
    except:
        raise Error("not_found", "Provider config not found")
    try:
        with app.app_context():
            config["migration"]["notification_bar"]["template_name"] = (
                r.table("notification_tmpls")
                .get(config["migration"]["notification_bar"]["template"])["name"]
                .run(db.conn)
            )
    except r.ReqlNonExistenceError:
        config["template_name"] = "[DELETED]"
    return config


def update_provider_config(provider, data):
    with app.app_context():
        r.table("config").get(1).update(
            {"auth": {provider: r.row["auth"][provider].merge(data)}}
        ).run(db.conn)
    provider_config_cache.clear()


def get_migrations_exceptions():
    with app.app_context():
        return list(
            r.table("users_migrations_exceptions")
            .merge(
                lambda exception: {
                    "item_name": r.table(exception["item_type"]).get(
                        exception["item_id"]
                    )["name"]
                }
            )
            .run(db.conn)
        )


def add_migration_exception(data):
    with app.app_context():
        existing_ids = set(
            r.table("users_migrations_exceptions")
            .get_all(*data["item_ids"], index="item_id")["item_id"]
            .run(db.conn)
        )
    new_items = [
        {
            "item_type": data["item_type"],
            "item_id": item_id,
            "created_at": r.now(),
        }
        for item_id in data["item_ids"]
        if item_id not in existing_ids
    ]
    with app.app_context():
        if new_items:
            r.table("users_migrations_exceptions").insert(new_items).run(db.conn)


def delete_migration_exception(exception_id):
    with app.app_context():
        r.table("users_migrations_exceptions").get(exception_id).delete().run(db.conn)
