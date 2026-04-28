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


import os
import traceback
from typing import Literal, TypedDict

from api.services.error import Error
from fastapi import Depends, Path, Request, status
from fastapi.security import HTTPBearer
from isardvdi_common.connections import api_sessions
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.maintenance import Maintenance
from isardvdi_common.helpers.token import Token
from isardvdi_common.lib.api_admin import ApiAdmin
from isardvdi_common.lib.domains.templates.templates import TemplatesProcessed
from isardvdi_common.models.deployment import Deployment
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.user import User


### Helpers
def get_remote_addr(request):
    return request.headers.get("x-forwarded-for", request.client.host).split(",")[0]


def maintenance(category_id=None):
    if Maintenance.enabled:
        raise Error(
            "maintenance",
            "Maintenance mode is enabled. Please try again later.",
        )
    elif category_id and Maintenance.category_enabled(category_id):
        raise Error(
            "maintenance",
            "Maintenance mode is enabled for this category. Please try again later.",
        )


class TokenFastAPI(Token):

    @staticmethod
    def get_token_header(header):
        """
        Obtains the Access Token from the a Header

        We cannot get the token from the request without refactoring token.py, so we cannot call `get_header_jwt_payload`.
        Instead we call `get_token_payload` passing the token from `OAuth2PasswordBearer`
        """

        return {}


class TokenPayload(TypedDict):
    provider: (
        Literal["unknown", "local", "ldap", "form", "external", "saml", "google"] | str
    )
    user_id: str
    role_id: Literal["admin", "manager", "advanced", "user"]
    category_id: str
    group_id: str
    name: str


## Router Dependencies
async def has_token(
    token: dict = Depends(HTTPBearer()), request: Request = None
) -> TokenPayload:
    token = token.credentials
    payload: TokenPayload = TokenFastAPI.get_token_payload(token)
    if payload.get("type", "") not in ["login", ""]:
        raise Error(
            "forbidden",
            "Token not valid for this operation.",
            traceback.format_exc(),
        )

    jwt_payload = TokenFastAPI.get_jwt_payload(token)
    session_id = jwt_payload.get("session_id", "")
    kid = jwt_payload.get("kid", "")
    if session_id == "isardvdi-service":
        # Internal service tokens: skip session validation and grant admin access
        # This covers admin service tokens (kid=isardvdi) and hypervisor
        # calls (kid=isardvdi-hypervisors) that use their own secrets
        if kid == "isardvdi-hypervisors":
            payload["role_id"] = "admin"
            payload["category_id"] = "*"
    else:
        try:
            api_sessions.get(session_id, get_remote_addr(request))
        except Error as e:
            raise e

    if payload.get("role_id") != "admin":
        maintenance(payload.get("category_id"))

    # Propagate session_id into payload so downstream code can check it
    payload["session_id"] = session_id

    # Save the payload in the request for later use
    request.token_payload = payload

    return payload


async def is_not_user(payload: TokenPayload = Depends(has_token)) -> TokenPayload:
    if payload["role_id"] == "user":
        raise Error(
            "forbidden",
            "Not enough rights.",
            traceback.format_exc(),
        )
    return payload


async def is_admin_or_manager(
    payload: TokenPayload = Depends(has_token),
) -> TokenPayload:
    if payload["role_id"] not in ["admin", "manager"]:
        raise Error(
            "forbidden",
            "Not enough rights.",
            traceback.format_exc(),
        )
    return payload


async def is_admin(payload: TokenPayload = Depends(has_token)) -> TokenPayload:
    if payload["role_id"] != "admin":
        raise Error(
            "forbidden",
            "Not enough rights.",
            traceback.format_exc(),
        )
    return payload


async def has_token_maintenance(
    token: dict = Depends(HTTPBearer()), request: Request = None
) -> TokenPayload:
    token = token.credentials
    payload: TokenPayload = TokenFastAPI.get_token_payload(token)
    if payload.get("type", "") not in ["login", ""]:
        raise Error(
            "forbidden",
            "Token not valid for this operation.",
            traceback.format_exc(),
        )

    jwt_payload = TokenFastAPI.get_jwt_payload(token)
    session_id = jwt_payload.get("session_id", "")
    if session_id != "isardvdi-service":
        try:
            api_sessions.get(session_id, get_remote_addr(request))
        except Error as e:
            raise e

    request.token_payload = payload

    return payload


async def has_token_register(
    token: dict = Depends(HTTPBearer()), request: Request = None
) -> TokenPayload:
    token = token.credentials
    payload: TokenPayload = TokenFastAPI.get_token_payload(token)
    if payload.get("type", "") != "register":
        raise Error(
            "forbidden",
            "Token not valid for this operation.",
            traceback.format_exc(),
        )

    maintenance(payload.get("category_id"))
    request.token_payload = payload

    return payload


async def has_token_password_reset_login(
    token: dict = Depends(HTTPBearer()), request: Request = None
) -> TokenPayload:
    token = token.credentials
    payload: TokenPayload = TokenFastAPI.get_token_payload(token)
    if payload.get("type", "") not in [
        "password-reset-required",
        "password-reset",
        "login",
        "",
    ]:
        raise Error(
            "forbidden",
            "Token not valid for this operation.",
            traceback.format_exc(),
        )

    request.token_payload = payload

    return payload


async def has_token_disclaimer(
    token: dict = Depends(HTTPBearer()), request: Request = None
) -> TokenPayload:
    token = token.credentials
    payload: TokenPayload = TokenFastAPI.get_token_payload(token)
    if payload.get("type", "") not in ["disclaimer-acknowledgement-required"]:
        raise Error(
            "forbidden",
            "Token not valid for this operation.",
            traceback.format_exc(),
        )

    request.token_payload = payload

    return payload


async def has_token_direct_viewer(
    token: dict = Depends(HTTPBearer()), request: Request = None
):
    token = token.credentials
    payload = TokenFastAPI.get_token_payload(token)
    if payload.get("type", "") not in ["direct-viewer", "login", ""]:
        raise Error(
            "forbidden",
            "Token not valid for direct viewer operation.",
            traceback.format_exc(),
        )

    request.token_payload = payload

    return payload


async def has_migration_required_or_login_token(
    token: dict = Depends(HTTPBearer()), request: Request = None
):
    token = token.credentials
    payload = TokenFastAPI.get_token_payload(token)
    if payload.get("type", "") not in ["user-migration-required", "login", ""]:
        raise Error(
            "forbidden",
            "Token not valid for this operation.",
            traceback.format_exc(),
        )

    jwt_payload = TokenFastAPI.get_jwt_payload(token)
    session_id = jwt_payload.get("session_id", "")
    if session_id != "isardvdi-service":
        try:
            api_sessions.get(session_id, get_remote_addr(request))
        except Error as e:
            raise e

    maintenance(payload.get("category_id"))

    # Save the payload in the request for later use
    request.token_payload = payload

    return payload
