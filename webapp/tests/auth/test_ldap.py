#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

from ...auth.ldap import check, Disabled
from ...models.user import User

from ..mocks.rethink import *


class TestLdap:
    """
    This class is the responsible for testing the check function
    """

    @staticmethod
    def test_should_work_as_expected(create_config):
        r.table("config").get(1).update(
            {
                "auth": {
                    "ldap": {
                        "active": True,
                        "ldap_server": "ipa.demo1.freeipa.org",
                        "bind_dn": "cn=users,cn=accounts,dc=demo1,dc=freeipa,dc=org",
                    }
                }
            }
        ).run(create_config)

        user = User(generated_users[0])
        user.id = "helpdesk"

        assert check(user, "Secret123")

    @staticmethod
    def test_wrong_password(create_config):
        r.table("config").get(1).update(
            {
                "auth": {
                    "ldap": {
                        "active": True,
                        "ldap_server": "ipa.demo1.freeipa.org",
                        "bind_dn": "cn=users,cn=accounts,dc=demo1,dc=freeipa,dc=org",
                    }
                }
            }
        ).run(create_config)

        user = User(generated_users[0])
        user.id = "helpdesk"

        assert not check(user, "n0p3!")

    @staticmethod
    def test_error_connection(create_config):
        r.table("config").get(1).update(
            {
                "auth": {
                    "ldap": {
                        "active": True,
                        "ldap_server": "ldap.ihopethisdomain.neverexists",
                        "bind_dn": "cn=users,cn=accounts,dc=demo1,dc=freeipa,dc=org",
                    }
                }
            }
        ).run(create_config)

        user = User(generated_users[0])
        user.id = "helpdesk"

        assert not check(user, "Secret123")

    @staticmethod
    def test_disabled(create_config):
        with pytest.raises(Disabled):
            check(None, "")
