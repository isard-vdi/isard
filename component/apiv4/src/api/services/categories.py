#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Optional

from api.services.error import Error
from isardvdi_common.lib.users.categories.categories import (
    CategoriesProcessed as CommonCategories,
)


class CategoryService:

    @staticmethod
    def get_categories_frontend(domain: Optional[str] = None) -> list[dict]:
        """
        Get all categories for frontend usage.
        """
        return CommonCategories.get_categories_frontend(domain=domain)

    @staticmethod
    def get_category_by_custom_url(
        custom_url: str, domain: Optional[str] = None
    ) -> dict:
        """
        Get a category by its custom URL.
        """
        category = CommonCategories.get_by_custom_url(custom_url, domain=domain)
        if not category:
            raise Error(
                "not_found",
                f"Category with custom URL '{custom_url}' not found.",
                description_code="not_found",
            )
        return category

    @staticmethod
    def get_category_custom_login_url(category_id: str) -> str:
        """
        Get the custom login URL for a category by its ID.
        """
        return CommonCategories.get_custom_login_url(category_id) or "/login"

    @staticmethod
    def search_users_in_category(category_id: str, search: str) -> list[dict]:
        """
        Get all users in a specific category.
        """
        return CommonCategories.search_users_in_category(category_id, search)
