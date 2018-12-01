#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import rethinkdb as r


class User:
    """
    User is the class that contains all the actions related with the users
    """

    def __init__(self, user):
        if user is None:
            user = {
                "id": "",
                "name": "",
                "password": "",
                "role": "",
                "category": "",
                "group": "",
                "mail": "",
                "quota": None,
                "active": False,
            }

        self.id = user["id"]
        self.username = user["id"]
        self.name = user["name"]
        self.password = user["password"]
        self.role = user["role"]
        self.category = user["category"]
        self.group = user["group"]
        self.path = user["category"] + "/" + user["group"] + "/" + user["id"] + "/"
        self.mail = user["mail"]
        self.quota = user["quota"]
        self.is_admin = True if self.role == "admin" else False
        self.active = user["active"]

    def get(self, username, conn):
        """
        get retrieves an user from the DB using their username. If the user isn't found or is any error, it throws an
        exception
        :param username: username is the username of the user
        :param conn: conn is the connection with the RethinkDB database
        """
        user = r.table("users").get(username).run(conn)
        print(user)

        if user is None:
            raise self.NotFound()

        self.id = user["id"]
        self.username = user["id"]
        self.name = user["name"]
        self.password = user["password"]
        self.role = user["role"]
        self.category = user["category"]
        self.group = user["group"]
        self.path = user["category"] + "/" + user["group"] + "/" + user["id"] + "/"
        self.mail = user["mail"]
        self.quota = user["quota"]
        self.is_admin = True if self.role == "admin" else False
        self.active = user["active"]

    class NotFound(Exception):
        """
        This exception is raised when the user isn't found in the DB
        """

        pass
