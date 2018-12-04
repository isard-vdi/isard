#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3
import bcrypt

from ..models.config import Config


class Local:
    """
    Local is the class that contains all the actions related with the local authentication
    """

    def __init__(self):
        self.cfg = Config()
        self.cfg.get()

    @staticmethod
    def check(user, password):
        """
        check checks if the password provided as a parameter is the correct password for the user
        :param user: user is the whole models.user.User class instance
        :param password: password is the password that the user has introduced
        :return: auth returns True if the authentication has succeeded and False if it hasn't
        """
        return bcrypt.checkpw(password.encode("utf-8"), user.password.encode("utf-8"))
