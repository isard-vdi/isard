#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

from ...auth.auth import initialize_kinds

from ..mocks.rethink import *


class TestInitializeKinds:
    """
    This class is the responsible of testing the initialize_kinds function
    """

    @staticmethod
    def test_should_work_as_expected_default(create_config):
        assert len(initialize_kinds().items()) == 1

    @staticmethod
    def test_shoud_work_as_expected_ldap_enabled(create_config):
        r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
            create_config
        )

        assert len(initialize_kinds().items()) == 2
