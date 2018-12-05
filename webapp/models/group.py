#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import rethinkdb as r

from ..lib.db import DB


# TODO: DB migration
class Group:
    """
    Group is the class that contains all the actions related with the groups
    """

    def __init__(self, group=None):
        self.conn = DB().conn

        if group is None:
            group = {
                "id": "",
                "name": "",
                "description": "",
                "kind": "",
                "role": None,
                "quota": None,
            }

        self.id = group["id"]
        self.name = group["name"]
        self.description = group["description"]
        self.kind = group["kind"]
        self.role = group["role"]
        self.quota = group["quota"]

    def get(self, group_id):
        """
        get retrieves a group from the DB using their id. If the group isn't found, it throws an exception
        :param group_id: username is the username of the user
        """
        group = r.table("groups").get(group_id).run(self.conn)

        if group is None:
            raise self.NotFound()

        self.id = group["id"]
        self.name = group["name"]
        self.description = group["description"]
        self.kind = group["kind"]
        self.role = group["role"]
        self.quota = group["quota"]

    def create(self):
        """
        create inserts the group to the DB
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        try:
            self.get(self.id)

        except self.NotFound:
            r.table("groups").insert(
                {
                    "id": self.id,
                    "name": self.name,
                    "description": self.description,
                    "kind": self.kind,
                    "role": self.role,
                    "quota": self.quota,
                }
            ).run(self.conn)

        else:
            raise self.Exists

    class NotFound(Exception):
        """
        This exception is raised when the group isn't found in the DB
        """

        pass

    class NotLoaded(Exception):
        """
        This exception is raised when a method needs to work with the group but this is empty (not loaded). If you are
        encountering this error, you should init the Group class with a dict containing the user information or call
        Group.get
        """

        pass

    class Exists(Exception):
        """
        This exception is raised when the group already exists in the DB and something tries to insert it into the DB as new group
        """
