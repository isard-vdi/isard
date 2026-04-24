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

from api.dependencies.alloweds import owns_template_children
from api.services.error import Error
from fastapi import Depends, Path
from isardvdi_common.lib.deployments.deployments import DeploymentsProcessed
from isardvdi_common.models.deployment import Deployment
from isardvdi_common.models.domain import Domain


def check_domain_kind(param_name: str = "domain_id", expected_kind: str = "desktop"):
    """
    Get the domain_id from route path and check if the domain is of the expected kind.
    """

    async def checker(
        resource_id: str = Path(..., alias=param_name),
    ):
        if Domain(resource_id).kind != expected_kind:
            raise Error(
                "bad_request",
                f"Domain with ID {resource_id} is must be of kind {expected_kind}",
            )

    return checker


async def template_has_no_children(derivates=Depends(owns_template_children)):
    """
    Check that the template has no children
    """
    if len(derivates["domains"]) > 1:
        raise Error(
            "precondition_required",
            "Template has children",
            traceback.format_exc(),
        )


async def deployment_has_no_started_desktops(deployment_id: str = Path(...)):
    """
    Check if the deployment has any started desktops.
    """
    return Deployment(deployment_id).check_desktops_started()


def tag_desktop_ids_belong_to_deployment(
    deployment_id: str,
    tag_desktop_ids: list[str],
):
    return DeploymentsProcessed.validate_tag_desktop_ids_for_deployment(
        deployment_id,
        tag_desktop_ids,
    )
