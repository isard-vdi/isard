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


from api.dependencies.jwt_token import has_token, is_not_user
from fastapi import Depends
from isardvdi_common.helpers.quotas import Quotas


async def can_create_desktop(
    payload: str = Depends(has_token),
):
    """
    Check if the user can create a new desktop according to their quota.
    """
    return Quotas.desktop_create(payload["user_id"])


async def can_create_template(
    payload: str = Depends(is_not_user),
):
    """
    Check if the user can create a new template according to their quota.
    """
    return Quotas.template_create(payload["user_id"])


async def can_create_deployment(
    payload: str = Depends(is_not_user),
):
    """
    Check if the user can create a new deployment according to their quota.
    This function will not check the number of users and desktops in the deployment.
    """
    return Quotas.deployment_create(
        owner_id=payload["user_id"],
        quantity=1,
        desktops_len=1,
        users=None,
    )


async def can_create_media(
    payload: str = Depends(is_not_user),
):
    """
    Check if the user can create a new media according to their quota.
    """
    return Quotas.media_create(payload["user_id"])
