#
#   Copyright © 2025 Naomi Hidalgo Piñar
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
from typing import Union

from api import admin_router, token_router
from api.schemas.common import DeleteResponse, ErrorResponse
from api.schemas.notifications import (
    NotificationsUserDisplaysTriggerResponse,
    NotificationsUserTriggerDisplayFlatResponse,
    NotificationsUserTriggerDisplayResponse,
    StatusBarNotificationResponse,
)
from api.services.admin_notifications import AdminNotificationService
from api.services.error import Error
from api.services.notifications import NotificationService
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "notifications"


@token_router.get(
    "/notifications/status-bar",
    tags=[tag],
    response_model=Union[StatusBarNotificationResponse, None],
    summary="Get status bar notification",
    description=(
        "Returns the status-bar notification configured for the caller's "
        "provider (e.g. a migration banner). ``@has_token``."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def get_status_bar_notifications(request: Request):
    try:
        notification = AdminNotificationService.get_status_bar_notification(
            request.token_payload
        )
        return JSONResponse(content=notification, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get status bar notification",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/notifications/user/displays/{trigger}",
    tags=[tag],
    response_model=NotificationsUserDisplaysTriggerResponse,
    summary="Get user notification displays for a trigger",
    description="Returns the user's notification displays for the specified trigger.",
)
async def get_user_notification_displays(request: Request, trigger: str):

    try:
        return JSONResponse(
            content=NotificationsUserDisplaysTriggerResponse(
                displays=NotificationService.get_user_trigger_notifications_displays(
                    request.token_payload, trigger
                )
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktop",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/notifications/user/{trigger}/{display}",
    tags=[tag],
    response_model=NotificationsUserTriggerDisplayFlatResponse,
    summary="Get user notifications for a trigger and display",
    description=(
        "Returns the user's notifications for the specified trigger and "
        "display as a flat, ordered list with the user's language template "
        "already resolved. Legacy consumers needing the nested grouping "
        "(by order and item_type) should use "
        "GET /api/v4/notification/user/{trigger}/{display}."
    ),
)
async def get_user_notification_trigger_display(
    request: Request, trigger: str, display: str
):

    try:
        return JSONResponse(
            content=NotificationsUserTriggerDisplayFlatResponse(
                notifications=NotificationService.get_user_trigger_notifications_flat(
                    request.token_payload, trigger, display
                )
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user trigger notifications",
            traceback.format_exc(),
        )


@token_router.get(
    "/notification/user/{trigger}/{display}",
    tags=[tag],
    response_model=NotificationsUserTriggerDisplayResponse,
    summary="Get user notifications for a trigger and display (nested)",
    description=(
        "Returns the user's notifications for the specified trigger and "
        "display as a nested dict grouped by order and item_type, with each "
        "group carrying its template. Matches the legacy apiv3 "
        "``GET /api/v3/notification/user/<trigger>/<display>`` shape so Vue 2 "
        "and webapp consumers keep working after the v3 retirement. For new "
        "clients, prefer the flat variant at ``/items/notifications/user/"
        "{trigger}/{display}``. ``@has_token``."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def get_user_notification_trigger_display_nested(
    request: Request, trigger: str, display: str
):
    try:
        return JSONResponse(
            content=NotificationsUserTriggerDisplayResponse(
                notifications=NotificationService.get_user_trigger_notifications(
                    request.token_payload, trigger, display
                )
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user trigger notifications (nested)",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/items/notifications/expired",
    tags=[tag],
    response_model=DeleteResponse,
    summary="Delete expired user notifications data",
    description="Deletes expired user notifications data.",
)
async def delete_expired_user_notifications_data(request: Request):
    try:
        NotificationService.delete_expired_notifications_data()
        return JSONResponse(
            content=DeleteResponse(
                message="Expired notifications data deleted",
                message_code="item.deleted",
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to delete expired user notifications data",
            traceback.format_exc(),
        )
