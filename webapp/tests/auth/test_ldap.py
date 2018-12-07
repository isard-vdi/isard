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
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            assert ldap.connect()

    class TestCheck:
        """
        This class is the responsible for testing the check function
        """

        @staticmethod
        def test_should_work_as_expected(create_config):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.connect()

            for ldap_user in ldap_users:
                user = User(ldap_user)
                assert ldap.check(user, user.password)

        @staticmethod
        def test_wrong_password(create_config):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.connect()

            for ldap_user in ldap_users:
                user = User(ldap_user)
                assert not ldap.check(user, "nop3!")

        @staticmethod
        def test_error_connection(create_config):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.connect()

            user = User(None)

            r.table("config").get(1).update(
                {"auth": {"ldap": {"ldap_server": "ldap.ihopethisdomain.neverexists"}}}
            ).run(create_config)

            ldap.cfg.get()

            assert not ldap.check(user, user.password)

        @staticmethod
        def test_disabled(create_config):
            ldap = LDAP()

            user = User(None)

            with pytest.raises(Disabled):
                assert not ldap.check(user, user.password)

    class TestGetUser:
        """
        This class is the responsible for testing the get_user function
        """

        @staticmethod
        def test_should_work_as_expected(create_roles):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_roles
            )

            ldap = LDAP()
            ldap.connect()

            for ldap_user in ldap_users:
                ldap_user["password"] = None
                assert ldap.get_user(ldap_user["id"]) == ldap_user

        @staticmethod
        def test_non_existing(create_config):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.connect()

            assert ldap.get_user("nefix") is None

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
        def test_should_work_as_expected(create_roles):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_roles
            )

            ldap = LDAP()
            ldap.connect()

            for ldap_category in ldap_categories:
                assert ldap.get_category(ldap_category["id"]) == ldap_category

        @staticmethod
        def test_not_found(create_config):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.connect()

            assert ldap.get_category("gods") is None
            assert ldap.get_category("managers") is None

        @staticmethod
        def test_not_selected(create_config):
            r.table("config").get(1).update(
                {"auth": {"ldap": {"active": True, "selected_categories": []}}}
            ).run(create_config)

            ldap = LDAP()
            ldap.connect()

            for ldap_category in ldap_categories:
                assert ldap.get_category(ldap_category["id"]) is None

        @staticmethod
        def test_disabled(create_config):
            with pytest.raises(Disabled):
                ldap = LDAP()
                ldap.get_category("")

    class TestSetCategory:
        """
        This class is the responsible for testing the set_category function
        """

        # TODO: Add more groups
        @staticmethod
        def test_should_work_as_expected(create_roles):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_roles
            )

            ldap = LDAP()
            ldap.connect()

            for ldap_user in ldap_users:
                assert (
                    ldap.set_category(ldap_users_dn[ldap_user["id"]])
                    == ldap_user["category"]
                )

        @staticmethod
        def test_default_cateogory(create_config):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.connect()

            assert (
                ldap.set_category("cn=Néfix Estrada,dc=planetexpress,dc=com")
                == "default_ldap"
            )

    class TestGetGroup:
        """
        This class is the responsible for testing the get_group function
        """

        @staticmethod
        def test_should_work_as_expected(create_roles):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_roles
            )

            ldap = LDAP()
            ldap.connect()

            for ldap_group in ldap_groups:
                assert ldap.get_group(ldap_group["id"]) == ldap_group

        @staticmethod
        def test_not_found(create_config):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            ldap = LDAP()
            ldap.connect()

            assert ldap.get_group("gods") is None
            assert ldap.get_group("managers") is None

        @staticmethod
        def test_not_selected(create_config):
            r.table("config").get(1).update(
                {"auth": {"ldap": {"active": True, "selected_groups": []}}}
            ).run(create_config)

            ldap = LDAP()
            ldap.connect()

            for ldap_group in ldap_groups:
                assert ldap.get_group(ldap_group["id"]) is None

        @staticmethod
        def test_disabled(create_config):
            ldap = LDAP()

            with pytest.raises(Disabled):
                ldap.get_group("")

    class TestSetGroup:
        """
        This class is the responsible for testing the set_group function
        """

        # TODO: Add more categories
        @staticmethod
        def test_should_work_as_expected(create_roles):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_roles
            )

            ldap = LDAP()
            ldap.connect()

            for ldap_user in ldap_users:
                assert (
                    ldap.set_group(ldap_user["id"], ldap_users_dn[ldap_user["id"]])
                    == ldap_user["group"]
                )

        @staticmethod
        def test_default_cateogory(create_config):
            ldap = LDAP()
            ldap.connect()

            assert (
                ldap.set_group(
                    "nefix", "cn=Néfix Estrada,ou=people,dc=planetexpress,dc=com"
                )
                == "default_ldap"
            )
