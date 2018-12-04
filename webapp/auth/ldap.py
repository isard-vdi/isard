#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

from ldap3 import Connection, core

from .exceptions import Disabled
from ..models.config import Config

from ..lib.log import *


# TODO: Add security (TLS, SSL, SASL...)
class LDAP:
    """
    LDAP is the class that contains all the actions related with LDAP
    """

    def __init__(self):
        self.cfg = Config()
        self.cfg.get()

        self.conn = None

    def connect(self):
        """
        Conn creates a new connection with the LDAP server
        """
        self.conn = Connection(
            self.cfg.auth["ldap"]["ldap_server"],
            self.cfg.auth["ldap"]["query_password"],
            self.cfg.auth["ldap"]["query_password"],
            auto_bind=True,
        )

        return True if self.conn else False

    def check(self, user, password):
        """
        check checks if the password provided as a parameter is the correct password for the user using LDAP
        :param user: user is the whole models.user.User class instance
        :param password: password is the password that the user has introduced
        :return: auth returns True if the authentication has succeeded and False if it hasn't
        """
        if self.cfg.auth["ldap"]["active"]:
            dn = "uid=" + user.id + "," + self.cfg.auth["ldap"]["bind_dn"]

            try:
                Connection(
                    self.cfg.auth["ldap"]["ldap_server"], dn, password, auto_bind=True
                )
                return True

            except core.exceptions.LDAPExceptionError as e:
                # Check that the exception isn't an invalidCredentials exception
                if (not isinstance(e, core.exceptions.LDAPBindError)) or (
                    len(str(e).split(" - ")) > 1
                    and str(e).split(" - ")[1] != "invalidCredentials"
                ):
                    log.error("LDAP ERROR: " + str(e))

                return False

        raise Disabled

    def get_user(self, user_id, role=None, quota=None):
        """
        get_user queries the LDAP server and creates a User.__init__ dict using the values gotten from it
        :param user_id: user_id is the ID of the user
        :param role: role is the role of the user. By default gets the quota of their parent (group)
        :param quota: quota is the quota of the user. By default gets the quota of their parent (group)
        :return: get_user returns a dictionary compatible with the User.__init__ function (the return is the parameter used when calling the __init__ method)
        """
        if self.cfg.auth["ldap"]["active"]:
            search_query = f"(&(objectclass=person)(uid={user_id}))"

            self.conn.search(
                self.cfg.auth["ldap"]["bind_dn"],
                search_query,
                attributes=["displayName", "mail"],
            )

            if not self.conn.entries:
                # TODO: User not found
                return None

            ldap_user = self.conn.entries[0]

            name = user_id.title()
            mail = None

            if ldap_user["displayName"]:
                name = ldap_user["displayName"].values[0]

            if ldap_user["mail"]:
                mail = ldap_user["mail"].values[0]

            user = {
                "id": user_id,
                "password": None,
                "kind": "ldap",
                "name": name,
                "mail": mail,
                "role": role,
                "category": self.set_category(self.conn.response[0]["dn"]),
                "group": self.set_group(user_id),
                "active": True,
                "accessed": 0,
                "quota": quota,
            }

            return user

        raise Disabled

    def get_category(self, category_id, role=None, quota=None):
        """
        get_category queries the LDAP server and creates a Category.__init__ dict using the values gotten from it
        :param category_id: category_id is the ID of the category
        :param role: role is the role of the category. By default it's "user"
        :param quota: quota is the quota of the category. By default gets the quota of their parent (role)
        :return: get_category returns a dictionary compatible with the Category.__init__ function (the return is the parameter used when calling the __init__ method)
        """
        if self.cfg.auth["ldap"]["active"]:
            search_query = f"(&(objectclass=*)({self.cfg.auth['ldap']['category_attribute']}={category_id}))"

            self.conn.search(
                self.cfg.auth["ldap"]["bind_dn"],
                search_query,
                attributes=["description"],
            )

            if not self.conn.entries:
                # TODO: Category not found
                return None

            if category_id not in self.cfg.auth["ldap"]["selected_categories"]:
                # TODO: Category not found in selected
                return None

            description = None

            if self.conn.entries[0]["description"]:
                description = self.conn.entries[0]["description"].values[0]

            category = {
                "id": category_id,
                "name": category_id.title(),
                "description": description,
                "kind": "ldap",
                "role": role,
                "quota": quota,
            }

            return category

        raise Disabled

    def set_category(self, dn):
        """
        set_category returns the category ID that the new LDAP users are going to use when being created in the DB
        :param dn: dn is the whole DN of the user
        :return: returns the ID of the category
        """
        for item in reversed(dn.split(",")):
            if item.split("=")[0] == self.cfg.auth["ldap"]["category_attribute"]:
                category = item.split("=")[1]

                if self.get_category(category):
                    return category

        return "default_ldap"

    def get_group(self, group_id, role=None, quota=None):
        """
        get_group queries the LDAP server and creates a Group.__init__ dict using the values gotten from it
        :param group_id: is the ID of the group
        :param role: role is the role of the group. By default gets the quota from their parent (category)
        :param quota: quota is the quota of the group. By default gets the quota of their parent (category)
        :return: get_group returns a dictionary compatible with the Group.__init__ function (the return is the parameter used when calling the __init__ method)
        """
        if self.cfg.auth["ldap"]["active"]:
            search_query = f"(&(objectclass={self.cfg.auth['ldap']['group_objectclass']})(cn={group_id}))"

            self.conn.search(
                self.cfg.auth["ldap"]["bind_dn"],
                search_query,
                attributes=[self.cfg.auth["ldap"]["group_objectclass"], "description"],
            )

            if not self.conn.entries:
                # TODO: Category not found
                return None

            if group_id not in self.cfg.auth["ldap"]["selected_groups"]:
                # TODO: Group not found in selected
                return None

            description = None

            if self.conn.entries[0]["description"]:
                description = self.conn.entries[0]["description"].values[0]

            group = {
                "id": group_id,
                "name": group_id.title(),
                "description": description,
                "kind": "ldap",
                "role": role,
                "quota": quota,
            }

            return group

        raise Disabled

    def set_group(self, user_id):
        """
        set_group returns the group ID that the new LDAP users are going to use when being created in the DB
        :param user_id: user_id is the ID of the user
        :return: returns the ID of the group
        """
        search_query = f"(&(objectclass={self.cfg.auth['ldap']['group_objectclass']})({self.cfg.auth['ldap']['group_attribute']}={user_id}))"

        self.conn.search(
            self.cfg.auth["ldap"]["bind_dn"], search_query, attributes=["cn"]
        )

        if self.conn.entries:

            # Get the group that is more important in the LDAP DN tree
            shortest_group = None
            shortest_group_len = 0
            for group in self.conn.entries:
                # When you read an entry of the response, it deletes it from the array. Because of that, the current entry is always going to be at the position 0
                current_group_len = len(self.conn.response[0]["dn"].split(","))

                if current_group_len > shortest_group_len:
                    if self.get_group(group["cn"].values[0]):
                        shortest_group = group["cn"].values[0]
                        shortest_group_len = current_group_len

            if shortest_group:
                return shortest_group

        return "default_ldap"
