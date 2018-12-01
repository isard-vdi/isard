#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3
from ...models.user import User

from ..mocks.rethink import *


class TestUser:
    """
    This is the class for testing the User class
    """

    def test_init(self):
        """
        __init__ should work as expected
        """
        generated_user = User(users[0])

        for k, v in users[0].items():
            assert getattr(generated_user, k) == v

    def test_get_found(self, create_users):
        """
        get should work as expected
        """
        generated_user = User(None)
        generated_user.get("nefix", create_users)

        for k, v in users[0].items():
            assert getattr(generated_user, k) == v

    def test_get_not_found(self, create_tables):
        """
        get should throw a not found error
        """
        generated_user = User(None)

        with pytest.raises(User.NotFound):
            generated_user.get("nefix", create_tables)
