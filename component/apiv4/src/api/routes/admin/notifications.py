#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import traceback
from typing import Literal

from api import admin_router
from api.schemas.admin.notifications import (
    AdminUserDisplaysResponse,
    NotificationActionsResponse,
    NotificationCreateRequest,
    NotificationDataListResponse,
    NotificationDeleteRequest,
    NotificationDetailResponse,
    NotificationGroupedDataResponse,
    NotificationListResponse,
    NotificationResponse,
    NotificationStatusesResponse,
    NotificationUpdateRequest,
    TemplateCreateRequest,
    TemplateListResponse,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateResponse,
    TemplateUpdateRequest,
)
from api.schemas.common import (
    DeleteResponse,
    EmptyResponse,
    ErrorResponse,
    SimpleResponse,
)
from api.services.admin.notifications import AdminNotificationService
from api.services.error import Error
from api.services.notifications import NotificationService
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "admin-notifications"


# =============================================================================
# TEMPLATES (admin_router)
# =============================================================================


@admin_router.post(
    "/admin/notifications/template",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Create notification template",
    description="Creates a new notification template.",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def admin_create_notification_template(
    request: Request,
    data: TemplateCreateRequest,
):
    try:
        template_id = await asyncio.to_thread(
            AdminNotificationService.create_template,
            data.model_dump(exclude_none=True),
        )
        return JSONResponse(
            content=SimpleResponse(id=template_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create notification template",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/notifications/templates",
    tags=[tag],
    response_model=TemplateListResponse,
    summary="List all notification templates",
    description="Returns all notification templates.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_list_notification_templates(request: Request):
    try:
        templates = await asyncio.to_thread(AdminNotificationService.get_templates)
        return JSONResponse(
            content=TemplateListResponse(templates=templates).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve notification templates",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/notifications/templates/custom",
    tags=[tag],
    response_model=TemplateListResponse,
    summary="List custom notification templates",
    description="Returns custom (non-system) notification templates.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_list_custom_notification_templates(request: Request):
    try:
        templates = await asyncio.to_thread(
            AdminNotificationService.get_templates, "custom"
        )
        return JSONResponse(
            content=TemplateListResponse(templates=templates).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve custom notification templates",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/notifications/templates/system",
    tags=[tag],
    response_model=TemplateListResponse,
    summary="List system notification templates",
    description="Returns system notification templates.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_list_system_notification_templates(request: Request):
    try:
        templates = await asyncio.to_thread(
            AdminNotificationService.get_templates, "system"
        )
        return JSONResponse(
            content=TemplateListResponse(templates=templates).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve system notification templates",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/notifications/template/{template_id}",
    tags=[tag],
    response_model=TemplateResponse,
    summary="Get notification template",
    description="Returns a notification template by its ID.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def admin_get_notification_template(request: Request, template_id: str):
    try:
        template = await asyncio.to_thread(
            AdminNotificationService.get_template, template_id
        )
        return JSONResponse(
            content=TemplateResponse(**(template or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve notification template",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/notifications/template/preview",
    tags=[tag],
    response_model=TemplatePreviewResponse,
    summary="Preview template rendering",
    description="Renders a notification event template with the provided data.",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def admin_preview_notification_template(
    request: Request,
    data: TemplatePreviewRequest,
):
    try:
        texts = await asyncio.to_thread(
            AdminNotificationService.preview_template,
            data.event,
            data.user_id,
            data.data,
        )
        return JSONResponse(
            content=TemplatePreviewResponse(**(texts or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to preview notification template",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/notifications/template/{template_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update notification template",
    description="Updates a notification template by its ID.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_notification_template(
    request: Request,
    template_id: str,
    data: TemplateUpdateRequest,
):
    try:
        await asyncio.to_thread(
            AdminNotificationService.update_template,
            template_id,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update notification template",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/notifications/template/{template_id}",
    tags=[tag],
    response_model=DeleteResponse,
    summary="Delete notification template",
    description="Deletes a notification template by its ID.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_delete_notification_template(request: Request, template_id: str):
    try:
        await asyncio.to_thread(AdminNotificationService.delete_template, template_id)
        return JSONResponse(
            content=DeleteResponse(
                message="Notification template deleted",
                message_code="item.deleted",
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete notification template",
            traceback.format_exc(),
        )


# =============================================================================
# NOTIFICATIONS CRUD (admin_router)
# =============================================================================


@admin_router.get(
    "/admin/notifications",
    tags=[tag],
    response_model=NotificationListResponse,
    summary="List all notifications",
    description="Returns all notifications.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_list_notifications(request: Request):
    try:
        notifications = await asyncio.to_thread(
            AdminNotificationService.get_all_notifications
        )
        return JSONResponse(
            content=NotificationListResponse(notifications=notifications).model_dump(
                mode="json"
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve notifications",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/notification",
    tags=[tag],
    response_model=NotificationResponse,
    summary="Create notification",
    description="Creates a new notification.",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def admin_create_notification(
    request: Request,
    data: NotificationCreateRequest,
):
    try:
        notification_id = await asyncio.to_thread(
            AdminNotificationService.create_notification,
            data.model_dump(exclude_none=True),
        )
        return JSONResponse(
            content=NotificationResponse(id=notification_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create notification",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/notification/actions",
    tags=[tag],
    response_model=NotificationActionsResponse,
    summary="List notification actions",
    description="Returns all notification actions.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_list_notification_actions(request: Request):
    try:
        actions = await asyncio.to_thread(
            AdminNotificationService.get_notification_actions
        )
        return JSONResponse(
            content=NotificationActionsResponse(actions=actions).model_dump(
                mode="json"
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve notification actions",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/notification/{notification_id}",
    tags=[tag],
    response_model=NotificationDetailResponse,
    summary="Get notification",
    description="Returns a notification by its ID.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def admin_get_notification(request: Request, notification_id: str):
    try:
        notification = await asyncio.to_thread(
            AdminNotificationService.get_notification, notification_id
        )
        return JSONResponse(
            content=NotificationDetailResponse(notification).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve notification",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/notification/{notification_id}",
    tags=[tag],
    response_model=NotificationResponse,
    summary="Update notification",
    description="Updates a notification by its ID.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_update_notification(
    request: Request,
    notification_id: str,
    data: NotificationUpdateRequest,
):
    try:
        await asyncio.to_thread(
            AdminNotificationService.update_notification,
            notification_id,
            data.model_dump(exclude_none=True),
        )
        return JSONResponse(
            content=NotificationResponse(id=notification_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update notification",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/notification/{notification_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete notification",
    description="Deletes a notification by its ID.",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def admin_delete_notification(
    request: Request,
    notification_id: str,
    data: NotificationDeleteRequest,
):
    try:
        await asyncio.to_thread(
            AdminNotificationService.delete_notification,
            notification_id,
            data.delete_logs,
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete notification",
            traceback.format_exc(),
        )


# =============================================================================
# NOTIFICATION DATA (admin_router)
# =============================================================================


@admin_router.get(
    "/admin/notifications/data/status/{status}/user/{user_id}",
    tags=[tag],
    response_model=NotificationDataListResponse,
    summary="Get user notification data by status",
    description="Returns notification data for a user filtered by status.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_get_notifications_data_by_status(
    request: Request, status: str, user_id: str
):
    try:
        data = await asyncio.to_thread(
            AdminNotificationService.get_notifications_data_by_status, status, user_id
        )
        return JSONResponse(
            content=NotificationDataListResponse(data=data).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve notification data",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/notifications/statuses",
    tags=[tag],
    response_model=NotificationStatusesResponse,
    summary="Get available notification statuses",
    description="Returns all distinct notification statuses.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_get_notification_statuses(request: Request):
    try:
        statuses = await asyncio.to_thread(
            AdminNotificationService.get_notification_statuses
        )
        return JSONResponse(
            content=NotificationStatusesResponse(statuses=statuses).model_dump(
                mode="json"
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve notification statuses",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/notifications/data/by_status/{status}",
    tags=[tag],
    response_model=NotificationGroupedDataResponse,
    summary="Get notifications grouped by status",
    description="Returns notification data grouped by user for a given status.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_get_notifications_grouped_by_status(
    request: Request, status: Literal["pending", "notified"]
):
    try:
        data = await asyncio.to_thread(
            AdminNotificationService.get_notifications_grouped_by_status, status
        )
        return JSONResponse(
            content=NotificationGroupedDataResponse(data=data).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve grouped notification data",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/notifications/data/user/{user_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete user notification data",
    description="Deletes all notification data for a specific user.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_delete_user_notification_data(request: Request, user_id: str):
    try:
        await asyncio.to_thread(
            AdminNotificationService.delete_user_notification_data, user_id
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete user notification data",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/notifications/data/{notification_data_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete specific notification data",
    description="Deletes a specific notification data entry by its ID.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_delete_notification_data(request: Request, notification_data_id: str):
    try:
        await asyncio.to_thread(
            AdminNotificationService.delete_notification_data, notification_data_id
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete notification data",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/notifications/data",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete all notification data",
    description="Deletes all notification data entries.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_delete_all_notification_data(request: Request):
    try:
        await asyncio.to_thread(AdminNotificationService.delete_all_notification_data)
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete all notification data",
            traceback.format_exc(),
        )


# =============================================================================
# USER DISPLAYS (admin_router)
# =============================================================================


@admin_router.get(
    "/admin/notifications/user/displays/{user_id}/{trigger}",
    tags=[tag],
    response_model=AdminUserDisplaysResponse,
    summary="Get user notification displays",
    description="Returns the notification displays for a specific user and trigger.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_get_user_notification_displays(
    request: Request, user_id: str, trigger: str
):
    try:
        displays = await asyncio.to_thread(
            AdminNotificationService.get_user_displays, user_id, trigger
        )
        return JSONResponse(
            content=AdminUserDisplaysResponse(displays=displays).model_dump(
                mode="json"
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user notification displays",
            traceback.format_exc(),
        )


# NOTE: three of the four user-facing token_router endpoints that used
# to live below — /notifications/status-bar,
# /notification/user/displays/{trigger}, and
# /notification/user/{trigger}/{display} — were dead code: their
# user-facing duplicates in routes/notifications.py shadow them via
# FastAPI's first-match rule. They were deleted in commit cleanup;
# coverage of the live endpoints lives in test_notifications.py.


# =============================================================================
# Expired-notifications cleanup (admin-only)
# =============================================================================


@admin_router.delete(
    "/items/notifications/expired",
    tags=[tag],
    response_model=DeleteResponse,
    summary="Delete expired user notifications data",
    description="Deletes expired user notifications data.",
)
async def delete_expired_user_notifications_data(request: Request):
    try:
        await asyncio.to_thread(NotificationService.delete_expired_notifications_data)
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
