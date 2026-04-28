#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases, Miriam Melina Gamboa Valdez
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


import base64
import importlib
import importlib.util
import logging as log
import mimetypes
import os
import shutil
import traceback
import uuid
from io import BytesIO
from pathlib import Path

from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from PIL import Image, ImageOps
from rethinkdb import r

from .gen_image import gen_img_from_name

api_spec = importlib.util.find_spec("api")
if api_spec and api_spec.origin == "/api/api/__init__.py":
    """APIv3"""
    from api import app as _

    USERS_CARDS = _.USERS_CARDS
    STOCK_CARDS = _.STOCK_CARDS


elif api_spec and api_spec.origin == "/app/api/__init__.py":
    """APIv4"""
    APP_ROOT = "/app/api/"

    STOCK_CARDS = os.path.join(APP_ROOT, "static/assets/img/desktops/stock")
    if not os.path.exists(STOCK_CARDS):
        os.makedirs(STOCK_CARDS, exist_ok=True)
    USERS_CARDS = os.path.join(APP_ROOT, "static/assets/img/desktops/user")
    if not os.path.exists(USERS_CARDS):
        os.makedirs(USERS_CARDS, exist_ok=True)
    STOCK_ASSETS_SEED = os.path.join(APP_ROOT, "static/stock_assets")


def _safe_card_path(base_dir, filename):
    """Resolve path and ensure it stays within base_dir (prevent path traversal)."""
    resolved = os.path.realpath(os.path.join(base_dir, filename))
    if not resolved.startswith(
        os.path.realpath(base_dir) + os.sep
    ) and resolved != os.path.realpath(base_dir):
        raise Exception(f"Invalid card filename: {filename}")
    return resolved


class Cards(RethinkSharedConnection):
    @classmethod
    def seed_stock_cards(cls):
        # Mirrors apiv3's Flask startup behavior (api/src/api/__init__.py
        # on main / apiv4-and-websockets): copy bundled stock images into
        # STOCK_CARDS so isard-static (nginx) serves them via the shared
        # host bind-mount on fresh installs.
        seed_dir = globals().get("STOCK_ASSETS_SEED")
        if not seed_dir or not os.path.isdir(seed_dir):
            return
        for filename in os.listdir(seed_dir):
            src = os.path.join(seed_dir, filename)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(STOCK_CARDS, filename)
            if os.path.isfile(dst):
                if os.stat(src).st_mtime - os.stat(dst).st_mtime > 1:
                    shutil.copy2(src, dst)
            else:
                shutil.copy(src, dst)

    @classmethod
    def read_stock_cards(cls):
        return [
            cls.get_card(p.name, "stock")
            for p in Path(STOCK_CARDS).rglob("*")
            if not p.is_dir()
        ]

    @classmethod
    @cached(cache=TTLCache(maxsize=1, ttl=3600))
    def get_stock_cards(cls):
        return cls.read_stock_cards()

    @classmethod
    def get_user_cards(cls, user_id, domain_id):
        with cls._rdb_context():
            images = list(
                r.table("domains")
                .get_all(user_id, index="user")
                .pluck("image")
                .distinct()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            proposed_img_exists = (
                r.table("domains")
                .get_all(domain_id + ".jpg", index="image_id")
                .count()
                .run(cls._rdb_connection)
            )
        if domain_id:
            proposed_img = [cls.get_card(domain_id + ".jpg", "user")]
            if not proposed_img_exists:
                with cls._rdb_context():
                    domain_name = (
                        r.table("domains")
                        .get(domain_id)
                        .pluck("name")
                        .run(cls._rdb_connection)["name"]
                    )
                img = gen_img_from_name(domain_name)
                img.save(_safe_card_path(USERS_CARDS, domain_id + ".jpg"))
        else:
            proposed_img = []
        return proposed_img + [
            image["image"]
            for image in images
            if image.get("image")
            and image["image"]["type"] == "user"
            and not image["image"]["id"].startswith("_")
        ]

    @classmethod
    def upload(cls, domain_id, image):
        try:
            img_data = image["file"]["data"]
            img = Image.open(BytesIO(base64.b64decode(img_data)))
            extension = mimetypes.guess_extension(img.get_format_mimetype())
            if extension not in [".jpg", ".png", ".gif"]:
                raise Error(
                    "precondition_required",
                    "Uploaded file with unknown format to guess extension",
                    traceback.format_exc(),
                )
            filename = str(uuid.uuid4()) + extension
            img_resized = ImageOps.fit(
                img, (480, 248), method=0, bleed=0.0, centering=(0.5, 0.5)
            )
            ## Check if file not exists?
            img_resized.save(_safe_card_path(USERS_CARDS, filename))

            with cls._rdb_context():
                r.table("domains").get(domain_id).update(
                    {"image": cls.get_card(filename, image["type"])}, durability="soft"
                ).run(cls._rdb_connection)

            return filename
        except Exception:
            raise Error(
                "internal_server",
                "Card file not saved",
                traceback.format_exc(),
            )

    @classmethod
    def update(cls, domain_id, card_id, type):
        with cls._rdb_context():
            if (
                r.table("domains")
                .get(domain_id)
                .update({"image": cls.get_card(card_id, type)}, durability="soft")
                .run(cls._rdb_connection)["skipped"]
            ):
                raise Error(
                    "not_found",
                    "Domain for card not found",
                    traceback.format_exc(),
                    description_code="not_found",
                )
        return card_id

    @classmethod
    def get_card(cls, card_id, type):
        # should we check if exists?
        # p = next(Path(app.USERS_CARDS).rglob(card_id))
        return {
            "id": card_id,
            "url": "/assets/img/desktops/" + type + "/" + card_id,
            "type": type,
        }

    @classmethod
    def get_domain_stock_card(cls, domain_id):
        total = 0
        for i in range(0, len(domain_id)):
            total += total + ord(domain_id[i])
        total = total % 48 + 1
        return cls.get_card(str(total) + ".jpg", "stock")

    @classmethod
    def get_domain_user_card(cls, domain_id):
        with cls._rdb_context():
            domain_name = (
                r.table("domains")
                .get(domain_id)
                .pluck("name")
                .run(cls._rdb_connection)["name"]
            )
        return cls.generate_default_card(domain_id, domain_name)

    @classmethod
    def generate_default_card(cls, domain_id, domain_name):
        img = gen_img_from_name(domain_name)
        img.save(_safe_card_path(USERS_CARDS, domain_id + ".jpg"))
        return cls.get_card(domain_id + ".jpg", "user")

    @classmethod
    def delete_card(cls, card_id):
        with cls._rdb_context():
            if (
                r.table("domains")
                .get_all(card_id, index="image_id")
                .count()
                .run(cls._rdb_connection)
            ):
                # Card file still used by other domains. Keep it.
                return
        try:
            img = Path(_safe_card_path(USERS_CARDS, card_id))
            img.unlink()
        except Exception:
            raise Error("not_found", "Card file not found", traceback.format_exc())

    # TODO: This method is not used in the current codebase, consider removing it.
    @classmethod
    def delete_domain_card(cls, domain_id, update_domain=True):
        with cls._rdb_context():
            card = (
                r.table("domains")
                .get(domain_id)
                .pluck("image")
                .run(cls._rdb_connection)["image"]
            )
        if card["image"]["type"] == "user":
            if update_domain:
                with cls._rdb_context():
                    r.table("domains").get(domain_id).update(
                        {"image": cls.get_domain_stock_card(domain_id)}
                    ).run(cls._rdb_connection)
            cls.delete_card(card["id"])

    # TODO: This method is not used in the current codebase, consider removing it.
    @classmethod
    def set_default_stock_cards(cls):
        with cls._rdb_context():
            ids = [
                d["id"] for d in r.table("domains").pluck("id").run(cls._rdb_connection)
            ]
        for domain_id in ids:
            with cls._rdb_context():
                r.table("domains").get(domain_id).update(
                    {"image": cls.get_domain_stock_card(domain_id)}
                ).run(cls._rdb_connection)

    @classmethod
    def cleanup_missing(cls):
        files = [p.name for p in Path(USERS_CARDS).rglob("*") if not p.is_dir()]
        with cls._rdb_context():
            db_files = list(
                dict.fromkeys(
                    [
                        d["image"]["id"] if d.get("image") else d["id"] + ".jpg"
                        for d in r.table("domains")
                        .pluck("id", {"image": {"id", "type"}})
                        .run(cls._rdb_connection)
                        if d.get("image", {}).get("type") == "user"
                    ]
                )
            )

        for f in files:
            if f not in db_files:
                log.info("Deleting card: " + f)
                try:
                    cls.delete_card(f)
                except Exception:
                    log.error(traceback.format_exc())
