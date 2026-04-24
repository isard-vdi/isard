#
#   Copyright © 2025 Pau Abril Iranzo, Miriam Melina Gamboa Valdez
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

from api.dependencies.jwt_token import has_token, is_not_user
from api.services.error import Error
from fastapi import Depends, Path, Request
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.recycle_bin import Helpers as RecycleBinHelpers
from isardvdi_common.lib.api_admin import ApiAdmin
from isardvdi_common.lib.deployments.deployments import DeploymentsProcessed
from isardvdi_common.lib.domains.templates.templates import TemplatesProcessed
from isardvdi_common.models.domain import Domain

## Domains


def owns_domain_id(param_name: str = "domain_id"):
    """
    Get the domain_id from route path and check if the user has access to it.
    """

    async def checker(
        payload: str = Depends(has_token),
        resource_id: str = Path(..., alias=param_name),
    ):
        return Helpers.owns_domain_id(payload=payload, domain_id=resource_id)

    return checker


def owns_domain_id_body(param_name: str = "domain_id"):
    """
    Get the domain_id from request json body and check if the user has access to it.
    """

    async def checker(
        payload: str = Depends(has_token),
        request: Request = None,
    ):
        body = await request.json()
        resource_id = body.get(param_name)
        if not resource_id:
            raise Error(
                "bad_request",
                f"Missing {param_name} in request body.",
            )

        return Helpers.owns_domain_id(payload=payload, domain_id=resource_id)

    return checker


## Templates


def _is_allowed_template_id(
    template_id: str,
    payload: dict,
) -> str:
    try:
        if not Domain.exists(template_id):
            raise Error(
                "not_found",
                f"Template with ID {template_id} not found.",
            )

        template = TemplatesProcessed.get_template(template_id)

        if template["kind"] != "template":
            raise Error(
                "bad_request",
                f"Template with ID {template_id} is not a template.",
            )

        if template["user"] == payload["user_id"]:
            return template_id

        is_allowed = Alloweds.is_allowed(payload, template, "domains")
        if not is_allowed:
            raise Error(
                "forbidden",
                f"User {payload['user_id']} is not allowed to access template {template_id}.",
            )

    except Error:
        raise Error(
            "forbidden",
            f"User {payload['user_id']} is not allowed to access template {template_id}.",
            traceback.format_exc(),
        )

    return template_id


async def is_allowed_template_id(
    template_id: str = Path(...),
    payload: str = Depends(has_token),
) -> str:
    """
    Get the template_id from route path and check if the user has access to it.
    """
    _is_allowed_template_id(template_id, payload)


def is_allowed_template_ids_body(
    param_name: str = "desktops",
) -> str:
    """
    Get the template_ids from request json body and check if the user has access to them.
    Will check the field `template_id` inside each object of the list.
    """

    async def checker(
        request: Request = None,
        payload: str = Depends(has_token),
    ):

        body = await request.json()
        resource = body.get(param_name)
        if not resource:
            return

        if not isinstance(resource, list):
            raise Error(
                "bad_request",
                f"{param_name} must be a list.",
            )

        for desktop in resource:
            if not (template_id := desktop.get("template_id")):
                continue
            _is_allowed_template_id(template_id, payload)

    return checker


def owns_template_children(
    template_id: str = Path(...),
    payload: str = Depends(has_token),
):
    """
    Get the template_id from route path and check if it has pending children.
    """
    tree = ApiAdmin.get_template_tree_list(template_id, payload["user_id"])[0]
    derivates = TemplatesProcessed.check_children(payload, tree)

    if derivates["pending"]:
        raise Error(
            "precondition_required",
            "Template has pending desktops or templates.",
            traceback.format_exc(),
        )

    return derivates


## Deployments


def owns_deployment_id(
    param_name: str = "deployment_id",
    check_co_owner: bool = True,
):
    """
    Get the deployment_id from route path and check if the user has access to it.
    """

    async def checker(
        payload: str = Depends(has_token),
        resource_id: str = Path(..., alias=param_name),
    ):
        return Helpers.owns_deployment_id(
            payload=payload,
            deployment_id=resource_id,
            check_co_owner=check_co_owner,
        )

    return checker


async def is_allowed_deployment_id_and_user_id(
    payload: str = Depends(has_token),
    deployment_id: str = Path(...),
    user_id: str = Path(...),
) -> str:
    """ "
    Get the deployment_id and user_id from route path and return the deployment_id if the user has access to it.
    """
    deployment = DeploymentsProcessed.get_deployment(deployment_id=deployment_id)
    is_allowed = Alloweds.is_allowed(
        payload,
        deployment,
        "deployments",
    )
    if not is_allowed and payload["user_id"] not in deployment["co_owners"]:
        raise Error(
            "forbidden",
            f"User {payload['user_id']} is not allowed to access the user {user_id} desktops from deployment {deployment_id}.",
        )

    # Check if the deployment is visible to the user
    if payload["user_id"] == user_id:
        if not deployment["tag_visible"]:
            raise Error(
                "forbidden",
                f" The deployment {deployment_id} is not visible to the user {user_id}.",
                traceback.format_exc(),
            )
    else:
        if payload["role_id"] not in ["admin", "manager", "advanced"]:
            raise Error(
                "forbidden",
                f"User {payload['user_id']} is not allowed to access the user {user_id} desktops from deployment {deployment_id}.",
            )
        Helpers.owns_deployment_id(
            payload=payload,
            deployment_id=deployment_id,
            check_co_owner=True,
        )

    return deployment_id


def allowed_deployment_action(action: str = "recreate"):

    async def checker(
        payload: str = Depends(has_token),
        desktop_id: str = Path(...),
    ):
        """
        Check if the user is allowed to perform the action on the desktop.
        """

        if payload["role_id"] in ["admin", "manager", "advanced"]:
            return True

        domain_tag = Caches.get_document("domains", desktop_id, ["tag"])
        user_permissions = Caches.get_document(
            "deployments", domain_tag, ["user_permissions"]
        )
        if user_permissions is None:
            user_permissions = []

        if action in user_permissions:
            return True

        raise Error(
            "unauthorized",
            f"Not enough rights to perform action {action} on desktop_id {desktop_id}",
            traceback.format_exc(),
            description_code=f"not_enough_rights_action_{action}_{desktop_id}",
        )

    return checker


## Media


async def owns_media_id(
    payload: str = Depends(is_not_user),
    media_id: str = Path(...),
) -> str:
    """
    Get the media_id from route path and return it if the user has access to it.
    """
    return Helpers.owns_media_id(
        payload=payload,
        media_id=media_id,
    )


## Booking


async def owns_booking_id(
    payload: str = Depends(has_token),
    booking_id: str = Path(...),
) -> str:
    """
    Get the booking_id from route path and check if the user has access
    to it. Mirrors v3 ``ownsBookingId`` from
    ``api/views/decorators.py``.
    """
    return Helpers.owns_booking_id(
        payload=payload,
        booking_id=booking_id,
    )


## Recycle Bin
def owns_recycle_bin_id(
    payload: str = Depends(has_token),
    recycle_bin_id: str = Path(...),
) -> str:
    """
    Get the recycle_bin_id from route path and check if the user has access to it.
    """
    return RecycleBinHelpers.owns_recycle_bin_id(payload, recycle_bin_id)
