#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

from ...auth.ldap import LDAP
from ...auth.exceptions import Disabled
from ...models.user import User

from ..mocks.rethink import *
from ..mocks.ldap import *


class TestLDAP:
    """
    This is the class for testing the LDAP class
    """

    class TestConnect:
        """
        This class is the responsible for testing the connect function
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

            ldap = LDAP()
            assert ldap.connect()

    class TestCheck:
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

            ldap = LDAP()
            assert ldap.check(user, "Secret123")

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

            ldap = LDAP()
            assert not ldap.check(user, "n0p3!")

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

            ldap = LDAP()
            assert not ldap.check(user, "Secret123")

        @staticmethod
        def test_disabled(create_config):
            with pytest.raises(Disabled):
                ldap = LDAP()
                ldap.check(None, "")

    class TestGetUser:
        """
        This class is the responsible for testing the get_user function
        """

        @staticmethod
        def test_should_work_as_expected(create_roles, ldap_create_everything):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_roles
            )

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            # TODO: Improve this assert
            assert ldap.get_user("nefix")

        @staticmethod
        def test_non_existing(create_config, ldap_create_everything):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            assert ldap.get_user("nefixestrada") is None

        @staticmethod
        def test_disabled(create_config):
            with pytest.raises(Disabled):
                ldap = LDAP()
                ldap.get_user("")

    class TestGetCategory:
        """
        This class is the responsible for testing the get_category function
        """

        @staticmethod
        def test_should_work_as_expected(create_roles, ldap_create_everything):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_roles
            )

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            # TODO: Improve this assert
            assert ldap.get_category("employees")

        @staticmethod
        def test_not_found(create_config, ldap_create_everything):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            assert ldap.get_category("managers") is None

        @staticmethod
        def test_not_selected(create_config, ldap_create_everything):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            assert ldap.get_category("users") is None

        @staticmethod
        def test_disabled(create_config):
            ldap = LDAP()

            with pytest.raises(Disabled):
                ldap.get_category("")

    class TestSetCategory:
        """
        This class is the responsible for testing the set_category function
        """

        @staticmethod
        def test_should_work_as_expected(create_roles, ldap_create_everything):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_roles
            )

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            assert (
                ldap.set_category("cn=nefix,ou=users,ou=employees,dc=domain,dc=com")
                == "employees"
            )

        @staticmethod
        def test_default_cateogory(create_config, ldap_create_everything):

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            assert ldap.set_category("cn=nefix,dc=domain,dc=com") == "default_ldap"

    class TestGetGroup:
        """
        This class is the responsible for testing the get_group function
        """

        @staticmethod
        def test_should_work_as_expected(create_roles, ldap_create_everything):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_roles
            )

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            # TODO: Improve this assert
            assert ldap.get_group("group1")

        @staticmethod
        def test_not_found(create_config, ldap_create_everything):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            assert ldap.get_group("gods") is None

        @staticmethod
        def test_not_selected(create_config, ldap_create_everything):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            assert ldap.get_group("group2") is None

        @staticmethod
        def test_disabled(create_config):
            ldap = LDAP()

            with pytest.raises(Disabled):
                ldap.get_group("")

    class TestSetGroup:
        """
        This class is the responsible for testing the set_group function
        """

        @staticmethod
        def test_should_work_as_expected(create_roles, ldap_create_everything):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_roles
            )

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            assert ldap.set_group("nefix") == "group1"

        @staticmethod
        def test_default_cateogory(create_config, ldap_create_everything):

            ldap = LDAP()
            ldap.conn = ldap_create_everything

            assert ldap.set_group("individual") == "default_ldap"
