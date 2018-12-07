#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

from ...auth.local import Local
from ...models.user import User

from ..mocks.rethink import *


class TestLocal:
    """
    This class is the responsible for testing the Local class
    """

    class TestConnect:
        """
        This class is the responsible of testing the connect method
        """

        @staticmethod
        def should_work_as_expected(create_config):
            local = Local()

            assert local.connect()

    class TestCheck:
        """
        This class is the responsible for testing the check function
        """

        @staticmethod
        def test_should_work_as_expected(create_users):
            for i, user in enumerate(generated_users):
                user = User(user)
                local = Local()

                assert local.check(user, generated_users_passwords[i])

        @staticmethod
        def test_wrong_password(create_users):
            for user in generated_users:
                user = User(user)
                local = Local()

                assert not local.check(user, "n0p3!")
