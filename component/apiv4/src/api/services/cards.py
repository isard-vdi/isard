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


import traceback
from typing import Optional

from api.services.error import Error
from isardvdi_common.helpers.cards import Cards as CommonCards


class CardService:
    @staticmethod
    def get_stock_cards() -> list[dict]:
        """Get all available stock cards"""
        try:
            return CommonCards.get_stock_cards()
        except Exception as e:
            raise Error(
                "internal_server",
                "Failed to retrieve stock cards",
                traceback.format_exc(),
            )

    @staticmethod
    def get_user_cards(user_id: str, domain_id: Optional[str] = None) -> list[dict]:
        """Get user cards for a specific user and optionally a domain"""
        try:
            return CommonCards.get_user_cards(user_id, domain_id)
        except Exception as e:
            raise Error(
                "internal_server",
                "Failed to retrieve user cards",
                traceback.format_exc(),
            )

    @staticmethod
    def get_card(card_id: str, card_type: str) -> dict:
        """Build a card from its id and type.

        The url is derived data: clients send `{id, type}` and the request
        models fill `url` with None, so recompute it before storing.
        """
        try:
            return CommonCards.get_card(card_id, card_type)
        except Exception:
            raise Error(
                "internal_server",
                "Failed to build card",
                traceback.format_exc(),
            )

    @staticmethod
    def get_domain_stock_card(domain_id: str) -> dict:
        """Get the default stock card for a domain"""
        try:
            return CommonCards.get_domain_stock_card(domain_id)
        except Exception as e:
            raise Error(
                "internal_server",
                "Failed to retrieve domain stock card",
                traceback.format_exc(),
            )

    @staticmethod
    def get_domain_user_card(domain_id: str) -> dict:
        """Get the default user card for a domain"""
        try:
            return CommonCards.get_domain_user_card(domain_id)
        except Exception as e:
            raise Error(
                "not_found",
                "Domain not found or failed to generate user card",
                traceback.format_exc(),
            )

    @staticmethod
    def generate_default_card(domain_id: str, domain_name: str) -> dict:
        """Generate a default card for a domain with custom name"""
        try:
            return CommonCards.generate_default_card(domain_id, domain_name)
        except Exception as e:
            raise Error(
                "internal_server",
                "Failed to generate default card",
                traceback.format_exc(),
            )

    @staticmethod
    def upload_card(domain_id: str, image_data: dict) -> dict:
        """Upload a custom card for a domain"""
        try:
            return CommonCards.upload(domain_id, image_data)
        except Exception as e:
            raise Error(
                "bad_request",
                "Failed to upload card",
                traceback.format_exc(),
            )

    @staticmethod
    def update_card(domain_id: str, card_id: str, card_type: str) -> dict:
        """Update domain card"""
        try:
            return CommonCards.update(domain_id, card_id, card_type)
        except Exception as e:
            raise Error(
                "not_found",
                "Failed to update domain card",
                traceback.format_exc(),
            )
