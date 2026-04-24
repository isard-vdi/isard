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


from api.dependencies.jwt_token import has_token
from fastapi import Depends, Path
from isardvdi_common.lib.hypervisors.hypervisors import HypervisorsProcessed


async def check_create_storage_pool_availability(
    payload: str = Depends(has_token),
):
    """
    Check there is a storage pool available for creation in the user's category.
    """
    return HypervisorsProcessed.check_create_storage_pool_availability(
        payload.get("category_id")
    )


async def check_virt_storage_pool_availability(
    payload: str = Depends(has_token),
    desktop_id: str = Path(...),
):
    """
    Check there is a virt storage pool available for virtualization of the user desktop.
    """
    return HypervisorsProcessed.check_virt_storage_pool_availability(
        domain_id=desktop_id
    )
