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
from isardvdi_common.storage import Storage, get_storage_id_from_path
from isardvdi_common.storage_pool import StoragePool
from isardvdi_common.task import Task
from rethinkdb import RethinkDB

from ..libv2.validators import _validate_item

r = RethinkDB()

from api import app

from ..libv2.api_desktop_events import desktops_stop

MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024

from ..libv2.api_admin import ApiAdmin
from ..libv2.api_desktops_persistent import ApiDesktopsPersistent
from ..libv2.api_notify import notify_admin
from ..libv2.api_storage import (
    _check_domains_status,
    get_disks_ids_by_status,
    get_storage_category,
    get_storage_derivatives,
    get_storages_with_uuid,
    get_storages_with_uuid_status,
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
    ownsDomainId,
    ownsUserId,
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

    owns_domains = [ownsDomainId(payload, domain.id) for domain in storage.domains]
    if any(owns_domains):
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


def check_task_retry(payload, retry):
    """
    Check task priority.

    :param payload: Data from JWT
    :type payload: dict
    :param retry: Number of retries for the task
    :type retry: str
    """
    if payload["role_id"] != "admin" or retry is None:
        retry = 0
    else:
        if not isinstance(retry, int):
            try:
                retry = int(retry)
            except ValueError:
                raise Error(
                    error="bad_request",
                    description="Retry should be an integer between 0 and 5",
                )
        if retry < 0 or retry > 5:
            raise Error(
                error="bad_request",
                description="Retry should be an integer between 0 and 5",
            )
    return retry


@app.route("/api/v3/storage/<path:storage_id>/status/maintenance", methods=["PUT"])
@is_admin
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
@is_admin
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
@is_admin
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
@is_admin
def create_storage(payload, priority="low"):
    """
    Endpoint to create a storage with storage specifications as JSON in body request.

    Storage specifications in JSON:
    {
        "usage": "Usage: desktop, template",
        "storage_type": "Disk format of the new storage: qcow2, vmdk",
        "parent": "Storage ID to be used as backing file",
        "size": "string with the size of new storage like qemu-img command",
        "user_id": "User ID of the owner of the new storage. If not specified, the user_id from JWT is used",
    }

    :param payload: Data from JWT
    :type payload: dict
    :return: Storage ID
    :rtype: Set with Flask response values and data in JSON
    """
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
        )
    data = _validate_item("storage_create", data)

    if payload["role_id"] != "admin":
        priority = "low"
    else:
        if priority not in ["low", "default", "high"]:
            raise Error(
                error="bad_request",
                description=f"Priority must be low, default or high",
            )

    ownsUserId(payload, data.get("user_id", payload["user_id"]))
    user_id = data.get("user_id", payload["user_id"])

    quota = quotas.get_applied_quota(user_id).get("quota")
    if quota and quota.get("desktops_disk_size") < int(data["size"][:-1]):
        raise Error("bad_request", "Disk size quota exceeded")

    try:
        storage, task_id = Storage().create_new_storage(
            user_id=user_id,
            pool_usage=data["usage"],
            parent_id=data["parent"],
            storage_type=data["storage_type"],
            size=str(data["size"]),
            priority=priority,
        )
    except Exception as e:
        raise Error(*e.args)

    return jsonify(
        {
            "storage_id": storage.id,
            "task_id": task_id,
        }
    )


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
@is_admin_or_manager
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
@is_admin
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

    try:
        return jsonify(
            {
                "task_id": storage.task_delete(
                    payload.get("user_id"),
                )
            }
        )
    except Exception as e:
        raise Error(*e.args)


@app.route(
    "/api/v3/storage/virt-win-reg/<path:storage_id>/priority/<priority>",
    methods=["PUT"],
)
@is_admin
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

    retry = check_task_retry(payload, request_json.get("retry", 0))

    storage = get_storage(payload, storage_id)

    try:
        return jsonify(
            {
                "task_id": storage.virt_win_reg(
                    payload["user_id"],
                    registry_patch,
                    priority,
                    retry=retry,
                )
            }
        )
    except Exception as e:
        raise Error(*e.args)


@app.route(
    "/api/v3/storage/sparsify/<path:storage_id>/priority/<priority>", methods=["PUT"]
)
@app.route(
    "/api/v3/storage/sparsify/<path:storage_id>/priority/<priority>/retry/<int:retry>",
    methods=["PUT"],
)
@is_admin
def storage_sparsify(payload, storage_id, priority="low", retry=0):
    """
    Endpoint to sparsify a storage qcow2

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    if priority not in ["low", "default", "high"]:
        raise Error(
            error="bad_request",
            description=f"Priority must be low, default or high",
        )
    retry = check_task_retry(payload, retry)

    storage = get_storage(payload, storage_id)

    try:
        return jsonify(
            {
                "task_id": storage.sparsify(
                    payload.get("user_id"),
                    priority=priority,
                    secondary_priority="high",
                    retry=retry,
                )
            }
        )
    except Exception as e:
        raise Error(*e.args)


@app.route("/api/v3/storages/sparsify", methods=["PUT"])
@is_admin
def storages_sparsifys(payload):
    if not request.is_json:
        raise Error(
            error="bad_request",
            description="No JSON in body request with storage ids",
        )
    request_json = request.get_json()
    storages_ids = request_json.get("ids")
    if not storages_ids:
        raise Error(
            error="bad_request",
            description="Storage ids required",
        )
    for storage_id in storages_ids:
        try:
            storage = get_storage(payload, storage_id)
            storage.sparsify(
                payload.get("user_id"),
                priority="default",
                secondary_priority="high",
            )
        except:
            notify_admin(
                payload["user_id"],
                "Error Sparsifying storage",
                f"There was an error creating a task for {storage_id}",
                type="error",
            )

    return jsonify({})


@app.route("/api/v3/storages/sparsify/<status>", methods=["PUT"])
@is_admin
def storages_sparsify_by_status(payload, status):
    storages_ids = get_disks_ids_by_status(status=status)

    for storage_id in storages_ids:
        try:
            storage = get_storage(payload, storage_id)
            storage.sparsify(
                payload.get("user_id"),
                priority="default",
                secondary_priority="high",
            )
        except:
            notify_admin(
                payload["user_id"],
                "Error Sparsifying storage",
                f"There was an error creating a task for {storage_id}",
                type="error",
            )

    return jsonify({})


@app.route(
    "/api/v3/storage/disconnect/<path:storage_id>/priority/<priority>",
    methods=["PUT"],
)
@app.route(
    "/api/v3/storage/disconnect/<path:storage_id>/priority/<priority>/retry/<int:retry>",
    methods=["PUT"],
)
@is_admin
def storage_disconnect(payload, storage_id, priority="low", retry=0):
    """
    Endpoint to disconnect a storage from its backing chain

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    if payload["role_id"] != "admin":
        priority = "low"
    else:
        if priority not in ["low", "default", "high"]:
            raise Error(
                error="bad_request",
                description=f"Priority must be low, default or high",
            )

    retry = check_task_retry(payload, retry)

    storage = get_storage(payload, storage_id)

    try:
        return jsonify(
            {
                "task_id": storage.disconnect_chain(
                    priority,
                    retry=retry,
                )
            }
        )
    except Exception as e:
        raise Error(*e.args)


@app.route("/api/v3/storage/<path:storage_id>/check_backing_chain", methods=["PUT"])
@is_admin_or_manager
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
                "task_id": storage.mv(
                    payload["user_id"],
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
    try:
        return jsonify(
            {
                "task_id": storage.rsync(
                    payload["user_id"],
                    destination_path,
                    data["bwlimit"],
                    data["remove_source_file"],
                    data["priority"],
                )
            }
        )
    except Exception as e:
        raise Error(*e.args)


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
    try:
        return jsonify(
            {
                "task_id": storage.rsync(
                    payload["user_id"],
                    destination_path,
                    data["bwlimit"],
                    data["remove_source_file"],
                    data["priority"],
                )
            }
        )
    except Exception as e:
        raise Error(*e.args)


@app.route(
    "/api/v3/storage/<path:storage_id>/path/<path:path>/priority/<priority>/<method>",
    methods=["PUT"],
)
@is_admin
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
                    user_id=payload["user_id"],
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


@app.route("/api/v3/storage/<path:storage_id>/convert", methods=["POST"])
@is_admin
def storage_convert(payload, storage_id):
    """
    Endpoint that creates a Task to convert an storage to a new storage.

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Task ID and new storage ID
    :rtype: Set with Flask response values and data in JSON
    """
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
        )
    data = _validate_item("storage_convert", data)
    data["priority"] = check_task_priority(payload, data["priority"])

    origin_storage = get_storage(payload, storage_id)
    origin_storage.set_maintenance("convert")

    new_storage = Storage(
        user_id=origin_storage.user_id,
        status="creating",
        type=data["new_storage_type"].lower(),
        directory_path=origin_storage.directory_path,
        converted_from=origin_storage.id,
    )

    try:
        return jsonify(
            {
                "new_storage_id": new_storage.id,
                "task_id": origin_storage.convert(
                    user_id=payload["user_id"],
                    new_storage=new_storage,
                    new_storage_type=data["new_storage_type"],
                    new_storage_status=data["new_storage_status"],
                    compress=data["compress"],
                    priority=data["priority"],
                ),
            }
        )
    except Exception as e:
        raise Error(*e.args)


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
        try:
            storage = get_storage(payload, storage_id)
            storage.check_backing_chain(user_id=payload.get("user_id"))
        except:
            notify_admin(
                payload["user_id"],
                "Error finding storage",
                f"There was an error creating a task for {storage_id}",
                type="error",
            )
    return jsonify({})


@app.route(
    "/api/v3/storage/<path:storage_id>/priority/<priority>/increase/<int:increment>",
    methods=["PUT"],
)
@app.route(
    "/api/v3/storage/<path:storage_id>/priority/<priority>/increase/<int:increment>/retry/<int:retry>",
    methods=["PUT"],
)
@is_not_user
def storage_increase_size(payload, storage_id, increment, priority="low", retry=0):
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
    retry = check_task_retry(payload, retry)

    try:
        return jsonify(
            {
                "task_id": storage.increase_size(
                    payload["user_id"],
                    increment,
                    priority,
                    retry=retry,
                )
            }
        )
    except Exception as e:
        raise Error(*e.args)


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

    task_agent_id = Task(storage.task).user_id
    try:
        ownsUserId(payload, task_agent_id)
    except:
        raise Error(
            "forbidden",
            "You are not authorized to cancel this operation as it was not initiated by you",
            description_code="operation_not_owned",
        )

    return jsonify(
        {
            "task_id": storage.abort_operations(
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
    if request.is_json:
        request_json = request.get_json()
    else:
        request_json = {}

    priority = request_json.get("priority", "default")
    priority = check_task_priority(payload, priority)

    retry = check_task_retry(payload, request_json.get("retry", 0))

    if not Domain.exists(domain_id):
        raise Error(
            "not_found",
            f"Domain {domain_id} not found",
        )
    allowed_deployment_action(payload, domain_id, "recreate")

    storage_id = Domain(domain_id).storages[0].id
    storage = get_storage(payload, storage_id)

    try:
        return jsonify(
            {
                "task_id": storage.recreate(
                    payload.get("user_id"),
                    domain_id,
                    priority=priority,
                    retry=retry,
                )
            }
        )
    except Exception as e:
        raise Error(*e.args)


@app.route("/api/v3/storage/<path:storage_id>/recreate", methods=["POST"])
@is_admin_or_manager
def storage_recreate_disk(payload, storage_id):
    """
    Endpoint to recreate a storage with the same specifications and parent.

    Storage specifications in JSON:
    {
        "user_id": "User ID",
        "priority": "low, default or high",
        "retry": "Number of retries for the task",
    }

    :param payload: Data from JWT
    :type payload: dict
    :param storage_id: Storage ID
    :type storage_id: str
    :return: Storage ID
    :rtype: Set with Flask response values and data in JSON
    """
    if request.is_json:
        request_json = request.get_json()
    else:
        request_json = {}

    priority = request_json.get("priority", "default")
    priority = check_task_priority(payload, priority)
    retry = check_task_retry(payload, request_json.get("retry", 0))

    storage = get_storage(payload, storage_id)
    if len(storage.domains) > 1:
        raise Error(
            "precondition_required",
            "Unable to recreate storage with more than one domain attached",
        )
    domain_id = storage.domains[0].id if len(storage.domains) == 1 else None

    try:
        return jsonify(
            {
                "task_id": storage.recreate(
                    payload.get("user_id"),
                    domain_id,
                    priority=priority,
                    retry=retry,
                )
            }
        )
    except Exception as e:
        raise Error(*e.args)


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
@is_admin
def storage_statuses(payload, storage_id):
    storage = get_storage(payload, storage_id)
    return jsonify(storage.statuses)


@app.route("/api/v3/storage/path/statuses", methods=["POST"])
@is_admin
def storage_path_statuses(payload):
    if not request.json["path"]:
        raise Error(
            description="Path query parameter is required",
        )
    storage = get_storage(get_storage_id_from_path(request.json["path"]))
    return jsonify(storage.statuses)


@app.route("/api/v3/storage/<path:storage_id>/find", methods=["GET"])
@is_admin
def storage_find(payload, storage_id):
    storage = get_storage(payload, storage_id)
    return jsonify(storage.find(payload.get("user_id")))


@app.route("/api/v3/storages/find", methods=["PUT"])
@is_admin
def storages_find(payload):
    if not request.is_json:
        raise Error(
            error="bad_request",
            description="No JSON in body request with storage ids",
        )
    request_json = request.get_json()
    storages_ids = request_json.get("ids")
    if not storages_ids:
        raise Error(
            error="bad_request",
            description="Storage ids required",
        )
    for storage_id in storages_ids:
        storage = get_storage(payload, storage_id)
        storage.find(payload.get("user_id"))

    return jsonify({})


@app.route("/api/v3/storages/find/<status>", methods=["PUT"])
@is_admin
def storages_find_by_status(payload, status):
    storages_ids = get_disks_ids_by_status(status=status)

    for storage_id in storages_ids:
        try:
            storage = get_storage(payload, storage_id)
            storage.find(payload.get("user_id"))
        except:
            notify_admin(
                payload["user_id"],
                "Error finding storage",
                f"There was an error creating a task for {storage_id}",
                type="error",
            )

    return jsonify({})


@app.route("/api/v3/storage/<path:storage_id>/storages_with_uuid", methods=["GET"])
@is_admin_or_manager
def storage_storages_with_uuid(payload, storage_id):
    storage = get_storage(payload, storage_id)
    return jsonify(storage.storages_with_uuid)


@app.route("/api/v3/storage/storages_with_uuid", methods=["GET"])
@app.route("/api/v3/storage/storages_with_uuid/<status>", methods=["GET"])
@is_admin_or_manager
def storage_all_storages_with_uuid(payload, status=None):
    return jsonify(
        get_storages_with_uuid(
            category_id=(
                payload["category_id"] if payload["role_id"] == "manager" else None
            ),
            status=status,
        )
    )


@app.route("/api/v3/storage/storages_with_uuid/status", methods=["GET"])
@is_admin_or_manager
def storage_storages_with_uuid_status(payload):
    return jsonify(
        get_storages_with_uuid_status(
            category_id=(
                payload["category_id"] if payload["role_id"] == "manager" else None
            )
        )
    )


@app.route("/api/v3/storage/<path:storage_id>/path", methods=["PUT"])
@is_admin_or_manager
def storage_set_path(payload, storage_id):
    if not request.is_json:
        raise Error(
            error="bad_request",
            description="No JSON in body request with storage ids",
        )
    data = request.get_json()
    if not data.get("path"):
        raise Error(
            error="bad_request",
            description="Path query parameter is required",
        )

    storage = get_storage(payload, storage_id)
    return jsonify(
        {
            "task_id": storage.set_path(
                payload.get("user_id"),
                request.json["path"],
                priority=check_task_priority(payload, data.get("priority", "default")),
                retry=check_task_retry(payload, data.get("retry", 0)),
            )
        }
    )


@app.route("/api/v3/storage/<path:storage_id>/path/", methods=["DELETE"])
@is_admin_or_manager
def storage_path_delete(payload, storage_id):
    if not request.is_json:
        raise Error(
            error="bad_request",
            description="No JSON in body request with storage ids",
        )
    data = request.get_json()
    if not data.get("path"):
        raise Error(
            error="bad_request",
            description="Path query parameter is required",
        )

    storage = get_storage(payload, storage_id)
    return jsonify(
        {
            "task_id": storage.delete_path(
                payload.get("user_id"),
                request.json["path"],
                priority=check_task_priority(payload, data.get("priority", "default")),
                retry=check_task_retry(payload, data.get("retry", 0)),
            )
        }
    )
