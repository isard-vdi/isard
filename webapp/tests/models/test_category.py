#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3
from ...models.category import Category

from ..mocks.rethink import *


class TestCategory:
    """
    This is the class for testing the Category class
    """

    class TestInit:
        """
        This class is the responsible for testing the __init__ function
        """

        @staticmethod
        def test_should_work_as_expected():
            for generated_category in generated_categories:
                category = Category(generated_category)

                for k, v in generated_category.items():
                    assert getattr(category, k) == v

        @staticmethod
        def test_empty_category():
            category = Category()

            for k, v in empty_category.items():
                assert getattr(category, k) == v

    class TestGet:
        """
        This class is the responsible for testing the get function
        """

        @staticmethod
        def test_should_work_as_expected(create_categories):
            for generated_category in generated_categories:
                category = Category()
                category.conn = create_categories

                category.get(generated_category["id"])

                for k, v in generated_category.items():
                    assert getattr(category, k) == v

        @staticmethod
        def test_category_not_found(create_tables):
            for generated_category in generated_categories:
                category = Category()
                category.conn = create_tables

                with pytest.raises(Category.NotFound):
                    category.get(generated_category["id"])

    class TestCreate:
        """
        This class is the responsible for testing the create function
        """

        @staticmethod
        def test_should_work_as_expected(create_tables):
            for generated_category in generated_categories:
                category = Category(
                    {
                        "id": generated_category["id"],
                        "name": generated_category["name"],
                        "description": generated_category["description"],
                        "kind": generated_category["kind"],
                        "role": generated_category["role"],
                        "quota": generated_category["quota"],
                    }
                )

                category.create()

                category = Category()
                category.get(generated_category["id"])

                for k, v in generated_category.items():
                    assert getattr(category, k) == v

        @staticmethod
        def test_not_loaded():
            category = Category()

            with pytest.raises(Category.NotLoaded):
                category.create()

        @staticmethod
        def test_already_exists(create_categories):
            for generated_category in generated_categories:
                category = Category()
                category.get(generated_category["id"])

                with pytest.raises(Category.Exists):
                    category.create()
