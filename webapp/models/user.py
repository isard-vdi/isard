#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import rethinkdb as r
import time

from ..lib.db import DB
from ..auth.local import check as local_check
from ..auth.ldap import check as ldap_check


class User:
    """
    User is the class that contains all the actions related with the users
    """

    # TODO: self.id and self.username need to be the same column
    # TODO: name needs to be split into name and surnames
    def __init__(self, user=None):
        self.conn = DB().conn

        if user is None:
            user = {
                "id": "",
                "password": "",
                "kind": "local",
                "name": "",
                "mail": "",
                "role": "",
                "category": "",
                "group": "",
                "active": False,
                "quota": {
                    "domains": {
                        "desktops": 0,
                        "desktops_disk_max": 0,
                        "templates": 0,
                        "templates_disk_max": 0,
                        "running": 0,
                        "isos": 0,
                        "isos_disk_max": 0,
                    },
                    "hardware": {"vcpus": 0, "memory": 0},
                },
            }

        self.id = user["id"]
        self.username = user["id"]
        self.password = user["password"]
        self.kind = user["kind"]

        self.name = user["name"]
        self.mail = user["mail"]

        self.role = user["role"]
        self.category = user["category"]
        self.group = user["group"]

        self.active = user["active"]
        self.is_admin = True if self.role == "admin" else False
        self.accessed = time.time()

        self.path = user["category"] + "/" + user["group"] + "/" + user["id"] + "/"
        self.quota = user["quota"]

    def get(self, username):
        """
        get retrieves an user from the DB using their username. If the user isn't found or is any error, it throws an
        exception
        :param username: username is the username of the user
        :param conn: conn is the connection with the RethinkDB database
        """
        user = r.table("users").get(username).run(self.conn)

        if user is None:
            raise self.NotFound()

        self.id = user["id"]
        self.username = user["id"]
        self.password = user["password"]
        self.kind = user["kind"]

        self.name = user["name"]
        self.mail = user["mail"]

        self.role = user["role"]
        self.category = user["category"]
        self.group = user["group"]

        self.active = user["active"]
        self.is_admin = True if self.role == "admin" else False
        self.accessed = user["accessed"]

        self.path = user["category"] + "/" + user["group"] + "/" + user["id"] + "/"
        self.quota = user["quota"]

    def auth(self, password):
        """
        auth checks the validity of the password sent as an arg
        :param password: password is the password that the user has introduced
        :return: auth returns True if the authentication has succeeded and False if it hasn't
        """
        if self.id == "":
            raise User.NotLoaded

        if self.id == "admin":
            return local_check(self, password)

        if not self.active:
            return False

        if self.kind == "local":
            return local_check(self, password)

        if self.kind == "ldap":
            return ldap_check(self, password)

        return False

    def update_access(self):
        """
        update_access updates the last time that the user has logged in
        :return returns the response from the DB
        """
        if self.id == "":
            raise User.NotLoaded

        rsp = (
            r.table("users")
            .get(self.id)
            .update({"accessed": time.time()})
            .run(self.conn)
        )

        if rsp["skipped"] == 1:
            raise User.NotFound

        return rsp

    class NotFound(Exception):
        """
        This exception is raised when the user isn't found in the DB
        """

        pass

    class NotLoaded(Exception):
        """
        This exception is raised when a method needs to work with the user but this is empty (not loaded). If you are
        encountering this error, you should init the User class with a dict containing the user information or call
        User.get
        """

        pass
