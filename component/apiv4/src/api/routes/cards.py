#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import traceback
from typing import Literal, Optional

from api import admin_router, token_router
from api.schemas.cards import CardResponse, GenerateCardRequest
from api.schemas.common import ErrorResponse
from api.services.cards import CardService
from api.services.error import Error
from fastapi import Query, Request
from fastapi.responses import JSONResponse

tag = "cards"


# =============================================================================
# DESKTOP IMAGE CARDS (token_router)
# =============================================================================


@token_router.get(
    "/images/desktops",
    tags=[tag],
    response_model=list[CardResponse],
    summary="Get desktop images",
    description="Returns all available desktop images (stock + user).",
    operation_id="get_desktop_card_images",
    responses={500: {"model": ErrorResponse}},
)
async def get_desktop_images(
    request: Request,
    desktop_id: Optional[str] = Query(
        None, description="Desktop ID to filter user cards"
    ),
) -> list[CardResponse]:
    try:
        stock = CardService.get_stock_cards()
        user = CardService.get_user_cards(request.token_payload["user_id"], desktop_id)
        return [CardResponse(**c) for c in (stock + user)]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get desktop images",
            traceback.format_exc(),
        )


@token_router.get(
    "/images/desktops/{kind}",
    tags=[tag],
    response_model=list[CardResponse],
    summary="Get desktop images by type",
    description="Returns desktop images filtered by type (stock or user).",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_desktop_images_by_type(
    request: Request,
    kind: Literal["stock", "user"],
    desktop_id: Optional[str] = Query(
        None, description="Desktop ID to filter user cards"
    ),
) -> list[CardResponse]:
    try:
        if kind == "stock":
            images = CardService.get_stock_cards()
        else:  # kind == "user" — Literal route guard ensures
            images = CardService.get_user_cards(
                request.token_payload["user_id"], desktop_id
            )
        return [CardResponse(**c) for c in (images or [])]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get desktop images by type",
            traceback.format_exc(),
        )


@token_router.get(
    "/images/desktops/stock/default/{domain_id}",
    tags=[tag],
    response_model=CardResponse,
    summary="Get default stock card for a domain",
    description="Returns the default stock card image for a specific domain.",
    responses={500: {"model": ErrorResponse}},
)
async def get_stock_default_card(request: Request, domain_id: str) -> CardResponse:
    try:
        result = CardService.get_domain_stock_card(domain_id)
        return CardResponse(**(result or {}))
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get stock default card",
            traceback.format_exc(),
        )


@token_router.get(
    "/images/desktops/user/default/{domain_id}",
    tags=[tag],
    response_model=CardResponse,
    summary="Get default user card for a domain",
    description="Returns the default user card image for a specific domain.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user_default_card(request: Request, domain_id: str) -> CardResponse:
    try:
        result = CardService.get_domain_user_card(domain_id)
        return CardResponse(**(result or {}))
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get user default card",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/images/desktops/generate",
    tags=[tag],
    response_model=CardResponse,
    summary="Generate a default card",
    description="Generates a default card image for a domain. Admin only.",
    responses={500: {"model": ErrorResponse}},
)
async def generate_default_card(
    request: Request, data: GenerateCardRequest
) -> CardResponse:
    try:
        result = CardService.generate_default_card(data.desktop_id, data.desktop_name)
        return CardResponse(**(result or {}))
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to generate default card",
            traceback.format_exc(),
        )
