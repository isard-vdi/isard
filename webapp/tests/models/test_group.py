#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3
from ...models.group import Group

from ..mocks.rethink import *


class TestGroup:
    """
    This is the class for testing the Group class
    """

    class TestInit:
        """
        This class is the responsible for testing the __init__ function
        """

        @staticmethod
        def test_should_work_as_expected():
            for generated_group in generated_groups:
                group = Group(generated_group)

                for k, v in generated_group.items():
                    assert getattr(group, k) == v

        @staticmethod
        def test_empty_group():
            group = Group()

            for k, v in empty_group.items():
                assert getattr(group, k) == v

    class TestGet:
        """
        This class is the responsible for testing the get function
        """

        @staticmethod
        def test_should_work_as_expected(create_groups):
            for generated_group in generated_groups:
                group = Group()
                group.conn = create_groups

                group.get(generated_group["id"])

                for k, v in generated_group.items():
                    assert getattr(group, k) == v

        @staticmethod
        def test_group_not_found(create_tables):
            for generated_group in generated_groups:
                group = Group()
                group.conn = create_tables

                with pytest.raises(Group.NotFound):
                    group.get(generated_group["id"])

    class TestGetQuota:
        """
        This class is the responsible for testing the get_quota method
        """

        @staticmethod
        def test_should_work_as_expected(create_categories):
            r.table("categories").get("admin").update({"role": "admin"}).run(
                create_categories
            )

            for generated_group in generated_groups:
                group_dict = generated_group.copy()
                group_dict["category"] = "admin"

                group = Group(group_dict)
                group.get_quota()

                assert (
                    group.quota
                    == [
                        role["quota"]
                        for role in generated_roles
                        if role["id"] == "admin"
                    ][0]
                )

        @staticmethod
        def test_no_category(create_categories):
            for generated_group in generated_groups:
                group_dict = generated_group.copy()
                group_dict["category"] = None

                group = Group(group_dict)
                group.get_quota()

                assert group.quota == {
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
        def test_category_not_fould(create_config):
            for generated_group in generated_groups:
                group = Group(generated_group)
                group.get_quota()

                assert group.quota == {
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
            for generated_group in generated_groups:
                group_dict = generated_group.copy()
                group_dict["quota"] = {
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

                group = Group(group_dict)
                group.get_quota()

                assert group.quota == group_dict["quota"]

    class TestCreate:
        """
        This class is the responsible for testing the create function
        """

        @staticmethod
        def test_should_work_as_expected(create_tables):
            for generated_group in generated_groups:
                group = Group(
                    {
                        "id": generated_group["id"],
                        "name": generated_group["name"],
                        "description": generated_group["description"],
                        "kind": generated_group["kind"],
                        "category": generated_group["category"],
                        "role": generated_group["role"],
                        "quota": generated_group["quota"],
                    }
                )

                group.create()

                group = Group()
                group.get(generated_group["id"])

                for k, v in generated_group.items():
                    assert getattr(group, k) == v

        @staticmethod
        def test_not_loaded():
            group = Group()

            with pytest.raises(Group.NotLoaded):
                group.create()

        @staticmethod
        def test_already_exists(create_groups):
            for generated_group in generated_groups:
                group = Group()
                group.get(generated_group["id"])

                with pytest.raises(Group.Exists):
                    group.create()
