#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import rethinkdb as r

from ..lib.db import DB
from .group import Group


# TODO: DB migration
class Category:
    """
    Category is the class that contains all the actions related with the categories
    """

    def __init__(self, category=None):
        self.conn = DB().conn

        if category is None:
            category = {
                "id": "",
                "name": "",
                "description": "",
                "kind": "",
                "role": None,
                "quota": None,
            }

        self.id = category["id"]
        self.name = category["name"]
        self.description = category["description"]
        self.kind = category["kind"]
        self.role = category["role"]
        self.quota = category["quota"]

    def get(self, category_id):
        """
        get retrieves a category from the DB using their id. If the category isn't found, it throws an exception
        :param category_id: username is the username of the user
        """
        category = r.table("categories").get(category_id).run(self.conn)

        if category is None:
            raise self.NotFound()

        self.id = category["id"]
        self.name = category["name"]
        self.description = category["description"]
        self.kind = category["kind"]
        self.role = category["role"]
        self.quota = category["quota"]


    def get_quota(self):
        """
        get_quota returns the correct quota of the category. If the category quota is None, it calls the group mehtod (User -> *Category* -> Group -> Role ["user" by default])
        :return: returns a dict with the quota
        """
        if self.quota:
            return self.quota

        try:
            group = Group()
            group.get(self.group)

        except Group.NotFound:
            return {
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

        return group.get_quota()

    def create(self):
        """
        create inserts the category to the DB
        """
        if self.id == "" or self.id is None:
            raise self.NotLoaded

        try:
            self.get(self.id)

        except self.NotFound:
            r.table("categories").insert(
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
        This exception is raised when the category isn't found in the DB
        """

        pass

    class NotLoaded(Exception):
        """
        This exception is raised when a method needs to work with the category but this is empty (not loaded). If you are
        encountering this error, you should init the Category class with a dict containing the user information or call
        Category.get
        """

        pass

    class Exists(Exception):
        """
        This exception is raised when the category already exists in the DB and something tries to insert it into the DB as new category
        """
