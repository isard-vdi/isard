#
#   Copyright © 2025 Pau Abril Iranzo
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later


from api.services.error import Error
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.lib.domains.domains import DomainsProcessed as CommonDomains


class DomainService:

    @staticmethod
    def get_domain_info(domain_id: str, payload: dict) -> dict:
        """
        Get domain information by ID.
        """
        domain_def = Caches.get_document(
            "domains",
            domain_id,
            ["id", "kind", "name", "description", "image", "guest_properties"],
            invalidate=True,
        )

        if not domain_def:
            raise Error("not_found", f"Domain with ID {domain_id} not found")

        domain = {
            **domain_def,
            **CommonDomains.get_domain_hardware(domain_id),
        }
        return Quotas.limit_user_hardware_allowed(payload, domain)
