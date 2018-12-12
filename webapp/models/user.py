#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import rethinkdb as r
import time
from flask_login import UserMixin

from ..lib.db import DB
from .category import Category
from .group import Group
from ..auth.auth import initialize_kinds


class User(UserMixin):
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
                "role": None,
                "category": "",
                "group": "",
                "active": False,
                "quota": None,
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

        self.quota = user["quota"]

        self.kinds = initialize_kinds()

    def get(self, user_id):
        """
        get retrieves an user from the DB using their username. If the user isn't found or is any error, it throws an
        exception
        :param user_id: username is the username of the user
        """
        user = r.table("users").get(user_id).run(self.conn)

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

        self.quota = user["quota"]

    def get_quota(self):
        """
        get_quota sets the correct quota of the user. If the user quota is None, it calls the category mehtod (*User* -> Group -> Category -> Role ["user" by default])
        """
        if not self.quota:
            try:
                if self.group:
                    group = Group()
                    group.get(self.group)

                else:
                    raise Group.NotFound

            except Group.NotFound:
                self.quota = {
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
                }

            else:
                group.get_quota()
                self.quota = group.quota

    def get_desktops(self):
        """
        get_desktops retrieves all the desktops of the user from the DB
        :return: returns a list containing all the desktops of the user
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        return list(
            r.table("domains")
            .get_all(self.id, index="user")
            .filter({"kind": "desktop"})
            .run(self.conn)
        )

    def get_started_desktops(self):
        """
        get_started_desktops retrieves all the started desktops of the user from the DB
        :return: returns a list containing all the started desktops of the user
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        return list(
            r.table("domains")
            .get_all(self.id, index="user")
            .filter({"kind": "desktop", "status": "Started"})
            .run(self.conn)
        )

    def get_templates(self):
        """
        get_templates retrieves all the templates of the user form the DB
        :return: returns a list containing all the templates of the user
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        return list(
            r.table("domains")
            .get_all(self.id, index="user")
            .filter({"kind": "user_template"})
            .run(self.conn)
        )

    def get_media(self):
        """
        get_media retrieves all the media of the user from the DB
        :return: returns a list containing all the media of the user
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        return list(r.table("media").get_all(self.id, index="user").run(self.conn))

    def create(self):
        """
        create inserts the user to the DB
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        try:
            self.get(self.id)

        except self.NotFound:
            user = {
                "id": self.id,
                "username": self.username,
                "password": self.password,
                "kind": self.kind,
                "name": self.name,
                "mail": self.mail,
                "role": self.role,
                "category": self.category,
                "group": self.group,
                "active": self.active,
                "accessed": 0,
                "quota": self.quota,
            }

            if self.kind != "local":
                user = self.kinds[self.kind].get_user(self.id)

                category = Category()

                try:
                    category.get(user["category"])

                except category.NotFound:
                    category = Category(
                        self.kinds[self.kind].get_category(user["category"])
                    )
                    category.create()

                group = Group()

                try:
                    group.get(user["group"])

                except group.NotFound:
                    group = Group(
                        self.kinds[self.kind].get_group(user["group"], category.id)
                    )
                    group.create()

            r.table("users").insert(user).run(self.conn)

        else:
            raise self.Exists

    def update_access(self):
        """
        update_access updates the last time that the user has logged in
        :return returns the response from the DB
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        rsp = (
            r.table("users")
            .get(self.id)
            .update({"accessed": time.time()})
            .run(self.conn)
        )

        if rsp["skipped"] == 1:
            raise self.NotFound

        return rsp

    def auth(self, password):
        """
        auth checks the validity of the password sent as an arg
        :param password: password is the password that the user has introduced
        :return: auth returns True if the authentication has succeeded and False if it hasn't
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        if self.id == "admin":
            return self.kinds["local"].check(self, password)

        if not self.active:
            return False

        if self.kind in self.kinds:
            return self.kinds[self.kind].check(self, password)

        return False

    def is_active(self):
        """
        is_active is a function used by flask-login to check if the user is disabled or not
        :return: returns the status of the user
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        return self.active

    def is_anonymous(self):
        """
        is_anonymous is a function used by flask-login to check if the user is an anonymous user. Since it's disabled, it's always going to return False
        :return: False
        """
        return False

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

    class Exists(Exception):
        """
        This exception is raised when the user already exists in the DB and something tries to insert it into the DB as new user
        """
