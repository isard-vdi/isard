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
