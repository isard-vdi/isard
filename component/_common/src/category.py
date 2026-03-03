#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Simó Albert i Beltran
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

from rethinkdb import r

from .rethink_custom_base_factory import RethinkCustomBase


class Category(RethinkCustomBase):
    """
    Manage Category Objects

    Use constructor with keyword arguments to create new Category Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Category Object.
    """

    _rdb_table = "categories"

    def __setattr__(self, name, value):
        """
        Set an attribute on the Category object.

        When setting the 'portal' attribute, validates that the domain
        is not already in use by another category.

        :param name: The attribute name to set.
        :type name: str
        :param value: The value to set.
        :type value: any
        :raises ValueError: If the portal domain is already in use by another category.
        """
        if name == "portal" and value:
            domain = value.get("domain")
            if domain:
                with self._rdb_context():
                    existing = list(
                        r.table("categories")
                        .filter(
                            lambda cat: (cat["portal"]["domain"] == domain)
                            & (cat["id"] != self.id)
                        )
                        .run(self._rdb_connection)
                    )
                if existing:
                    raise ValueError(f"Portal domain {domain} is already in use")
        super().__setattr__(name, value)
