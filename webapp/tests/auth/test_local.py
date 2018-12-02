#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

from ...auth.local import check, Disabled
from ...models.user import User

from ..mocks.rethink import *


class TestLocal:
    """
    This class is the responsible for testing the check function
    """

    @staticmethod
    def test_should_work_as_expected(create_users):
        user = User(generated_users[0])

        assert check(user, "P4$$w0rd! ")

    @staticmethod
    def test_wrong_password(create_users):
        user = User(generated_users[0])

        assert not check(user, "n0p3!")

    @staticmethod
    def test_disabled(create_config):
        r.table("config").get(1).update({"auth": {"local": {"active": False}}}).run(
            create_config
        )

        with pytest.raises(Disabled):
            check(None, "")
