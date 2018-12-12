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

    # TODO: Better assertions
    @staticmethod
    def test_should_work_as_expected(create_users_and_domains):
        for user in generated_users:
            assert isard.get_user_quotas(user["id"]) == {
                "d": 1,
                "dq": 0,
                "dqp": "100.00",
                "r": 0,
                "rq": 0,
                "rqp": "100.00",
                "t": 0,
                "tq": 0,
                "tqp": "100.00",
                "i": 0,
                "iq": 0,
                "iqp": "100.00",
            }

    @staticmethod
    def test_user_not_found(create_config):
        assert isard.get_user_quotas("nefix") == {}
