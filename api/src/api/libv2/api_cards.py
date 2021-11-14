#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import ipaddress
import os
import time
import traceback
from datetime import datetime, timedelta

import requests
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from rethinkdb.errors import ReqlNonExistenceError, ReqlTimeoutError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import base64
import mimetypes
import uuid
from io import BytesIO
from pathlib import Path
from subprocess import check_call, check_output

from PIL import Image, ImageOps
from werkzeug.utils import secure_filename

from ..auth.authentication import *
from .genimage import gen_img_from_name


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
                return CardError(
                    {
                        "error": "not_saved",
                        "msg": "Uploaded file with unknown format to guess extension",
                    },
                    304,
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
            raise CardError({"error": "not_saved", "msg": "Card file not saved"}, 304)

    def update(self, domain_id, card_id, type):
        with app.app_context():
            if (
                r.table("domains")
                .get(domain_id)
                .update({"image": self.get_card(card_id, type)})
                .run(db.conn)["skipped"]
            ):
                raise CardError({"error": "not_found", "msg": "Domain not found"}, 404)
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
                return CardError(
                    {"error": "exists", "msg": "Card file still used by other domains"},
                    304,
                )
        try:
            img = Path(app.USERS_CARDS + "/" + card_id)
            img.unlink()
        except:
            print(traceback.format_exc())
            raise CardError({"error": "not_found", "msg": "Card file not found"}, 304)

    def delete_domain_card(self, domain_id, update_domain=True):
        with app.app_context():
            card_id = (
                r.table("domains")
                .get(domain_id)
                .pluck({"image": "id"})
                .run(db.conn)["image"]["id"]
            )
            if update_domain:
                r.table("domains").get(domain_id).update(
                    {"image": self.get_domain_stock_card(domain_id)}
                ).run(db.conn)
        self.delete_card(card_id)

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
                print("Deleting card: " + f)
                try:
                    self.delete_card(f)
                except:
                    print(traceback.format_exc())


# Error handler
class CardError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code


@app.errorhandler(CardError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response
