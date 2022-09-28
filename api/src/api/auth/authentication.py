# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time

#!/usr/bin/env python
# coding=utf-8
from flask_login import LoginManager, UserMixin
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from ..libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..libv2.log import *

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

ram_users = {}


class LocalUsers:
    def __init__(self):
        None

    def getUser(self, username):
        with app.app_context():
            usr = r.table("users").get(username).run(db.conn)
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


def logout_ram_user(username):
    del ram_users[username]


@login_manager.user_loader
def user_loader(username):
    if username not in ram_users:
        user = app.localuser.getUser(username)
        if user == None:
            return
        ram_users[username] = user
    return User(ram_users[username])


"""
LOCAL AUTHENTICATION AGAINS RETHINKDB USERS TABLE
"""


class auth(object):
    def __init__(self):
        None

    def _check(self, username, password):
        if username == "admin":
            user_validated = self.authentication_local(username, password)
            if user_validated:
                self.update_access(username)
                return user_validated
        with app.app_context():
            cfg = r.table("config").get(1).run(db.conn)
        if cfg == None:
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


"""
VOUCHER AUTH
"""
import smtplib


class Email(object):
    def __init__(self):
        try:
            self.passwd = os.environ.get("ISARDMAILKEY")
        except Exception as e:
            print("Environtment email password not found.")

    def send(self, to_addr_list, subject, message):
        login = "isard.vdi@gmail.com"
        # In bash do: export ISARDMAILKEY=some_value
        password = os.environ.get("ISARDMAILKEY")
        smtpserver = "smtp.gmail.com"
        smtpport = 587
        from_addr = "isard.vdi@gmail.com"
        subject = subject
        message = message
        header = "From: %s\n" % from_addr
        header += "To: %s\n" % ",".join(to_addr_list)
        # header += 'Cc: %s\n' % ','.join(cc_addr_list)
        header += "Subject: %s\n\n" % subject
        message = header + message

        server = smtplib.SMTP(smtpserver, smtpport)  # use both smtpserver  and -port
        server.starttls()
        server.login(login, password)
        problems = server.sendmail(from_addr, to_addr_list, message)
        server.quit()
        # ~ print 'Sent email: '+error_header

    def email_validation(self, email, code):
        subject = "IsardVDI email verification"
        message = (
            "You have requested access to IsardVDI online demo platform through this email address.\n\n"
            + "Please access this link to get your demo user: https://try.isardvdi.com/voucher_validation/"
            + code
        )
        self.send([email], subject, message)

    def account_activation(self, email, user, passwd):
        subject = "IsardVDI credentials"
        message = (
            "Here you have your demo user and passwords: \n\n"
            + "Username: "
            + user
            + "\n"
            + "Password: "
            + passwd
            + "\n\n"
            + "IsardVDI:  https://try.isardvdi.com"
        )
        self.send([email], subject, message)


class auth_voucher(object):
    def __init__(self):
        self.pw = Password()
        self.email = Email()

    def check_voucher(self, voucher):
        with app.app_context():
            dbv = r.table("vouchers").get(voucher).run(db.conn)
        if dbv == None:
            return False
        return True

    def check_validation(self, code):
        with app.app_context():
            user = list(r.table("users").filter({"code": code}).run(db.conn))
        if not len(user):
            return False
        return True

    def check_user_exists(self, email):
        with app.app_context():
            user = r.table("users").get(email).run(db.conn)
        if user == None:
            return False
        return True

    def register_user(self, voucher, email, remote_addr):
        user = self.user_tmpl(voucher, email, remote_addr)
        with app.app_context():
            if not r.table("categories").get(user["category"]).run(db.conn):
                r.table("categories").insert(
                    {
                        "id": user["category"],
                        "name": user["category"],
                        "description": "",
                        "quota": r.table("roles")
                        .get(user["role"])
                        .run(db.conn)["quota"],
                    }
                ).run(db.conn)
            if not r.table("groups").get(user["group"]).run(db.conn):
                r.table("groups").insert(
                    {
                        "id": user["group"],
                        "name": user["group"],
                        "description": "",
                        "quota": r.table("categories")
                        .get(user["category"])
                        .run(db.conn)["quota"],
                    }
                ).run(db.conn)
            r.table("users").insert(user, conflict="update").run(db.conn)

        # Send email with code=user['code']
        self.email.email_validation(email, user["code"])
        return User(user)
        # ~ return False

    def activate_user(self, code, remote_addr):
        with app.app_context():
            user = list(r.table("users").filter({"code": code}).run(db.conn))
        if len(user):
            user = user[0]
            key = self.pw.generate_human()
            with app.app_context():
                r.table("users").filter({"code": code}).update(
                    {"active": True, "password": self.pw.encrypt(key)}
                ).run(db.conn)
                log = list(r.table("users").filter({"code": code}).run(db.conn))[0][
                    "log"
                ]
            log.append(
                {"when": int(time.time()), "ip": remote_addr, "action": "Activate user"}
            )
            with app.app_context():
                r.table("users").filter({"code": code}).update({"log": log}).run(
                    db.conn
                )
            # Send email with email=user['email'], user=user['username'], key
            self.email.account_activation(user["email"], user["username"], key)
            return True
        return False

    def user_tmpl(self, voucher, email, remote_addr):
        usr = {
            "id": email.replace("@", "_").replace(".", "_"),
            "name": email.split("@")[0],
            "provider": "local",
            "active": False,
            "accessed": int(time.time()),
            "username": email.replace("@", "_").replace(".", "_"),
            "password": self.pw.encrypt(
                self.pw.generate_human()
            ),  # Unknown temporary key, updated on activate_user
            "code": self.pw.encrypt(self.pw.generate_human())
            .replace("/", "-")
            .replace(".", "_"),  # Code for email confirmation
            "log": [
                {"when": int(time.time()), "ip": remote_addr, "action": "Register user"}
            ],
            "role": "advanced",
            "category": voucher,
            "group": voucher,
            "email": email,
            "quota": {
                "domains": {
                    "desktops": 3,
                    "desktops_disk_max": 999999999,  # 1TB
                    "templates": 2,
                    "templates_disk_max": 999999999,
                    "running": 1,
                    "isos": 1,
                    "isos_disk_max": 999999999,
                },
                "hardware": {"vcpus": 2, "memory": 20000000},
            },  # 2GB
        }
        with app.app_context():
            r.table("users").insert(usr, conflict="update").run(db.conn)
        return usr

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
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), enc_password.encode("utf-8")
        )

    def encrypt(self, plain_password):
        return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

    def generate_human(self, length=6):
        chars = string.ascii_letters + string.digits + "!@#$*"
        rnd = random.SystemRandom()
        return "".join(rnd.choice(chars) for i in range(length))
