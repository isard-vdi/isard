#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3


class AuthException(Exception):
    """
    This is the base exception for all the exceptions during authentication
    """

    pass


class Disabled(AuthException):
    """
    Disabled is the exception that is raised when the ldap authentication is disabled
    """

    pass
