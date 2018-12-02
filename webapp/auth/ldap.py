#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import ldap

from ..models.config import Config

# from ..lib.log import *


# TODO: Add test coverage
# TODO: Refactor code with better exception handling
def check(user, password):
    """
    check checks if the password provided as a parameter is the correct password for the user using LDAP
    :param user: user is the whole models.user.User class instance
    :param password: password is the password that the user has introduced
    :return: auth returns True if the authentication has succeeded and False if it hasn't
    """
    cfg = Config()
    cfg.get()

    if cfg.auth["ldap"]["active"]:
        try:
            conn = ldap.initialize(cfg.auth["ldap"]["ldap_server"])
            id_conn = conn.search(
                cfg.auth["ldap"]["bind_dn"], ldap.SCOPE_SUBTREE, "uid=" + user.id
            )

            tmp, info = conn.result(id_conn, 0)
            user_dn = info[0][0]

            if conn.simple_bind_s(who=user_dn, cred=password):
                return True

            return False

        except ldap.LDAPError as e:
            # log.error("LDAP ERROR: " + str(e))
            print("LDAP ERROR: " + str(e))
            return False

    raise Disabled


class Disabled(Exception):
    """
    Disabled is the exception that is raised when the ldap authentication is disabled
    """

    pass
