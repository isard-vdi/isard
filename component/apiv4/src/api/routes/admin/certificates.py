#
#   Copyright © 2026 Josep Maria Viñolas Auquer
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

import asyncio
import traceback

from api import admin_router
from api.schemas.admin.certificates import (
    AcmeDnsRegisterRequest,
    AcmeDnsRegisterResponse,
    AcmeDnsVerifyResponse,
    CertificatesConfigResponse,
    CertificatesConfigUpdate,
)
from api.schemas.common import ErrorResponse
from api.services.admin.certificates import AdminCertificatesService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "admin-certificates"


@admin_router.get(
    "/admin/config/certificates",
    tags=[tag],
    response_model=CertificatesConfigResponse,
    summary="Get the main-domain certificate configuration",
    description="Returns the deployment main-domain certificate configuration: "
    "the names the certificate carries, how it is issued, and the ACME account "
    "used for it.",
    responses={500: {"model": ErrorResponse}},
)
async def get_certificates_config(request: Request):
    try:
        certs = await asyncio.to_thread(AdminCertificatesService.get_certificates)
        return JSONResponse(
            content=CertificatesConfigResponse(**(certs or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get the certificate configuration",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/config/certificates",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Update the main-domain certificate configuration",
    description="Persists the main-domain certificate configuration. Fields "
    "left out of the payload keep their stored value.",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def update_certificates_config(request: Request, data: CertificatesConfigUpdate):
    try:
        await asyncio.to_thread(
            AdminCertificatesService.update_certificates,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update the certificate configuration",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/config/certificates/acmedns/register",
    tags=[tag],
    response_model=AcmeDnsRegisterResponse,
    summary="Register an acme-dns account for the main domain",
    description="Registers a fresh account with the acme-dns server and stores "
    "its credentials, returning the CNAME record the domain owner has to create "
    "for DNS-01 issuance to work. Refuses when an account is already registered "
    "unless replace is set: acme-dns cannot delete accounts, so registering "
    "another one abandons the first and any CNAME created for it.",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def register_acmedns_account(request: Request, data: AcmeDnsRegisterRequest):
    try:
        result = await asyncio.to_thread(
            AdminCertificatesService.register_acmedns, data.base_url, data.replace
        )
        return JSONResponse(
            content=AcmeDnsRegisterResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to register the acme-dns account",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/config/certificates/acmedns/verify",
    tags=[tag],
    response_model=AcmeDnsVerifyResponse,
    summary="Check the acme-dns delegation for the main domain",
    description="Resolves the challenge name and reports whether it points at "
    "the registered acme-dns subdomain yet, recording the result. A delegation "
    "that is not visible is reported, not raised: this is expected to be polled "
    "while DNS propagates.",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def verify_acmedns_delegation(request: Request):
    try:
        result = await asyncio.to_thread(AdminCertificatesService.verify_acmedns)
        return JSONResponse(
            content=AcmeDnsVerifyResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check the acme-dns delegation",
            traceback.format_exc(),
        )
