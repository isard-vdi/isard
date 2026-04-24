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


import traceback

from api.dependencies.jwt_token import has_token
from api.services.error import Error
from fastapi import Depends
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.bastion import Bastion
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.models.targets import Targets


async def can_use_bastion(payload: str = Depends(has_token)):
    if not Helpers.can_use_bastion(payload):
        raise Error(
            "forbidden",
            "User can not use bastion",
            traceback.format_exc(),
        )


async def can_use_bastion_individual_domains(
    payload: str = Depends(has_token),
    _can_use_bastion: None = Depends(can_use_bastion),
):
    bastion_allowed = Caches.get_document("config", 1, ["bastion"]).get(
        "individual_domains"
    )
    if bastion_allowed is None:
        raise Error(
            "internal_error",
            "Bastion individual domains configuration not found",
            traceback.format_exc(),
        )

    return Alloweds.is_allowed(payload, bastion_allowed, "config", True)


def bastion_domain_verification_required() -> bool:
    return Bastion.bastion_domain_verification_required()


def domain_has_bastion_target(domain_id: str) -> bool:
    try:
        Targets.get_domain_target(domain_id)
        return True
    except Error:
        return False
