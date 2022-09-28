# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import time

import requests

#!/usr/bin/env python
# coding=utf-8
import rethinkdb as r
from flask import request
from flask_login import LoginManager, UserMixin

from webapp import app

from ..lib.flask_rethink import RethinkDB

db = RethinkDB(app)
db.init_app(app)
import traceback

from ..lib.log import *

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "remote_logout"

ram_users = {}


class LocalUsers:
    def __init__(self):
        None

    def getUser(self, username):
        with app.app_context():
            usr = r.table("users").get(username).run(db.conn)
            if usr is None:
                return None
            usr["group_uid"] = (
                r.table("groups").get(usr["group"]).pluck("uid").run(db.conn)["uid"]
            )
        return usr

    def getUserWithGroup(self, usr):
        with app.app_context():
            if usr is None:
                return None
            usr["group_uid"] = (
                r.table("groups").get(usr["group"]).pluck("uid").run(db.conn)["uid"]
            )
        return usr


class User(UserMixin):
    def __init__(self, dict):
        self.id = dict["id"]
        self.provider = dict["provider"]
        self.category = dict["category"]
        self.uid = dict["uid"]
        self.username = dict["username"]
        self.name = dict["name"]
        self.role = dict["role"]
        self.group = dict["group"]
        self.path = (
            dict["category"]
            + "/"
            + dict["group_uid"]
            + "/"
            + dict["provider"]
            + "/"
            + dict["uid"]
            + "-"
            + dict["username"]
            + "/"
        )
        self.email = dict["email"]
        self.quota = dict["quota"]
        self.auto = dict["auto"] if "auto" in dict.keys() else False
        self.is_admin = True if self.role == "admin" else False
        self.active = dict["active"]
        self.tags = dict.get("tags", [])
        self.photo = dict["photo"]

    def is_active(self):
        return self.active

    def is_anonymous(self):
        return False


def get_authenticated_user():
    """Check if session is authenticated by jwt

    :returns: User object if authenticated
    """

    auth = request.headers.get("Authorization", None)
    if not auth:
        return None

    response = requests.get(
        "http://isard-api:5000/api/v3/user", headers={"Authorization": auth}
    )
    if response.status_code == 200:
        user = app.localuser.getUserWithGroup(json.loads(response.text))
        if user:
            return User(user)
    return None


def logout_ram_user(username):
    del ram_users[username]


@login_manager.user_loader
def user_loader(username):
    if username not in ram_users:
        user = app.localuser.getUser(username)
        if user is None:
            return
        ram_users[username] = user
    return User(ram_users[username])


def user_reloader(username):
    user = app.localuser.getUser(username)
    if user is None:
        return
    ram_users[username] = user
    return User(ram_users[username])


"""
LOCAL AUTHENTICATION AGAINS RETHINKDB USERS TABLE
"""


class auth(object):
    def __init__(self):
        None

    def check(self, username, password):
        if username == "admin":
            user_validated = self.authentication_local(username, password)
            if user_validated:
                self.update_access(username)
                return user_validated
        with app.app_context():
            cfg = r.table("config").get(1).run(db.conn)
        if cfg is None:
            return False
        local_auth = cfg["auth"]["local"]
        with app.app_context():
            local_user = r.table("users").get(username).run(db.conn)
        if local_user != None:
            if local_user["provider"] == "local" and local_auth["active"]:
                user_validated = self.authentication_local(username, password)
                if user_validated:
                    self.update_access(username)
                    return user_validated
        return False

    def authentication_local(self, username, password):
        with app.app_context():
            dbuser = r.table("users").get(username).run(db.conn)
            # log.info('USER:'+username)
            if dbuser is None or dbuser["active"] is not True:
                return False
            dbuser["group_uid"] = (
                r.table("groups").get(dbuser["group"]).pluck("uid").run(db.conn)["uid"]
            )
        pw = Password()
        if pw.valid(password, dbuser["password"]):
            # ~ TODO: Check active or not user
            return User(dbuser)
        else:
            return False

    def update_access(self, username):
        with app.app_context():
            r.table("users").get(username).update({"accessed": int(time.time())}).run(
                db.conn
            )


"""
PASSWORDS MANAGER
"""
import random
import string

import bcrypt


class Password(object):
    def __init__(self):
        None

    def valid(self, plain_password, enc_password):
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"), enc_password.encode("utf-8")
            )
        except:
            # If password is too short could lead to 'Invalid salt' Exception
            return False

    def encrypt(self, plain_password):
        return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

    def generate_human(self, length=6):
        chars = string.ascii_letters + string.digits + "!@#$*"
        rnd = random.SystemRandom()
        return "".join(rnd.choice(chars) for i in range(length))
