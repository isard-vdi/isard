#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import os
import traceback

from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import base64
import mimetypes
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from .genimage import gen_img_from_name


def get_domain_stock_card(domain_id):
    total = 0
    for i in range(0, len(domain_id)):
        total += total + ord(domain_id[i])
    total = total % 48 + 1
    return get_card(str(total) + ".jpg", "stock")


def get_card(card_id, type):
    return {
        "id": card_id,
        "url": "/assets/img/desktops/" + type + "/" + card_id,
        "type": type,
    }


class ApiCards:
    def __init__(self):
        self.stock_cards = self.read_stock_cards()
        self.cleanup_missing()

    def read_stock_cards(self):
        return [
            self.get_card(p.name, "stock")
            for p in Path(app.STOCK_CARDS).rglob("*")
            if not p.is_dir()
        ]

    def get_stock_cards(self):
        return self.stock_cards

    def get_user_cards(self, user_id, domain_id):
        with app.app_context():
            images = list(
                r.table("domains")
                .get_all(user_id, index="user")
                .pluck("image")
                .distinct()
                .run(db.conn)
            )
            proposed_img_exists = (
                r.table("domains")
                .get_all(domain_id + ".jpg", index="image_id")
                .count()
                .run(db.conn)
            )
        if domain_id:
            proposed_img = [self.get_card(domain_id + ".jpg", "user")]
            if not proposed_img_exists:
                with app.app_context():
                    domain_name = (
                        r.table("domains")
                        .get(domain_id)
                        .pluck("name")
                        .run(db.conn)["name"]
                    )
                img = gen_img_from_name(domain_name)
                img.save(os.path.join(app.USERS_CARDS, domain_id + ".jpg"))
        else:
            proposed_img = []
        return proposed_img + [
            image["image"]
            for image in images
            if image.get("image")
            and image["image"]["type"] == "user"
            and not image["image"]["id"].startswith("_")
        ]

    def upload(self, domain_id, image):
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
                img, (240, 124), method=0, bleed=0.0, centering=(0.5, 0.5)
            )
            ## Check if file not exists?
            img_resized.save(os.path.join(app.USERS_CARDS, filename))

            with app.app_context():
                r.table("domains").get(domain_id).update(
                    {"image": self.get_card(filename, image["type"])}
                ).run(db.conn)

            return filename
        except:
            raise Error(
                "internal_server",
                "Card file not saved",
                traceback.format_exc(),
            )

    def update(self, domain_id, card_id, type):
        with app.app_context():
            if (
                r.table("domains")
                .get(domain_id)
                .update({"image": self.get_card(card_id, type)})
                .run(db.conn)["skipped"]
            ):
                raise Error(
                    "not_found",
                    "Domain for card not found",
                    traceback.format_exc(),
                    description_code="not_found",
                )
        return card_id

    def get_card(self, card_id, type):
        # should we check if exists?
        # p = next(Path(app.USERS_CARDS).rglob(card_id))
        return {
            "id": card_id,
            "url": "/assets/img/desktops/" + type + "/" + card_id,
            "type": type,
        }

    def get_domain_stock_card(self, domain_id):
        total = 0
        for i in range(0, len(domain_id)):
            total += total + ord(domain_id[i])
        total = total % 48 + 1
        return self.get_card(str(total) + ".jpg", "stock")

    def get_domain_user_card(self, domain_id):
        with app.app_context():
            domain_name = (
                r.table("domains").get(domain_id).pluck("name").run(db.conn)["name"]
            )
        return self.generate_default_card(domain_id, domain_name)

    def generate_default_card(self, domain_id, domain_name):
        img = gen_img_from_name(domain_name)
        img.save(os.path.join(app.USERS_CARDS, domain_id + ".jpg"))
        return self.get_card(domain_id + ".jpg", "user")

    def delete_card(self, card_id):
        with app.app_context():
            if (
                r.table("domains")
                .get_all(card_id, index="image_id")
                .count()
                .run(db.conn)
            ):
                # Card file still used by other domains. Keep it.
                return
        try:
            img = Path(app.USERS_CARDS + "/" + card_id)
            img.unlink()
        except:
            raise Error("not_found", "Card file not found", traceback.format_exc())

    def delete_domain_card(self, domain_id, update_domain=True):
        with app.app_context():
            card = (
                r.table("domains").get(domain_id).pluck("image").run(db.conn)["image"]
            )
        if card["image"]["type"] == "user":
            if update_domain:
                with app.app_context():
                    r.table("domains").get(domain_id).update(
                        {"image": self.get_domain_stock_card(domain_id)}
                    ).run(db.conn)
            self.delete_card(card["id"])

    def set_default_stock_cards(self):
        with app.app_context():
            ids = [d["id"] for d in r.table("domains").pluck("id").run(db.conn)]
            for domain_id in ids:
                r.table("domains").get(domain_id).update(
                    {"image": self.get_domain_stock_card(domain_id)}
                ).run(db.conn)

    def cleanup_missing(self):
        files = [p.name for p in Path(app.USERS_CARDS).rglob("*") if not p.is_dir()]
        with app.app_context():
            db_files = list(
                dict.fromkeys(
                    [
                        d["image"]["id"] if d.get("image") else d["id"] + ".jpg"
                        for d in r.table("domains")
                        .pluck("id", {"image": {"id", "type"}})
                        .run(db.conn)
                        if d["image"]["type"] == "user"
                    ]
                )
            )

        for f in files:
            if f not in db_files:
                log.info("Deleting card: " + f)
                try:
                    self.delete_card(f)
                except:
                    log.error(traceback.format_exc())
