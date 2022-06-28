import datetime
import itertools
import json
import locale
import os
import random
import re
import time
import unicodedata
from datetime import timedelta
from pprint import pprint

from jose import jwt
from rethinkdb import r

dbconn = r.connect("isard-db", 28015, "isard").repl()


def date_generator(from_date=datetime.datetime.today()):
    while True:
        yield from_date
        from_date = from_date + datetime.timedelta(hours=random.randrange(1, 3))


def _parseString(txt):
    if type(txt) is not str:
        txt = txt.decode("utf-8")
    prog = re.compile("[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$")
    if not prog.match(txt):
        return False
    else:
        # ~ Replace accents
        txt = "".join(
            (
                c
                for c in unicodedata.normalize("NFD", txt)
                if unicodedata.category(c) != "Mn"
            )
        )
        return txt.replace(" ", "_")


def header_auth(
    user_id=None, username=None, role_id=None, category_id=None, group_id=None
):
    if not user_id:
        user = {
            "user_id": "local-default-admin-admin",
            "role_id": "admin",
            "category_id": "default",
            "group_id": "default-default",
            "username": "admin",
            "email": "",
            "photo": "",
        }
    else:
        try:
            userdb = list(r.db("isard").table("users").get(user_id).run())[0]
            user = {
                "user_id": userdb["id"],
                "role_id": userdb["role"],
                "category_id": userdb["category"],
                "group_id": userdb["group"],
                "username": userdb["username"],
                "email": userdb["email"],
                "photo": userdb["photo"],
            }
        except:
            user = {
                "user_id": "local-default-admin-admin" if not user_id else user_id,
                "role_id": "admin" if not role_id else role_id,
                "category_id": "default" if not category_id else category_id,
                "group_id": "default-default" if not group_id else group_id,
                "username": "admin" if not username else username,
                "email": "",
                "photo": "",
            }
    print("HEADER AUTH: ")
    pprint(user)
    token = jwt.encode(
        {
            "exp": datetime.datetime.utcnow() + timedelta(seconds=20),
            "kid": "isardvdi",
            "data": user,
        },
        os.environ["API_ISARDVDI_SECRET"],
        algorithm="HS256",
    )

    return {"Authorization": "Bearer " + token}
