#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import rethinkdb as r

from ..lib.db import DB


# TODO: DB migration to add permissions
class Role:
    """
    Role is the class that contains all the actions related with the roles
    """

    def __init__(self, role=None):
        self.conn = DB().conn

        if role is None:
            role = {
                "id": "",
                "name": "",
                "description": "",
                "permissions": [
                    {
                        # id is the same value as the parameter in url_to()
                        "id": "media",
                        "view": False,
                        "edit": False,
                    }
                ],
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

        self.id = role["id"]
        self.name = role["name"]
        self.description = role["description"]
        self.permissions = role["permissions"]
        self.quota = role["quota"]

    def get(self, role_id):
        """
        get retrieves a role from the DB using their id. If the role isn't found, it throws an exception
        :param role_id: username is the username of the user
        """
        role = r.table("roles").get(role_id).run(self.conn)

        if role is None:
            raise self.NotFound()

        self.id = role["id"]
        self.name = role["name"]
        self.description = role["description"]
        self.permissions = role["permissions"]
        self.quota = role["quota"]

    def create(self):
        """
        create inserts the role to the DB
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        try:
            self.get(self.id)

        except self.NotFound:
            r.table("roles").insert(
                {
                    "id": self.id,
                    "name": self.name,
                    "description": self.description,
                    "permissions": self.permissions,
                    "quota": self.quota,
                }
            ).run(self.conn)

        else:
            raise self.Exists

    class NotFound(Exception):
        """
        This exception is raised when the role isn't found in the DB
        """

        pass

    class NotLoaded(Exception):
        """
        This exception is raised when a method needs to work with the role but this is empty (not loaded). If you are
        encountering this error, you should init the Role class with a dict containing the user information or call
        Role.get
        """

        pass

    class Exists(Exception):
        """
        This exception is raised when the role already exists in the DB and something tries to insert it into the DB as new role
        """
