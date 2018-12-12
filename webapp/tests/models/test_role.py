#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3
from ...models.role import Role

from ..mocks.rethink import *


class TestRole:
    """
    This is the class for testing the Role class
    """

    class TestInit:
        """
        This class is the responsible for testing the __init__ function
        """

        @staticmethod
        def test_should_work_as_expected():
            for generated_role in generated_roles:
                role = Role(generated_role)

                for k, v in generated_role.items():
                    assert getattr(role, k) == v

        @staticmethod
        def test_empty_role():
            role = Role()

            for k, v in empty_role.items():
                assert getattr(role, k) == v

    class TestGet:
        """
        This class is the responsible for testing the get function
        """

        @staticmethod
        def test_should_work_as_expected(create_roles):
            for generated_role in generated_roles:
                role = Role()
                role.conn = create_roles

                role.get(generated_role["id"])

                for k, v in generated_role.items():
                    assert getattr(role, k) == v

        @staticmethod
        def test_role_not_found(create_tables):
            for generated_role in generated_roles:
                role = Role()
                role.conn = create_tables

                with pytest.raises(Role.NotFound):
                    role.get(generated_role["id"])

    class TestGetQuota:
        """
        This class is the responsible for testing the get_quota method
        """

        @staticmethod
        def test_should_work_as_expected(create_roles):
            for generated_role in generated_roles:
                role = Role(generated_role)
                role.get_quota()

                assert role.quota == generated_role["quota"]

        @staticmethod
        def test_role_no_quota(create_roles):
            for generated_role in generated_roles:
                role_dict = generated_role.copy()

                if generated_role["id"] != "user":
                    role_dict["quota"] = None

                role = Role(role_dict)
                role.get_quota()

                assert (
                    role.quota
                    == [
                        role["quota"]
                        for role in generated_roles
                        if role["id"] == "user"
                    ][0]
                )

        @staticmethod
        def test_role_user_not_fould(create_config):
            for generated_role in generated_roles:
                role_dict = generated_role.copy()
                role_dict["quota"] = None

                role = Role(role_dict)
                role.get_quota()

                assert role.quota == {
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

    class TestCreate:
        """
        This class is the responsible for testing the create function
        """

        @staticmethod
        def test_should_work_as_expected(create_tables):
            for generated_role in generated_roles:
                role = Role(
                    {
                        "id": generated_role["id"],
                        "name": generated_role["name"],
                        "description": generated_role["description"],
                        "permissions": generated_role["permissions"],
                        "quota": generated_role["quota"],
                    }
                )

                role.create()

                role = Role()
                role.get(generated_role["id"])

                for k, v in generated_role.items():
                    assert getattr(role, k) == v

        @staticmethod
        def test_not_loaded():
            role = Role()

            with pytest.raises(Role.NotLoaded):
                role.create()

        @staticmethod
        def test_already_exists(create_roles):
            for generated_role in generated_roles:
                role = Role()
                role.get(generated_role["id"])

                with pytest.raises(Role.Exists):
                    role.create()
