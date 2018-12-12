#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3
from ...models.user import User

from ..mocks.rethink import *
from ..mocks.ldap import *


class TestUser:
    """
    This is the class for testing the User class
    """

    class TestInit:
        """
        This class is the responsible for testing the __init__ function
        """

        @staticmethod
        def test_should_work_as_expected(create_config):
            user = User(generated_users[0])

            for k, v in generated_users[0].items():
                if k == "accessed":
                    time.gmtime(getattr(user, k))
                else:
                    assert getattr(user, k) == v

        @staticmethod
        def test_empty_user(create_config):
            user = User()

            for k, v in empty_user.items():
                if k == "accessed":
                    time.gmtime(getattr(user, k))
                else:
                    assert getattr(user, k) == v

    class TestGet:
        """
        This class is the responsible for testing the get function
        """

        @staticmethod
        def test_should_work_as_expected(create_users):
            user = User()
            user.conn = create_users

            user.get("nefix")

            for k, v in generated_users[0].items():
                assert getattr(user, k) == v

        @staticmethod
        def test_user_not_found(create_config):
            user = User()
            user.conn = create_config

            with pytest.raises(User.NotFound):
                user.get("nefix")

    class TestGetQuota:
        """
        This class is the responsible for testing the get_quota method
        """

        @staticmethod
        def test_should_work_as_expected(create_groups):
            r.table("groups").get("advanced").update({"category": "admin"}).run(
                create_groups
            )
            r.table("categories").get("admin").update({"role": "admin"}).run(
                create_groups
            )

            for generated_user in generated_users:
                user_dict = generated_user.copy()
                user_dict["group"] = "advanced"

                user = User(user_dict)
                user.get_quota()

                assert (
                    user.quota
                    == [
                        role["quota"]
                        for role in generated_roles
                        if role["id"] == "admin"
                    ][0]
                )

        @staticmethod
        def test_no_group(create_groups):
            for generated_user in generated_users:
                user_dict = generated_user.copy()
                user_dict["group"] = None

                user = User(user_dict)
                user.get_quota()

                assert user.quota == {
                    "domains": {
                        "desktops": 0,
                        "desktops_disk_max": 0,
                        "templates": 0,
                        "templates_disk_max": 0,
                        "running": 0,
                        "isos": 0,
                        "isos_disk_max": 0,
                    },
                    "hardware": {"vcpus": 0, "memory": 0},
                }

        @staticmethod
        def test_group_not_fould(create_config):
            for generated_user in generated_users:
                user = User(generated_user)
                user.get_quota()

                assert user.quota == {
                    "domains": {
                        "desktops": 0,
                        "desktops_disk_max": 0,
                        "templates": 0,
                        "templates_disk_max": 0,
                        "running": 0,
                        "isos": 0,
                        "isos_disk_max": 0,
                    },
                    "hardware": {"vcpus": 0, "memory": 0},
                }

        @staticmethod
        def test_existing_quota():
            for generated_user in generated_users:
                user_dict = generated_user.copy()
                user_dict["quota"] = {
                    "domains": {
                        "desktops": 5,
                        "desktops_disk_max": 999999999,
                        "templates": 5,
                        "templates_disk_max": 999999999,
                        "running": 2,
                        "isos": 0,
                        "isos_disk_max": 999999999,
                    },
                    "hardware": {"vcpus": 4, "memory": 10000000},
                }

                user = User(user_dict)
                user.get_quota()

                assert user.quota == user_dict["quota"]

    class TestGetDesktops:
        """
        This class is the responsible of testing the get_desktops method
        """

        @staticmethod
        def test_should_work_as_expected(create_users_and_domains):
            for generated_user in generated_users:
                user = User(generated_user)

                assert user.get_desktops() == [
                    desktop
                    for desktop in generated_domains
                    if desktop["kind"] == "desktop" and desktop["user"] == user.id
                ]

        @staticmethod
        def test_user_not_loaded():
            user = User()

            with pytest.raises(User.NotLoaded):
                user.get_desktops()

    class TestGetStartedDesktops:
        """
        This class is the responsible of testing the get_started_desktops method
        """

        @staticmethod
        def test_should_work_as_expected(create_users_and_domains):
            for generated_user in generated_users:
                user = User(generated_user)

                assert user.get_started_desktops() == [
                    desktop
                    for desktop in generated_domains
                    if desktop["kind"] == "desktop"
                    and desktop["user"] == user.id
                    and desktop["status"] == "Started"
                ]

        @staticmethod
        def test_user_not_loaded():
            user = User()

            with pytest.raises(User.NotLoaded):
                user.get_started_desktops()

    class TestGetTemplates:
        """
        This class is the responsible of testing the get_templates method
        """

        @staticmethod
        def test_should_work_as_expected(create_users_and_domains):
            for generated_user in generated_users:
                user = User(generated_user)

                assert user.get_templates() == [
                    template
                    for template in generated_domains
                    if template["kind"] == "user_template"
                    and template["user"] == user.id
                ]

        @staticmethod
        def test_user_not_loaded():
            user = User()

            with pytest.raises(User.NotLoaded):
                user.get_templates()

    class TestGetMedia:
        """
        This class is the responsible of testing the get_media method
        """

        @staticmethod
        def test_should_work_as_expected(create_users_and_media):
            for generated_user in generated_users:
                user = User(generated_user)

                assert user.get_media() == [
                    media for media in generated_media if media["user"] == user.id
                ]

        @staticmethod
        def test_user_not_loaded():
            user = User()

            with pytest.raises(User.NotLoaded):
                user.get_media()

    class TestAuth:
        """
        This class is the responsible for testing the auth function
        """

        @staticmethod
        def test_user_not_loaded(create_config):
            user = User()

            with pytest.raises(User.NotLoaded):
                user.auth("P4$$w0rd! ")

        @staticmethod
        def test_admin(create_admin):
            user = User()
            user.conn = create_admin
            user.get("admin")

            assert user.auth("P4$$w0rd! ")

        @staticmethod
        def test_disabled(create_users):
            user = User(generated_users[0])
            user.active = False

            assert not user.auth("P4$$w0rd! ")

        @staticmethod
        def test_local(create_users):
            user = User(generated_users[0])

            assert user.auth("P4$$w0rd! ")

        @staticmethod
        def test_ldap(create_config):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_config
            )

            for ldap_user in ldap_users:
                user = User(ldap_user)
                assert user.auth(ldap_user["password"])

        @staticmethod
        def test_unsupported_auth_method():
            user = User(generated_users[0])
            user.kind = "hjkl"

            assert not user.auth("P4$$w0rd! ")

    class TestCreate:
        """
        This class is the responsible for testing the create function
        """

        @staticmethod
        def test_should_work_as_expected(create_config):
            for generated_user in generated_users:
                user = User(generated_user)
                user.create()

                user = User()
                user.get(generated_user["id"])

                for k, v in generated_user.items():
                    if k == "accessed":
                        time.gmtime(getattr(user, k))
                    else:
                        assert getattr(user, k) == v

        @staticmethod
        def test_ldap(create_groups):
            r.table("config").get(1).update({"auth": {"ldap": {"active": True}}}).run(
                create_groups
            )

            for ldap_user in ldap_users:
                user = User(ldap_user)
                user.create()

                user = User()
                user.get(ldap_user["id"])

                user.password = ldap_user["password"]

                for k, v in ldap_user.items():
                    if k == "accessed":
                        time.gmtime(getattr(user, k))
                    else:
                        assert getattr(user, k) == v

                db_category = (
                    r.table("categories").get(ldap_user["category"]).run(create_groups)
                )
                db_group = r.table("groups").get(ldap_user["group"]).run(create_groups)

                assert (
                    db_category in ldap_categories
                    or db_category == ldap_default_category
                )
                assert db_group in ldap_groups or db_group == ldap_default_group

        @staticmethod
        def test_not_loaded(create_config):
            user = User()

            with pytest.raises(User.NotLoaded):
                user.create()

        @staticmethod
        def test_already_exists(create_users):
            for generated_user in generated_users:
                user = User()
                user.get(generated_user["id"])

                with pytest.raises(User.Exists):
                    user.create()

    class TestUpdateAccess:
        """
        This class is the responsible for testing the update_access function
        """

        @staticmethod
        def test_should_work_as_expected(create_users):
            user = User(generated_users[0])
            user.conn = create_users

            rsp = user.update_access()
            assert rsp["replaced"] == 1

            time.gmtime(r.table("users").get(user.id).run(create_users)["accessed"])

        @staticmethod
        def test_user_not_loaded(create_config):
            user = User()

            with pytest.raises(User.NotLoaded):
                user.update_access()

        @staticmethod
        def test_user_not_found(create_config):
            user = User(generated_users[0])
            user.conn = create_config

            with pytest.raises(User.NotFound):
                user.update_access()

    class TestIsActive:
        """
        This class is the responsible for testing the is_active function (used by flask-login)
        """

        @staticmethod
        def test_should_work_as_expected_active(create_config):
            user = User(generated_users[0])

            assert user.is_active()

        @staticmethod
        def test_should_work_as_expected_non_active(create_config):
            user = User(generated_users[0])
            user.active = False

            assert not user.is_active()

        @staticmethod
        def test_user_not_loaded(create_config):
            user = User()

            with pytest.raises(User.NotLoaded):
                user.is_active()

    class TestIsAnonymous:
        """
        This class is the responsible for testing the is_anonymous function (used by flask-login)
        """

        @staticmethod
        def test_should_work_as_expected(create_config):
            user = User(generated_users[0])

            assert not user.is_anonymous()
