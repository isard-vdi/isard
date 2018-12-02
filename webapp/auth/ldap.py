#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

from ldap3 import Connection, core

from .auth import Disabled
from ..models.config import Config

from ..lib.log import *


# TODO: Add security (TLS, SSL, SASL...)
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
        dn = "uid=" + user.id + "," + cfg.auth["ldap"]["bind_dn"]

        try:
            Connection(cfg.auth["ldap"]["ldap_server"], dn, password, auto_bind=True)
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
