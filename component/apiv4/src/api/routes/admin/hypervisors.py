#
#   Copyright © 2025 IsardVDI
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
from typing import Literal, Optional

from api import admin_router
from api.schemas.admin.hypervisors import (
    AdminBootProgressRequest,
    AdminBootProgressResponse,
    AdminHypervisor,
    AdminHypervisorCreateData,
    AdminHypervisorCreateResponse,
    AdminHypervisorDisksFoundData,
    AdminHypervisorDisksFoundResponse,
    AdminHypervisorEnableData,
    AdminHypervisorEnableResponse,
    AdminHypervisorGpu,
    AdminHypervisorMediaDeleteData,
    AdminHypervisorMediaDeleteResponse,
    AdminHypervisorMediaFoundData,
    AdminHypervisorMediaFoundResponse,
    AdminHypervisorMountpoint,
    AdminHypervisorStartedDomain,
    AdminHypervisorStatusResponse,
    AdminHypervisorVirtPool,
    AdminHypervisorVirtPoolUpdateData,
    AdminHypervisorVpnResponse,
    AdminHypervisorWgAddrData,
    AdminHypervisorWgAddrResponse,
    AdminRegisterVlansRequest,
    AdminVlanRegistration,
    DeadRowSetResponse,
    OrchestratorHypervisor,
    OrchestratorManagedHypervisor,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin.hypervisors import AdminHypervisorsService
from api.services.error import Error
from fastapi import Path, Request
from fastapi.responses import JSONResponse, Response

tag = "admin_hypervisors"


# ── List Hypervisors ─────────────────────────────────────────────────────


@admin_router.get(
    "/admin/hypervisors",
    tags=[tag],
    response_model=list[AdminHypervisor],
    summary="List all hypervisors",
    description="List all hypervisors, optionally filtered by status.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisors_list(
    request: Request,
    status: Optional[str] = None,
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.get_hypervisors, status
        )
        return JSONResponse(
            content=[AdminHypervisor(**h).model_dump(mode="json") for h in result],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list hypervisors",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/hypervisors/{status}",
    tags=[tag],
    response_model=list[AdminHypervisor],
    summary="List hypervisors by status",
    description="List hypervisors filtered by status (Online, Offline, Error).",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisors_list_by_status(
    request: Request,
    status: Literal["Online", "Offline", "Error"] = Path(
        ..., description="Hypervisor status filter"
    ),
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.get_hypervisors, status
        )
        return JSONResponse(
            content=[
                AdminHypervisor(**h).model_dump(mode="json") for h in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list hypervisors by status",
            traceback.format_exc(),
        )


# ── Hypervisor Status ────────────────────────────────────────────────────


@admin_router.get(
    "/admin/hypervisor/status/{hyper_id}",
    tags=[tag],
    response_model=AdminHypervisorStatusResponse,
    summary="Get hypervisor status",
    description="Get the status and only_forced flag for a hypervisor.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_status(
    request: Request,
    hyper_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.get_hyper_status, hyper_id
        )
        return JSONResponse(
            content=AdminHypervisorStatusResponse(**(result or {})).model_dump(
                mode="json"
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get hypervisor status",
            traceback.format_exc(),
        )


# ── Create / Register Hypervisor ─────────────────────────────────────────


@admin_router.post(
    "/admin/hypervisor",
    tags=[tag],
    response_model=AdminHypervisorCreateResponse,
    summary="Create or register a hypervisor",
    description="Register a new hypervisor or update an existing one. "
    "Performs SSH key scanning and certificate exchange.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_create(
    request: Request,
    data: AdminHypervisorCreateData,
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.create_or_update_hypervisor, data.model_dump()
        )
        if isinstance(result, dict):
            return JSONResponse(
                content=AdminHypervisorCreateResponse(**result).model_dump(mode="json"),
                status_code=200,
            )
        return JSONResponse(
            content=AdminHypervisorCreateResponse().model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create hypervisor",
            traceback.format_exc(),
        )


# ── Enable / Disable Hypervisor ──────────────────────────────────────────


@admin_router.put(
    "/admin/hypervisor/{hyper_id}",
    tags=[tag],
    response_model=AdminHypervisorEnableResponse,
    summary="Enable or disable a hypervisor",
    description="Enable or disable an existing hypervisor.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_enable(
    request: Request,
    data: AdminHypervisorEnableData,
    hyper_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        if data.numa_topology is not None:
            await asyncio.to_thread(
                AdminHypervisorsService.update_hyper_numa_topology,
                hyper_id,
                data.numa_topology,
            )
        result = await asyncio.to_thread(
            AdminHypervisorsService.enable_hyper, hyper_id, data.enabled
        )
        if isinstance(result, dict):
            return JSONResponse(
                content=AdminHypervisorEnableResponse(**result).model_dump(mode="json"),
                status_code=200,
            )
        return JSONResponse(
            content=AdminHypervisorEnableResponse().model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update hypervisor",
            traceback.format_exc(),
        )


# ── Delete Hypervisor ────────────────────────────────────────────────────


@admin_router.delete(
    "/admin/hypervisor/{hyper_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Remove a hypervisor",
    description="Remove a hypervisor. Stops its domains and waits for engine removal.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_delete(
    request: Request,
    hyper_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        await asyncio.to_thread(AdminHypervisorsService.remove_hyper, hyper_id)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to remove hypervisor",
            traceback.format_exc(),
        )


# ── Stop Hypervisor Domains ──────────────────────────────────────────────


@admin_router.put(
    "/admin/hypervisor/stop/{hyper_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Stop all domains on a hypervisor",
    description="Force stop all running domains on the specified hypervisor.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_stop_domains(
    request: Request,
    hyper_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        await asyncio.to_thread(AdminHypervisorsService.stop_hyper_domains, hyper_id)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to stop hypervisor domains",
            traceback.format_exc(),
        )


# ── Hypervisor VPN ───────────────────────────────────────────────────────


@admin_router.get(
    "/admin/hypervisor_vpn/{hyper_id}",
    tags=[tag],
    response_model=AdminHypervisorVpnResponse,
    summary="Get hypervisor VPN config",
    description="Get the VPN configuration for a hypervisor.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_vpn(
    request: Request,
    hyper_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.get_hypervisor_vpn, hyper_id
        )
        if isinstance(result, dict):
            return JSONResponse(
                content=AdminHypervisorVpnResponse(**result).model_dump(mode="json"),
                status_code=200,
            )
        return JSONResponse(
            content=AdminHypervisorVpnResponse().model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get hypervisor VPN config",
            traceback.format_exc(),
        )


# ── Wireguard Address ────────────────────────────────────────────────────


@admin_router.post(
    "/admin/hypervisor/vm/wg_addr",
    tags=[tag],
    response_model=AdminHypervisorWgAddrResponse,
    summary="Update wireguard guest address",
    description="Update the wireguard guest IP address for a domain identified by MAC.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_wg_addr(
    request: Request,
    data: AdminHypervisorWgAddrData,
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.update_wg_address, data.mac, data.ip
        )
        if isinstance(result, dict):
            return JSONResponse(
                content=AdminHypervisorWgAddrResponse(**result).model_dump(mode="json"),
                status_code=200,
            )
        return JSONResponse(
            content=AdminHypervisorWgAddrResponse().model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update wireguard address",
            traceback.format_exc(),
        )


# ── Media / Disks Discovery ─────────────────────────────────────────────


@admin_router.post(
    "/admin/hypervisor/media_found",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Report media found on hypervisor",
    description="Register media files discovered on a hypervisor.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_media_found(
    request: Request,
    data: AdminHypervisorMediaFoundData,
):
    try:
        await asyncio.to_thread(AdminHypervisorsService.update_media_found, data.medias)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update media found",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/hypervisor/disks_found",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Report disks found on hypervisor",
    description="Register disk files discovered on a hypervisor.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_disks_found(
    request: Request,
    data: AdminHypervisorDisksFoundData,
):
    try:
        await asyncio.to_thread(AdminHypervisorsService.update_disks_found, data.disks)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update disks found",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/hypervisor/media_delete",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete media by paths",
    description="Delete media entries matching the specified paths.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_media_delete(
    request: Request,
    data: AdminHypervisorMediaDeleteData,
):
    try:
        await asyncio.to_thread(AdminHypervisorsService.delete_media, data.medias_paths)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete media",
            traceback.format_exc(),
        )


# ── GPU Management ───────────────────────────────────────────────────────


@admin_router.put(
    "/admin/hypervisors/gpus",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Assign GPUs to hypervisors",
    description="Reassign physical GPU devices to GPU profiles across all online hypervisors.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisors_assign_gpus(
    request: Request,
):
    try:
        await asyncio.to_thread(AdminHypervisorsService.assign_gpus)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to assign GPUs",
            traceback.format_exc(),
        )


# ── Orchestrator: List Hypervisors ───────────────────────────────────────


@admin_router.get(
    "/admin/orchestrator/hypervisors",
    tags=[tag],
    response_model=list[OrchestratorHypervisor],
    summary="List orchestrator hypervisors",
    description="List all hypervisors with orchestrator-specific fields.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def admin_orchestrator_hypervisors_list(
    request: Request,
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.get_orchestrator_hypervisors
        )
        return JSONResponse(
            content=[
                OrchestratorHypervisor(**h).model_dump(mode="json") for h in result
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list orchestrator hypervisors",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/orchestrator/hypervisor/{hypervisor_id}",
    tags=[tag],
    response_model=OrchestratorHypervisor,
    summary="Get orchestrator hypervisor details",
    description="Get orchestrator-specific details for a single hypervisor.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_orchestrator_hypervisor_get(
    request: Request,
    hypervisor_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.get_orchestrator_hypervisors, hyp_id=hypervisor_id
        )
        return JSONResponse(
            content=OrchestratorHypervisor(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get orchestrator hypervisor",
            traceback.format_exc(),
        )


# ── Orchestrator: Managed Hypervisors ────────────────────────────────────


@admin_router.post(
    "/admin/hypervisors/orchestrator_managed",
    tags=[tag],
    response_model=list[OrchestratorManagedHypervisor],
    summary="List orchestrator-managed hypervisors",
    description="List only hypervisors that are marked as orchestrator-managed.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def admin_orchestrator_managed_list(
    request: Request,
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.get_orchestrator_managed_hypervisors
        )
        return JSONResponse(
            content=[
                OrchestratorManagedHypervisor(**h).model_dump(mode="json")
                for h in result
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list orchestrator managed hypervisors",
            traceback.format_exc(),
        )


# ── Orchestrator: Dead Row ───────────────────────────────────────────────


@admin_router.post(
    "/admin/orchestrator/hypervisor/{hypervisor_id}/dead_row",
    tags=[tag],
    response_model=DeadRowSetResponse,
    summary="Set hypervisor dead row timeout",
    description="Set the dead row timeout for an orchestrator-managed hypervisor.",
    responses={
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_orchestrator_dead_row_set(
    request: Request,
    hypervisor_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.set_hyper_deadrow_time, hypervisor_id
        )
        return JSONResponse(
            content=DeadRowSetResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set dead row timeout",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/orchestrator/hypervisor/{hypervisor_id}/dead_row",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Reset hypervisor dead row timeout",
    description="Reset (remove) the dead row timeout for an orchestrator-managed hypervisor.",
    responses={
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_orchestrator_dead_row_reset(
    request: Request,
    hypervisor_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        await asyncio.to_thread(
            AdminHypervisorsService.set_hyper_deadrow_time, hypervisor_id, reset=True
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to reset dead row timeout",
            traceback.format_exc(),
        )


# ── Orchestrator: Stop Desktops ──────────────────────────────────────────


@admin_router.delete(
    "/admin/orchestrator/hypervisor/{hypervisor_id}/desktops",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Stop hypervisor desktops (orchestrator)",
    description="Stop all started desktops on an orchestrator-managed hypervisor.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def admin_orchestrator_stop_desktops(
    request: Request,
    hypervisor_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        await asyncio.to_thread(
            AdminHypervisorsService.stop_hyper_domains, hypervisor_id
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to stop orchestrator hypervisor desktops",
            traceback.format_exc(),
        )


# ── Orchestrator: Manage ─────────────────────────────────────────────────


@admin_router.post(
    "/admin/orchestrator/hypervisor/{hypervisor_id}/manage",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Mark hypervisor for orchestrator management",
    description="Mark a hypervisor as managed by the orchestrator.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_orchestrator_manage_set(
    request: Request,
    hypervisor_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        await asyncio.to_thread(
            AdminHypervisorsService.set_hyper_orchestrator_managed, hypervisor_id
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set orchestrator managed",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/orchestrator/hypervisor/{hypervisor_id}/manage",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Unmark hypervisor from orchestrator management",
    description="Remove orchestrator management flag from a hypervisor.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_orchestrator_manage_unset(
    request: Request,
    hypervisor_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        await asyncio.to_thread(
            AdminHypervisorsService.set_hyper_orchestrator_managed,
            hypervisor_id,
            reset=True,
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to unset orchestrator managed",
            traceback.format_exc(),
        )


# ── Virt Pools ───────────────────────────────────────────────────────────


@admin_router.get(
    "/admin/hypervisor/{hyper_id}/virt_pools",
    tags=[tag],
    response_model=list[AdminHypervisorVirtPool],
    summary="Get hypervisor virt pools",
    description="Get the virt pool assignments for a hypervisor.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_virt_pools_get(
    request: Request,
    hyper_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.get_hyper_virt_pools, hyper_id
        )
        return JSONResponse(
            content=[
                AdminHypervisorVirtPool(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get hypervisor virt pools",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/hypervisor/{hyper_id}/virt_pools",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update hypervisor virt pool assignment",
    description="Enable or disable a virt pool for a hypervisor.",
    responses={
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_virt_pools_update(
    request: Request,
    data: AdminHypervisorVirtPoolUpdateData,
    hyper_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        await asyncio.to_thread(
            AdminHypervisorsService.update_hyper_virt_pools, hyper_id, data.model_dump()
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update hypervisor virt pools",
            traceback.format_exc(),
        )


# ── Mountpoints ──────────────────────────────────────────────────────────


@admin_router.get(
    "/admin/hypervisor/mountpoints/{hyper_id}",
    tags=[tag],
    response_model=list[AdminHypervisorMountpoint],
    summary="Get hypervisor mountpoints",
    description="Get the filesystem mountpoints reported by a hypervisor.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_mountpoints(
    request: Request,
    hyper_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.get_hyper_mountpoints, hyper_id
        )
        return JSONResponse(
            content=[
                AdminHypervisorMountpoint(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get hypervisor mountpoints",
            traceback.format_exc(),
        )


# ── Started Domains ──────────────────────────────────────────────────────


@admin_router.get(
    "/admin/hypervisor/started_domains/{hyper_id}",
    tags=[tag],
    response_model=list[AdminHypervisorStartedDomain],
    summary="Get started domains on a hypervisor",
    description="Get all currently started desktop domains on a hypervisor.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_hypervisor_started_domains(
    request: Request,
    hyper_id: str = Path(..., description="Hypervisor ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminHypervisorsService.get_hyper_started_domains, hyper_id
        )
        return JSONResponse(
            content=[
                AdminHypervisorStartedDomain(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get hypervisor started domains",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/vlans",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Register VLANs from hypervisor",
    description="Creates network interface entries for discovered VLANs.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_register_vlans(request: Request, data: AdminRegisterVlansRequest):
    try:
        await asyncio.to_thread(AdminHypervisorsService.register_vlans, data.vlans)
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to register VLANs",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/hypervisor/{hyper_id}/boot_progress",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update hypervisor boot progress",
    description="Updates the boot progress data for a hypervisor.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_hypervisor_boot_progress(
    request: Request,
    hyper_id: str,
    data: AdminBootProgressRequest,
):
    try:
        await asyncio.to_thread(
            AdminHypervisorsService.update_hyper_boot_progress,
            hyper_id,
            data.boot_progress,
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update boot progress",
            traceback.format_exc(),
        )
