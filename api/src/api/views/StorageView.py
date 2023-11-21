# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json

from flask import jsonify, request
from isardvdi_common.api_exceptions import Error
from isardvdi_common.domain import Domain
from isardvdi_common.storage import Storage
from isardvdi_common.storage_pool import StoragePool
from isardvdi_common.task import Task
from isardvdi_protobuf.queue.storage.v1 import ConvertRequest, DiskFormat

from api import app

from ..libv2.api_storage import (
    get_disks_ids_by_status,
    get_user_ready_disks,
    parse_disks,
)
from .decorators import has_token, is_admin, ownsStorageId


def check_storage_existence_and_permissions(payload, storage_id):
    """
    Check storage existence and permissions.

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    """
    if not Storage.exists(storage_id):
        raise Error(error="not_found", description="Storage not found")
    ownsStorageId(payload, storage_id)


def set_storage_maintenance(payload, storage_id):
    """
    Set storage to maintenance status.

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Storage object
    :rtype: isardvdi_common.storage.Storage
    """

    check_storage_existence_and_permissions(payload, storage_id)
    storage = Storage(storage_id)
    if storage.status != "ready":
        raise Error(error="precondition_required", description="Storage not ready")
    storage.status = "maintenance"
    return storage


@app.route("/api/v3/storage", methods=["POST"])
# TODO: Quotas should be implemented before open this endpoint
# @has_token
@is_admin
def create_storage(payload):
    """
    Endpoint to create a storage with storage specifications as JSON in body request.

    Storage specifications in JSON:
    {
        "usage_type": "Usage: desktop, media, template, volatile",
        "storage_type": "disk format of the new storage",
        "size": "string with the size of new storage like qemu-img command",
        "parent": "Storage ID to be used as backing file",
        "priority": "low, default or high",
    }

    :param payload: Data from JWT
    :type payload: dict
    :return: Storage ID
    :rtype: Set with Flask response values and data in JSON
    """
    if not request.is_json:
        raise Error(
            description="No JSON in body request with storage specifications",
        )
    request_json = request.get_json()
    for specification in ["usage_type", "storage_type"]:
        if specification not in request_json:
            raise Error(
                description=f"No {specification} in JSON of body request",
            )
    if "size" not in request_json and "parent" not in request_json:
        raise Error(
            description="size or parent must be specified in JSON of body request",
        )
    priority = request_json.get("priority", "default")
    if priority not in ["low", "default", "high"]:
        raise Error(
            description="priority should be low, default or high",
        )
    parent_args = {}
    if "parent" in request_json:
        if not Storage.exists(request_json.get("parent")):
            raise Error(error="not_found", description="Parent storage not found")
        parent = Storage(request_json.get("parent"))
        if parent.status != "ready":
            raise Error(
                error="precondition_required", description="Parent storage not ready"
            )
        parent_args = {
            "parent_path": f"{parent.directory_path}/{parent.id}.{parent.type}",
            "parent_type": parent.type,
        }
    storage_pool = StoragePool.get_best_for_action("create")
    storage = Storage(
        status="maintenance",
        user_id=payload.get("user_id"),
        type=request_json.get("storage_type"),
        parent=request_json.get("parent"),
        directory_path=storage_pool.get_directory_path_by_usage(
            request_json.get("usage_type")
        ),
    )
    try:
        storage.create_task(
            user_id=payload.get("user_id"),
            queue=f"storage.{storage_pool.id}.{priority}",
            task="create",
            job_kwargs={
                "kwargs": {
                    "storage_path": f"{storage.directory_path}/{storage.id}.{storage.type}",
                    "storage_type": storage.type,
                    "size": request_json.get("size"),
                    **parent_args,
                },
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "update_status",
                    "job_kwargs": {
                        "kwargs": {
                            "statuses": {
                                "finished": {
                                    "ready": {
                                        "storage": [storage.id],
                                    },
                                },
                            },
                        },
                    },
                }
            ],
        )
    except Exception as e:
        if e.args[0] == "precondition_required":
            raise Error(
                "precondition_required",
                f"Storage {storage.id} already has a pending task.",
            )
        raise Error(
            "internal_server_error",
            "Error creating storage",
        )
    return jsonify(storage.id)


@app.route("/api/v3/storage/<path:storage_id>/parents", methods=["GET"])
@has_token
def storage_parents(payload, storage_id):
    return jsonify(
        [
            {
                "id": storage.id,
                "status": storage.status,
                "parent_id": storage.parent,
                "domains": [
                    {"id": domain.id, "name": domain.name, "kind": domain.kind}
                    for domain in storage.domains
                ],
            }
            for storage in [Storage(storage_id)] + Storage(storage_id).parents
        ]
    )


@app.route("/api/v3/storage/<path:storage_id>/task", methods=["GET"])
@has_token
def storage_task(payload, storage_id):
    """
    Endpoint that get Task as dict of a Storage.

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task as dict
    :rtype: Set with Flask response values and data in JSON
    """
    check_storage_existence_and_permissions(payload, storage_id)
    storage = Storage(storage_id)
    task_dict = None
    if storage.task:
        task_dict = Task(storage.task).to_dict()
    return jsonify(task_dict)


@app.route("/api/v3/storage/ready", methods=["GET"])
@has_token
def api_v3_storage(payload):
    disks = get_user_ready_disks(payload["user_id"])

    disks = parse_disks(disks)

    return (
        json.dumps(disks),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/storage/<path:storage_id>", methods=["DELETE"])
@has_token
def storage_delete(payload, storage_id):
    """
    Endpoint to delete a storage

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    storage = set_storage_maintenance(payload, storage_id)
    try:
        storage.create_task(
            user_id=payload.get("user_id"),
            queue=f"storage.{StoragePool.get_best_for_action('delete', path=storage.directory_path).id}.default",
            task="delete",
            job_kwargs={
                "kwargs": {
                    "path": f"{storage.directory_path}/{storage.id}.{storage.type}",
                },
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "update_status",
                    "job_kwargs": {
                        "kwargs": {
                            "statuses": {
                                "finished": {
                                    "deleted": {
                                        "storage": [storage.id],
                                    },
                                },
                                "canceled": {
                                    "ready": {
                                        "storage": [storage.id],
                                    },
                                },
                            },
                        },
                    },
                }
            ],
        )
    except Exception as e:
        if e.args[0] == "precondition_required":
            raise Error(
                "precondition_required",
                f"Storage {storage.id} already has a pending task.",
            )
        raise Error(
            "internal_server_error",
            "Error deleting storage",
        )
    return jsonify(storage.task)


@app.route(
    "/api/v3/storage/<path:storage_id>/update_qemu_img_info",
    methods=["PUT"],
)
@has_token
def storage_update_qemu_img_info(payload, storage_id):
    """
    Endpoint that creates a Task to update storage qemu-img info.

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    storage = set_storage_maintenance(payload, storage_id)
    try:
        storage.create_task(
            user_id=payload.get("user_id"),
            queue=f"storage.{StoragePool.get_best_for_action('qemu_img_info', path=storage.directory_path).id}.default",
            task="qemu_img_info",
            job_kwargs={
                "kwargs": {
                    "storage_id": storage.id,
                    "storage_path": f"{storage.directory_path}/{storage.id}.{storage.type}",
                }
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "storage_update",
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "update_status",
                            "job_kwargs": {
                                "kwargs": {
                                    "statuses": {
                                        "finished": {
                                            "ready": {
                                                "storage": [storage.id],
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    ],
                }
            ],
        )
    except Exception as e:
        if e.args[0] == "precondition_required":
            raise Error(
                "precondition_required",
                f"Storage {storage.id} already has a pending task.",
            )
        raise Error(
            "internal_server_error",
            "Error updating qemu img info for storage",
        )
    return jsonify(storage.task)


@app.route("/api/v3/storage/<path:storage_id>/check_backing_chain", methods=["PUT"])
@has_token
def storage_check_check_backing_chain(payload, storage_id):
    """
    Endpoint that creates a Task to check storage backing chain.

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    check_storage_existence_and_permissions(payload, storage_id)
    storage = Storage(storage_id)
    return jsonify(
        storage.check_backing_chain(user_id=payload.get("user_id"), blocking=False)
    )


@app.route(
    "/api/v3/storage/<path:storage_id>/check_existence",
    methods=["PUT"],
)
@has_token
def storage_check_existence(payload, storage_id):
    """
    Endpoint that creates a Task to check storage existence.

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    storage = set_storage_maintenance(payload, storage_id)
    try:
        storage.create_task(
            user_id=payload.get("user_id"),
            queue=f"storage.{StoragePool.get_best_for_action('check_existence', path=storage.directory_path).id}.default",
            task="check_existence",
            job_kwargs={
                "kwargs": {
                    "storage_id": storage.id,
                    "storage_path": f"{storage.directory_path}/{storage.id}.{storage.type}",
                }
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "storage_update",
                }
            ],
        )
    except Exception as e:
        if e.args[0] == "precondition_required":
            raise Error(
                "precondition_required",
                f"Storage {storage.id} already has a pending task.",
            )
        raise Error(
            "internal_server_error",
            "Error checking storage existence",
        )
    return jsonify(storage.task)


@app.route(
    "/api/v3/storage/<path:storage_id>/update_parent",
    methods=["PUT"],
)
@has_token
def storage_update_parent(payload, storage_id):
    """
    Endpoint that creates a Task to update storage parent.

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    storage = set_storage_maintenance(payload, storage_id)
    try:
        storage.create_task(
            user_id=payload.get("user_id"),
            queue="core",
            task="storage_update_parent",
            job_kwargs={
                "kwargs": {
                    "storage_id": storage.id,
                }
            },
            dependencies=[
                {
                    "queue": "core",
                    "task": "storage_update",
                    "dependencies": [
                        {
                            "queue": f"storage.{StoragePool.get_best_for_action('check_backing_filename', path=storage.directory_path).id}.default",
                            "task": "check_backing_filename",
                            "dependencies": [
                                {
                                    "queue": f"storage.{StoragePool.get_best_for_action('qemu_img_info', path=storage.directory_path).id}.default",
                                    "task": "qemu_img_info",
                                    "job_kwargs": {
                                        "kwargs": {
                                            "storage_id": storage.id,
                                            "storage_path": f"{storage.directory_path}/{storage.id}.{storage.type}",
                                        }
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        )
    except Exception as e:
        if e.args[0] == "precondition_required":
            raise Error(
                "precondition_required",
                f"Storage {storage.id} already has a pending task.",
            )
        raise Error(
            "internal_server_error",
            "Error updating storage parent",
        )
    return jsonify(storage.task)


@app.route("/api/v3/storage/<path:storage_id>/path/<path:path>", methods=["PUT"])
@has_token
def storage_move(payload, storage_id, path):
    """
    Endpoint to move a storage to another path

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :param path: Absolute path without leading slash to move the storage
    :type path: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    check_storage_existence_and_permissions(payload, storage_id)
    path = f"/{path}"
    storage_pool_destination = StoragePool.get_best_for_action("move", path=path)
    if not storage_pool_destination:
        raise Error(error="not_found", description="Path not found")
    storage = Storage(storage_id)
    if storage.status != "ready":
        raise Error(error="precondition_required", description="Storage not ready")
    if storage.directory_path == path:
        raise Error(error="bad_request", description="Storage already in path")
    for domain in Domain.get_with_storage(storage):
        if domain.status != "Stopped":
            raise Error(
                error="precondition_required",
                description=f"Storage in use by domain {domain.id}",
            )
    if storage.children:
        raise Error(
            error="conflict",
            description=f"Used as backing file for {', '.join([storage.id for storage in storage.children])}",
        )
    storage.status = "maintenance"
    storage_pool_origin = StoragePool.get_best_for_action(
        "move", path=storage.directory_path
    )
    if storage_pool_origin == storage_pool_destination:
        queue = storage_pool_origin.id
    else:
        storage_pool_ids = [storage_pool_origin.id, storage_pool_destination.id]
        storage_pool_ids.sort()
        queue = ":".join(storage_pool_ids)
    try:
        storage.create_task(
            user_id=payload.get("user_id"),
            queue=f"storage.{queue}.default",
            task="move",
            job_kwargs={
                "kwargs": {
                    "origin_path": f"{storage.directory_path}/{storage.id}.{storage.type}",
                    "destination_path": f"{path}/{storage.id}.{storage.type}",
                },
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "storage_update",
                    "job_kwargs": {
                        "kwargs": {
                            "id": storage.id,
                            "directory_path": path,
                            "qemu-img-info": {
                                "filename": f"{path}/{storage.id}.{storage.type}"
                            },
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "update_status",
                            "job_kwargs": {
                                "kwargs": {
                                    "statuses": {
                                        "finished": {
                                            "ready": {
                                                "storage": [storage.id],
                                            },
                                        },
                                        "canceled": {
                                            "ready": {
                                                "storage": [storage.id],
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    ],
                },
            ],
        )
    except Exception as e:
        if e.args[0] == "precondition_required":
            raise Error(
                "precondition_required",
                f"Storage {storage.id} already has a pending task.",
            )
        raise Error(
            "internal_server_error",
            "Error moving storage",
        )
    return jsonify(storage.task)


@app.route(
    "/api/v3/storage/<path:storage_id>/convert/<new_storage_type>",
    methods=["POST"],
)
@app.route(
    "/api/v3/storage/<path:storage_id>/convert/<new_storage_type>/compress",
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
    origin_storage = set_storage_maintenance(payload, storage_id)
    compress = request.url_rule.rule.endswith("/compress")
    new_storage = Storage(
        user_id=origin_storage.user_id,
        status="creating",
        type=new_storage_type.lower(),
        directory_path=origin_storage.directory_path,
    )
    try:
        origin_storage.create_task(
            user_id=payload.get("user_id"),
            queue=f"storage.{StoragePool.get_best_for_action('convert', path=origin_storage.directory_path).id}.default",
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
                    "queue": "core",
                    "task": "update_status",
                    "job_kwargs": {
                        "kwargs": {
                            "statuses": {
                                "_all": {
                                    "ready": {
                                        "storage": [origin_storage.id],
                                    },
                                },
                                "finished": {
                                    "ready": {
                                        "storage": [new_storage.id],
                                    },
                                },
                                "canceled": {
                                    "deleted": {
                                        "storage": [new_storage.id],
                                    },
                                },
                            }
                        }
                    },
                }
            ],
        )
    except Exception as e:
        if e.args[0] == "precondition_required":
            raise Error(
                "precondition_required",
                f"Storage {origin_storage.id} already has a pending task.",
            )
        raise Error(
            "internal_server_error",
            "Error converting storage",
        )
    return jsonify(new_storage.id)


@app.route("/api/v3/storages/status", methods=["PUT"])
@is_admin
def storage_update_status(payload):
    if not request.is_json:
        raise Error(
            description="No JSON in body request with storage ids",
        )
    request_json = request.get_json()
    storages_ids = request_json.get("ids")
    if not storages_ids:
        raise Error(
            description="Storage ids required",
        )
    for storage_id in storages_ids:
        check_storage_existence_and_permissions(payload, storage_id)
        storage = Storage(storage_id)
        storage.check_backing_chain(user_id=payload.get("user_id"))

    return jsonify({})


@app.route("/api/v3/storages/status/<status>", methods=["PUT"])
@is_admin
def storage_update_by_status(payload, status):
    storages_ids = get_disks_ids_by_status(status=status)
    for storage_id in storages_ids:
        storage = Storage(storage_id)
        storage.check_backing_chain(user_id=payload.get("user_id"))

    return jsonify({})
