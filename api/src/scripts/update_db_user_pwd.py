#!/usr/bin/python3

import sys

import bcrypt
from rethinkdb import r

if len(sys.argv) < 3:
    print("Usage: update_db_user_pwd.py <uid> <new_password>")
    sys.exit(1)

UID = sys.argv[1]
PASSWD = sys.argv[2]
r.connect("isard-db", 28015).repl()
enc_pwd = bcrypt.hashpw(PASSWD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
user = list(r.db("isard").table("users").get_all(UID, index="uid").run())
if not user:
    print("User does not exist.")
    exit(1)
if len(user) > 1:
    print("Multiple users found.")
    exit(1)
r.db("isard").table("users").get(UID).update({"password": enc_pwd}).run()
print("Password updated successfully.")
