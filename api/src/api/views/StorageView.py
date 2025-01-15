# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import time

from flask import jsonify, request
from isardvdi_common.api_exceptions import Error
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.domain import Domain
from isardvdi_common.storage import Storage, get_storage_id_from_path, new_storage_dict
from isardvdi_common.storage_pool import StoragePool
from isardvdi_common.task import Task
from isardvdi_protobuf_old.queue.storage.v1 import ConvertRequest, DiskFormat
from rethinkdb import RethinkDB

from ..libv2.validators import _validate_item

r = RethinkDB()

from api import app

from ..libv2.api_desktop_events import desktops_stop

MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024

from ..libv2.api_admin import ApiAdmin
from ..libv2.api_desktops_persistent import ApiDesktopsPersistent
from ..libv2.api_storage import (
    _check_domains_status,
    get_disks_ids_by_status,
    get_storage_category,
    get_storage_derivatives,
    get_user_ready_disks,
    parse_disks,
)
from ..libv2.quotas import Quotas

desktops = ApiDesktopsPersistent()
quotas = Quotas()
from .decorators import (
    allowed_deployment_action,
    has_token,
    is_admin,
    is_admin_or_manager,
    is_not_user,
)

admins = ApiAdmin()

from ..libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)


def get_storage(payload, storage_id):
    """
    Check storage existence.

    :param storage_id: Storage ID
    :type storage_id: str
    """
    if not Storage.exists(storage_id):
        raise Error(error="not_found", description=f"Storage {storage_id} not found")

    storage = Storage(storage_id)
    if payload["role_id"] == "admin":
        return storage

    if storage.user_id is None:
        raise Error(
            "not_found",
            f"Storage {storage_id} missing user_id",
            "not_found",
        )

    if storage.user_id == payload["user_id"]:
        return storage

    if payload["role_id"] == "manager":
        with app.app_context():
            storage_category_id = (
                r.table("users")
                .get(storage.user_id)
                .pluck("category")["category"]
                .run(db.conn)
            )
        if storage_category_id == payload["category_id"]:
            return storage

    raise Error(
        "forbidden",
        "Not enough access rights for this user_id " + payload["user_id"],
        "forbidden",
    )


def get_storage_pool(storage_pool_id):
    """
    Check storage pool existence.

    :param storage_pool_id: Storage Pool ID
    :type storage_pool_id: str
    """
    if not StoragePool.exists(storage_pool_id):
        raise Error(
            error="not_found",
            description=f"Storage pool {storage_pool_id} not found",
        )
    return StoragePool(storage_pool_id)


def get_storage_pool_by_path(path):
    """
    Get storage pool by path.

    :param path: Path
    :type path: str
    """
    storage_pools = StoragePool.get_by_path(path)
    if not storage_pools:
        raise Error(
            error="not_found",
            description=f"Storage pool for path {path} not found",
        )
    return storage_pools[0]


def storage_status(storage, status):
    if storage.status != status:
        raise Error(
            error="precondition_required",
            description=f"Storage {storage.id} status is not ready ({storage.status}). Can't execute operation",
            description_code="storage_not_ready",
        )


def not_storage_children(storage):
    if storage.children:
        raise Error(
            error="conflict",
            description=f"Storage {storage.id} used as backing file for {len([storage.id for storage in storage.children])} storages. Can't execute operation",
        )


def get_queue_from_storage_pools(storage_pool_origin, storage_pool_destination):
    if storage_pool_origin == storage_pool_destination:
        queue = storage_pool_origin.id
    else:
        storage_pool_ids = [storage_pool_origin.id, storage_pool_destination.id]
        storage_pool_ids.sort()
        queue = ":".join(storage_pool_ids)
    return queue


def check_task_priority(payload, priority):
    """
    Check task priority.

    :param payload: Data from JWT
    :type payload: dict
    :param priority: Task priority
    :type priority: str
    """
    if payload["role_id"] != "admin":
        priority = "low"
    else:
        if priority not in ["low", "default", "high"]:
            raise Error(
                error="bad_request",
                description=f"Priority must be low, default or high",
            )
    return priority


@app.route("/api/v3/storage/<path:storage_id>/status/maintenance", methods=["PUT"])
@has_token
def storage_maintenance(payload, storage_id):
    """
    Endpoint to set a storage to maintenance status.

    :param payload: Data from JWT
    :type payload: dict
    :return: Storage ID
    :rtype: Set with Flask response values and data in JSON
    """
    params = request.get_json(force=True)
    action = params.get("action", "system maintenance")
    storage = get_storage(payload, storage_id)
    storage.set_maintenance(storage_id, action)
    return jsonify(storage.id)


@app.route("/api/v3/storage/<path:storage_id>/status/ready", methods=["PUT"])
@has_token
def storage_ready(payload, storage_id):
    """
    Endpoint to set a storage to ready status.

    :param payload: Data from JWT
    :type payload: dict
    :return: Storage ID
    :rtype: Set with Flask response values and data in JSON
    """
    storage = get_storage(payload, storage_id)
    storage.set_ready()
    return jsonify(storage.id)


@app.route(
    "/api/v3/storage/<path:storage_id>/storage_pool/<path:storage_pool_id>",
    methods=["PUT"],
)
@has_token
def storage_set_storage_pool(payload, storage_id, storage_pool_id):
    """
    Endpoint to set a storage to a storage pool.

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :param storage_pool_id: Storage Pool ID
    :type storage_pool_id: str
    :return: Storage ID
    :rtype: Set with Flask response values and data in JSON
    """
    storage = get_storage(payload, storage_id)
    storage_pool = get_storage_pool(storage_pool_id)
    storage.set_storage_pool(storage_pool)
    return jsonify(storage.id)


@app.route("/api/v3/storage/<path:storage_id>", methods=["GET"])
@has_token
def get_storage_id(payload, storage_id):
    """
    Get storage status.

    :param storage_id: Storage ID
    :type storage_id: str
    :return: Storage object
    """
    return get_storage(payload, storage_id)


@app.route("/api/v3/storage/priority/<priority>", methods=["POST"])
# TODO: Quotas should be implemented before open this endpoint
# @has_token
@is_admin
def create_storage(payload, priority="low"):
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
    parent = ""
    if not "parent" in request_json and not "user_id" in request_json:
        raise Error(
            error="bad_request",
            description="Must provide a parent storage or a user ID",
        )
    if "parent" in request_json:
        parent = get_storage(payload, request_json.get("parent"))
        if parent.status != "ready":
            raise Error(
                error="precondition_required",
                description="Storage not ready",
                description_code="storage_not_ready",
            )

        parent_args = {
            "parent_path": parent.path,
            "parent_type": parent.type,
        }
    if payload["role_id"] != "admin":
        priority = "low"
    else:
        if priority not in ["low", "default", "high"]:
            raise Error(
                error="bad_request",
                description=f"Priority must be low, default or high",
            )

    if request.get_json().get("storage_pool"):
        storage_pool = StoragePool(request.get_json().get("storage_pool"))
        if not storage_pool.paths[request_json.get("usage_type")]:
            storage_pool = StoragePool(DEFAULT_STORAGE_POOL_ID)
    else:
        if parent:
            storage_pool = StoragePool.get_best_for_action(
                "create", parent.directory_path
            )
        else:
            if request.get_json().get("user_id"):
                storage_pool = StoragePool.get_by_user_kind(
                    request.get_json().get("user_id"),
                    request.get_json().get("usage_type"),
                )

            else:
                storage_pool = StoragePool.get_best_for_action("create")

    category = ""
    if "parent" in request_json and storage_pool.id != DEFAULT_STORAGE_POOL_ID:
        category = get_storage_category(parent) + "/"

    usage_path = storage_pool.get_usage_path(request_json.get("usage_type"))
    user_id = (
        request.get_json().get("user_id")
        if request.get_json().get("user_id")
        else payload.get("user_id")
    )

    quota = quotas.get_applied_quota(user_id).get("quota")
    if quota and quota.get("desktops_disk_size") < int(request_json.get("size")[:-1]):
        raise Error("bad_request", "Disk size quota exceeded")

    storage = Storage(
        status="maintenance",
        user_id=user_id,
        type=request_json.get("storage_type"),
        parent=request_json.get("parent"),
        directory_path=f"{storage_pool.mountpoint}/{category}{usage_path}",
        status_logs=[{"time": int(time.time()), "status": "created"}],
        perms=["r", "w"] if request_json.get("usage_type") != "template" else ["r"],
    )

    try:
        storage.create_task(
            user_id=storage.user_id,
            queue=f"storage.{storage_pool.id}.{priority}",
            task="create",
            job_kwargs={
                "kwargs": {
                    "storage_path": storage.path,
                    "storage_type": storage.type,
                    "size": request_json.get("size"),
                    **parent_args,
                },
            },
            dependents=[
                {
                    "queue": f"storage.{storage_pool.id}.default",
                    "task": "qemu_img_info_backing_chain",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_id": storage.id,
                            "storage_path": storage.path,
                        }
                    },
                    "dependents": [
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
                                            },
                                        },
                                    },
                                }
                            ],
                        }
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
            "Error creating storage",
        )
    return jsonify(storage.id)


@app.route("/api/v3/storage/<path:storage_id>/parents", methods=["GET"])
@is_admin_or_manager
def storage_parents(payload, storage_id):
    storage = get_storage(payload, storage_id)
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
            for storage in [storage] + storage.parents
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
    storage = get_storage(payload, storage_id)
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
    storage = get_storage(payload, storage_id)

    return jsonify(
        {
            "id": storage.delete(
                payload.get("user_id"),
            )
        }
    )


@app.route(
    "/api/v3/storage/virt-win-reg/<path:storage_id>/priority/<priority>",
    methods=["PUT"],
)
@has_token
def storage_virt_win_reg(payload, storage_id, priority="low"):
    """
    Endpoint to apply a registry patch to a storage qcow2

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    # Get registry patch from request body
    if not request.is_json:
        raise Error(
            description="No JSON in body request with registry patch",
        )
    request_json = request.get_json()

    registry_patch = request_json.get("registry_patch")
    if not registry_patch:
        raise Error(
            description="registry_patch must be specified in JSON of body request",
        )
    if len(registry_patch.encode()) > MAX_FILE_SIZE_BYTES:
        raise Error(
            description="The registry file is too large, exceeding the 1MB maximum"
        )

    if payload["role_id"] != "admin":
        priority = "low"
    else:
        if priority not in ["low", "default", "high"]:
            raise Error(
                error="bad_request",
                description=f"Priority must be low, default or high",
            )

    storage = get_storage(payload, storage_id)

    return jsonify(
        {
            "id": storage.virt_win_reg(
                registry_patch,
                priority,
            )
        }
    )


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
    storage = get_storage(payload, storage_id)
    try:
        storage.create_task(
            user_id=payload.get("user_id"),
            queue=f"storage.{StoragePool.get_best_for_action('qemu_img_info', path=storage.directory_path).id}.default",
            task="qemu_img_info",
            job_kwargs={
                "kwargs": {
                    "storage_id": storage.id,
                    "storage_path": storage.path,
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
    storage = get_storage(payload, storage_id)
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
    storage = get_storage(payload, storage_id)
    try:
        storage.create_task(
            user_id=payload.get("user_id"),
            queue=f"storage.{StoragePool.get_best_for_action('check_existence', path=storage.directory_path).id}.default",
            task="check_existence",
            job_kwargs={
                "kwargs": {
                    "storage_id": storage.id,
                    "storage_path": storage.path,
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
    storage = get_storage(payload, storage_id)

    return jsonify(
        {
            "id": storage.update_parent(
                payload.get("user_id"),
            )
        }
    )


@app.route(
    "/api/v3/storage/<path:storage_id>/move/by-path",
    methods=["PUT"],
)
@is_admin
def storage_move_by_path(payload, storage_id):
    """
    Endpoint to move a storage to another path with storage specifications as JSON in body request.

    Storage move action specification in JSON:
    {
        "dest_path": "Absolute path without trailing slash to move the storage",
        "priority": "low, default or high", # Optional
    }

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """

    if not request.is_json:
        raise Error(
            description="No JSON in body request. dest_path must be specified, priority is optional",
        )

    request_json = request.get_json()

    if not request_json.get("dest_path"):
        raise Error(
            description="Incorrect JSON of body request: dest_path must be specified",
        )

    path = request_json.get("dest_path")
    if not path.startswith("/"):
        path = f"/{path}"
    priority = check_task_priority(payload, request_json.get("priority", "default"))

    storage = get_storage(payload, storage_id)
    if storage.directory_path == path:
        raise Error(
            error="bad_request",
            description=f"Storage {storage.id} already in destination path {path}, no need to execute operation",
        )

    # TODO: make it less hardcoded
    destination_path = f"{path}/{storage.id}.{storage.type}"

    try:
        return jsonify(
            {
                "id": storage.mv(
                    path,
                    priority,
                )
            }
        )
    except Exception as e:
        raise Error(*e.args)


@app.route(
    "/api/v3/storage/<path:storage_id>/rsync/to-path",
    methods=["PUT"],
)
@is_admin
def storage_rsync_to_path(payload, storage_id):
    """
    Endpoint to move a storage to another path with storage specifications as JSON in body request.

    Storage move action specification in JSON:
    {
        "destination_path": "Absolute path without trailing slash to rsync the storage",
        "bwlimit": "Bandwidth limit in KBytes/s", # Optional
        "remove_source_file": "Boolean to remove source file after rsync", # Optional
        "priority": "low, default or high", # Optional
    }

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    # Check parameters
    data = request.get_json()
    data["storage_id"] = storage_id
    data = _validate_item("storage_rsync_by_path", data)
    storage = get_storage(payload, storage_id)
    storage_status(storage, "ready")
    not_storage_children(storage)
    storage_pool_destination = get_storage_pool_by_path(data["destination_path"])

    # Prepare data
    destination_path = storage.path_in_pool(storage_pool_destination)
    if destination_path is None:
        raise Error(
            error="not_found",
            description="No pool found with the usage, it was not found to execute rsync operation",
        )

    # Create task
    return jsonify(
        {
            "id": storage.rsync(
                payload["user_id"],
                destination_path,
                data["bwlimit"],
                data["remove_source_file"],
                data["priority"],
            )
        }
    )


@app.route(
    "/api/v3/storage/<path:storage_id>/rsync/to-storage-pool",
    methods=["PUT"],
)
@is_admin
def storage_rsync_to_storage_pool(payload, storage_id):
    """
    Endpoint to move a storage to another storage pool with storage specifications as JSON in body request.

    Storage move action specification in JSON:
    {
        "destination_storage_pool_id": "Storage Pool ID to rsync the storage",
        "bwlimit": "Bandwidth limit in KBytes/s", # Optional
        "remove_source_file": "Boolean to remove source file after rsync", # Optional
        "priority": "low, default or high", # Optional
    }

    :param payload: Data from JWT
    :type payload: dict: {"destination_storage_pool_id": "Storage Pool ID to rsync the storage", "bwlimit": "Bandwidth limit in KBytes/s", "remove_source_file": "Boolean to remove source file after rsync", "priority": "low, default or high",}
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    # Check parameters
    data = request.get_json()
    data["storage_id"] = storage_id
    data = _validate_item("storage_rsync_by_storage_pool", data)

    storage = get_storage(payload, storage_id)

    if not StoragePool.exists(data["destination_storage_pool_id"]):
        raise Error(
            error="not_found",
            description=f"Storage pool {data['destination_storage_pool_id']} not found",
        )
    destination_path = storage.path_in_pool(
        StoragePool(data["destination_storage_pool_id"])
    )
    if destination_path is None:
        raise Error(
            error="not_found",
            description="No pool found with the usage, it was not found to execute rsync operation",
        )
    if storage.path == destination_path:
        raise Error(
            error="bad_request",
            description=f"Storage {storage.id} already in destination pool path {destination_path} to execute rsync operation",
        )
    # Create task
    return jsonify(
        {
            "id": storage.rsync(
                payload["user_id"],
                destination_path,
                data["bwlimit"],
                data["remove_source_file"],
                data["priority"],
            )
        }
    )


@app.route(
    "/api/v3/storage/<path:storage_id>/path/<path:path>/priority/<priority>/<method>",
    methods=["PUT"],
)
@has_token
def storage_move(payload, storage_id, path, priority="low", method="mv"):
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
    # Check parameters
    if payload["role_id"] != "admin":
        priority = "low"
    else:
        if priority not in ["low", "default", "high"]:
            raise Error(
                error="bad_request",
                description=f"Priority {priority} must be low, default or high",
            )
    if method not in ["mv", "rsync"]:
        raise Error(
            error="bad_request",
            description=f"Method must be mv or rsync",
        )

    # Storage move checks
    storage = get_storage(payload, storage_id)
    storage_derivatives = get_storage_derivatives(storage_id)
    if len(storage_derivatives) > 1:
        raise Error(
            "precondition_required",
            "Unable to move storage with derivatives",
            description_code="storage_has_derivatives",
        )

    path = f"/{path}"  # Why this?? if not path.startswith("/"): ??
    storage_pool_destination = StoragePool.get_best_for_action("move", path=path)
    if storage_pool_destination is None:
        raise Error(
            error="not_found",
            description=f"Destination storage pool for path {path} not found to execute move operation",
        )

    if storage.directory_path == path:
        raise Error(
            error="bad_request",
            description=f"Storage {storage.id} already in destination pool path {path} to execute move operation",
        )
    if storage.status != "ready":
        raise Error(
            error="precondition_required",
            description=f"Storage {storage.id} not ready ({storage.status}) to execute move operation",
            description_code="storage_not_ready",
        )
    if storage.children:
        raise Error(
            error="conflict",
            description=f"Storage {storage.id} used as backing file for {', '.join([storage.id for storage in storage.children])} to execute move operation",
        )

    # We can create move action
    try:
        match method:
            case "rsync":
                return storage.rsync(
                    user_id=payload["user_id"],
                    destination_path=f"{path}/{storage.id}.{storage.type}",
                    priority=priority,
                    timeout=3600,
                )
            case "mv":
                return storage.mv(
                    destination_path=f"{path}/{storage.id}.{storage.type}",
                    priority=priority,
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
    "/api/v3/storage/<path:storage_id>/convert/<new_storage_type>/priority/<priority>",
    methods=["POST"],
)
@app.route(
    "/api/v3/storage/<path:storage_id>/convert/<new_storage_type>/<new_storage_status>/priority/<priority>",
    methods=["POST"],
)
@app.route(
    "/api/v3/storage/<path:storage_id>/convert/<new_storage_type>/compress/priority/<priority>",
    methods=["POST"],
)
@app.route(
    "/api/v3/storage/<path:storage_id>/convert/<new_storage_type>/<new_storage_status>/compress/priority/<priority>",
    methods=["POST"],
)
@has_token
def storage_convert(
    payload,
    storage_id,
    new_storage_type,
    new_storage_status="ready",
    compress=None,
    priority="low",
):
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
    if new_storage_status not in ["ready", "downloadable"]:
        raise Error(
            error="bad_request",
            description=f"Storage status {new_storage_status} not supported",
            description_code="status_not_ready",
        )
    if not _check_domains_status(storage_id):
        raise Error(
            "precondition_required",
            "All desktops must be 'Stopped' for storage operations.",
            description_code="desktops_not_stopped",
        )
    if payload["role_id"] != "admin":
        priority = "low"

    origin_storage = get_storage(payload, storage_id)

    if len(get_storage_derivatives(storage_id)) > 1:
        raise Error(
            "precondition_required", "Unable to convert storage with derivatives"
        )
    origin_storage.set_maintenance("convert")
    compress = request.url_rule.rule.endswith("/compress")
    new_storage = Storage(
        user_id=origin_storage.user_id,
        status="creating",
        type=new_storage_type.lower(),
        directory_path=origin_storage.directory_path,
        converted_from=origin_storage.id,
    )
    try:
        origin_storage.create_task(
            user_id=new_storage.user_id,
            queue=f"storage.{StoragePool.get_best_for_action('convert', path=origin_storage.directory_path).id}.{priority}",
            task="convert",
            job_kwargs={
                "timeout": 4096,
                "args": [
                    ConvertRequest(
                        source_disk_path=origin_storage.path,
                        dest_disk_path=new_storage.path,
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
                                    new_storage_status: {
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
        storage = get_storage(payload, storage_id)
        storage.check_backing_chain(user_id=payload.get("user_id"))

    return jsonify({})


@app.route("/api/v3/storages/status/<status>", methods=["PUT"])
@is_admin
def storage_update_by_status(payload, status):
    storages_ids = get_disks_ids_by_status(status=status)
    for storage_id in storages_ids:
        storage = get_storage(payload, storage_id)
        storage.check_backing_chain(user_id=payload.get("user_id"))
    return jsonify({})


@app.route(
    "/api/v3/storage/<path:storage_id>/priority/<priority>/increase/<int:increment>",
    methods=["PUT"],
)
@is_not_user
def storage_increase_size(payload, storage_id, increment, priority="low"):
    storage = get_storage(payload, storage_id)
    quota = quotas.get_applied_quota(storage.user_id).get("quota")
    if quota and (
        quota.get("desktops_disk_size")
        < (
            getattr(storage, "qemu-img-info")["virtual-size"] / 1024 / 1024 / 1024
            - int(increment)
        )
    ):
        raise Error("bad_request", "Disk size quota exceeded")

    if payload["role_id"] != "admin":
        priority = "low"
    if priority not in ["low", "default", "high"]:
        raise Error(
            description="priority should be low, default or high",
        )

    return jsonify(
        {
            "id": storage.increase_size(
                increment,
                priority,
            )
        }
    )


@app.route("/api/v3/storage/<path:storage_id>/stop", methods=["PUT"])
@is_admin_or_manager
def storage_stop_all_desktops(payload, storage_id):
    storage = get_storage(payload, storage_id)
    domains = [domain.id for domain in storage.domains if domain.kind == "desktop"]
    desktops_stop(domains, force=True)
    return jsonify({}), 200


@app.route("/api/v3/storage/<path:storage_id>/has_derivatives", methods=["GET"])
@is_admin_or_manager
def storage_has_derivatives(payload, storage_id):
    storage = get_storage(payload, storage_id)
    return jsonify({"derivatives": len(storage.children)}), 200


@app.route("/api/v3/storage/<path:storage_id>/abort_operations", methods=["PUT"])
@has_token
def storage_abort(payload, storage_id):
    storage = get_storage(payload, storage_id)

    # storage_domains = get_storage_derivatives(storage_id)
    return jsonify(
        {
            "id": storage.abort_operations(
                payload.get("user_id"),
            )
        }
    )


@app.route("/api/v3/domain/<domain_id>/recreate_disk", methods=["POST"])
@has_token
def domain_recreate_disk(payload, domain_id):
    """
    Endpoint to recreate a domain disk.

    :param payload: Data from JWT
    :type payload: dict
    :param domain_id: Domain ID
    :type domain_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    allowed_deployment_action(payload, domain_id, "recreate")
    if not Domain.exists(domain_id):
        raise Error(
            "not_found",
            f"Domain {domain_id} not found",
        )
    storage_id = Domain(domain_id).storages[0].id
    return recreate_storage(payload, storage_id)


@app.route("/api/v3/storage/<path:storage_id>/recreate", methods=["POST"])
@has_token
def storage_recreate_disk(payload, storage_id):
    """
    Endpoint to recreate a storage with the same specifications and parent.

    Storage specifications in JSON:
    {
        "user_id": "User ID",
        "priority": "low, default or high",
    }

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Storage ID
    :rtype: Set with Flask response values and data in JSON
    """
    return recreate_storage(payload, storage_id)


def recreate_storage(payload, storage_id, domain_id=None):
    storage = get_storage(payload, storage_id)
    if domain_id is None:
        if len(storage.domains) > 1:
            raise Error(
                "precondition_required",
                "Unable to recreate storage with more than one domain attached",
            )
        domain_id = storage.domains[0].id if len(storage.domains) == 1 else None
    if storage.parent:
        if not Storage.exists(storage.parent):
            raise Error(
                error="precondition_required",
                description="Storage parent missing",
                description_code="storage_has_no_parent",
            )
        storage_parent = Storage(storage.parent)
        if storage_parent.status != "ready":
            raise Error(
                error="precondition_required",
                description="Storage parent not ready",
                description_code="storage_parent_not_ready",
            )
        parent_args = {
            "parent_path": storage_parent.path,
            "parent_type": storage_parent.type,
        }
    else:
        storage_parent = None
        parent_args = {}
    storage_pool = StoragePool.get_best_for_action("delete", storage.directory_path)

    if request.is_json:
        request_json = request.get_json()
    else:
        request_json = {}

    priority = request_json.get("priority", "default")
    if payload["role_id"] != "admin":
        priority = "low"
    else:
        if priority not in ["low", "default", "high"]:
            raise Error(
                error="bad_request",
                description=f"Priority must be low, default or high",
            )

    storage.set_maintenance("recreate")

    status_logs = storage.status_logs
    status_logs.append(
        {"time": int(time.time()), "status": f"recreated from {storage_id}"}
    )

    new_storage = new_storage_dict(
        storage.user_id,
        storage.pool_usage,
        storage_parent.id if storage.parent else None,
    )
    new_storage_path = str(
        new_storage["directory_path"]
        + "/"
        + new_storage["id"]
        + "."
        + new_storage["type"]
    )
    new_storage["status_logs"] = status_logs
    new_storage_pool = StoragePool.get_best_for_action(
        "create", new_storage["directory_path"]
    )

    try:
        task = Task(
            user_id=storage.user_id,
            queue=f"storage.{new_storage_pool.id}.{priority}",
            task="create",
            job_kwargs={
                "kwargs": {
                    "storage_path": new_storage_path,
                    "storage_type": new_storage["type"],
                    **parent_args,
                },
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "storage_add",
                    "job_kwargs": {
                        "kwargs": new_storage,
                    },
                    "dependents": [
                        (
                            {
                                "queue": f"core",
                                "task": "domain_change_storage",
                                "job_kwargs": {
                                    "kwargs": {
                                        "domain_id": domain_id,
                                        "storage_id": new_storage["id"],
                                    },
                                },
                            }
                            if domain_id
                            else None
                        ),
                        {
                            "queue": f"storage.{new_storage_pool.id}.{priority}",
                            "task": "qemu_img_info_backing_chain",
                            "job_kwargs": {
                                "kwargs": {
                                    "storage_id": new_storage["id"],
                                    "storage_path": new_storage_path,
                                }
                            },
                            "dependents": [
                                {
                                    "queue": "core",
                                    "task": "storage_update",
                                },
                                {
                                    "queue": f"storage.{storage_pool.id}.{priority}",
                                    "task": "delete",
                                    "job_kwargs": {
                                        "kwargs": {
                                            "path": storage.path,
                                        },
                                    },
                                },
                            ],
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
            "Error creating storage",
        )

    return (
        json.dumps(
            {
                "old_id": storage_id,
                "new_id": storage.id,
            }
        ),
        200,
        {"Content-Type": "application/json"},
    )


def get_storage_statuses(storage):
    domains = storage.domains
    return {
        "id": storage.id,
        "status": storage.status,
        "parent": storage.parent,
        "domains": [
            {
                "id": domain.id,
                "status": domain.status,
                "kind": domain.kind,
            }
            for domain in domains
        ],
    }


@app.route("/api/v3/storage/<path:storage_id>/statuses", methods=["GET"])
@has_token
def storage_statuses(payload, storage_id):
    storage = get_storage(payload, storage_id)
    return jsonify(storage.statuses)


@app.route("/api/v3/storage/path/statuses", methods=["POST"])
@has_token
def storage_path_statuses(payload):
    if not request.json["path"]:
        raise Error(
            description="Path query parameter is required",
        )
    storage = get_storage(get_storage_id_from_path(request.json["path"]))
    return jsonify(storage.statuses)
