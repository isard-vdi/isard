# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log

from flask import jsonify, request
from isardvdi_protobuf.queue.storage.v1 import ConvertRequest, DiskFormat

from api import app

from .._common.api_exceptions import Error
from ..libv2.api_storage import get_disks, parse_disks
from ..libv2.storage import Storage
from ..libv2.storage_pool import StoragePool
from ..libv2.task import Task
from .decorators import has_token, ownsStorageId


@app.route("/api/v3/storage/<status>", methods=["GET"])
@has_token
def api_v3_storage(payload, status):

    disks = get_disks(
        payload["user_id"],
        pluck=[
            "id",
            "user_id",
            "user_name",
            {"qemu-img-info": {"virtual-size": True, "actual-size": True}},
            "status_logs",
        ],
        status=status,
    )

    disks = parse_disks(disks)

    return (
        json.dumps(disks),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/storage/<storage_id>/convert/<new_storage_type>",
    methods=["POST"],
)
@app.route(
    "/api/v3/storage/<storage_id>/convert/<new_storage_type>/compress",
    methods=["POST"],
)
@has_token
def storage_convert(payload, storage_id, new_storage_type, compress=None):
    """
    Endpoint that creates a Task to convert an storage to a new storage.

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :param new_storage_type: New storage format
    :type new_storage_type: str
    :param compress: if 'compress' compress new qcow2 storage
    :type compress: str
    :return: New storage ID
    :rtype: Set with Flask response values and data in JSON
    """
    # https://github.com/danielgtaylor/python-betterproto/issues/174
    disk_format = f"DISK_FORMAT_{new_storage_type.upper()}"
    if not hasattr(DiskFormat, disk_format):
        raise Error(
            error="bad_request",
            description=f"Storage type {new_storage_type} not supported",
        )
    if not Storage.exists(storage_id):
        raise Error(error="not_found", description="Storage not found")
    ownsStorageId(payload, storage_id)
    compress = request.url_rule.rule.endswith("/compress")
    origin_storage = Storage(storage_id)
    if origin_storage.status != "ready":
        raise Error(error="precondition_required", description="Storage not ready")
    origin_storage.status = "maintenance"
    new_storage = Storage(
        user_id=origin_storage.user_id,
        status="creating",
        type=new_storage_type.lower(),
        directory_path=origin_storage.directory_path,
    )
    Task(
        user_id=payload.get("user_id"),
        queue=f"storage.{StoragePool.get_by_path(origin_storage.directory_path)[0].id}.default",
        task="convert",
        job_kwargs={
            "timeout": 4096,
            "args": [
                ConvertRequest(
                    source_disk_path=f"{origin_storage.directory_path}/{origin_storage.id}.{origin_storage.type}",
                    dest_disk_path=f"{new_storage.directory_path}/{new_storage.id}.{new_storage.type}",
                    format=getattr(DiskFormat, disk_format),
                    compression=compress,
                )
            ],
        },
        dependents=[
            {
                "queue": "api",
                "task": "storage_ready",
                "job_kwargs": {
                    "kwargs": {
                        "storage_ids": [origin_storage.id],
                        "on_finished_storage_ids": [new_storage.id],
                        "on_canceled_delete_storage_ids": [new_storage.id],
                    }
                },
            }
        ],
    )
    return jsonify(new_storage.id)
