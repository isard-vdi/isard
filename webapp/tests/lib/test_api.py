#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

from ...lib.api import isard

from ..mocks.rethink import *


class TestGetUserQuotas:
    """
    This is the class responsible of testing the get_user_quotas method
    """

    @staticmethod
    def test_should_work_as_expected(create_users):
        for user in generated_users:
            print(isard.get_user_quotas(user["id"]))
            assert False

    @staticmethod
    def test_fake_quota(create_users):
        for user in generated_users:
            print(isard.get_user_quotas(user["id"], True))
            assert False
