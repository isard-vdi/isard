import copy
import logging as log
import threading
import traceback
from time import sleep, time

from cachetools import TTLCache, cached
from isardvdi_common.api_exceptions import Error
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.domain import Domain
from rethinkdb import RethinkDB
from rethinkdb.errors import ReqlNonExistenceError

from api import app

from .flask_rethink import RDB

r = RethinkDB()


db = RDB(app)
db.init_app(app)

# Create the cache object
cache = TTLCache(maxsize=2000, ttl=10)


def get_document(table, item_id, keys=[], invalidate=False):
    try:
        if invalidate:
            invalidate_cache(table, item_id)
    except Exception as e:
        pass
    try:
        time_start = time()
        data = get_cached(table, item_id)
    except ReqlNonExistenceError:
        raise Error(
            "not_found",
            f"Document {table} {item_id} not found",
            traceback.format_exc(),
            description_code="not_found",
        )
    if data is None:
        log.debug(
            f"get_document: {table} {item_id} in {time()-time_start:.2f} seconds. Document not found. {show_cache_occupancy()}"
        )
        return None
    if len(keys) == 0:
        log.debug(
            f"get_document: {table} {item_id} in {time()-time_start:.2f} seconds. Document full. {show_cache_occupancy()}"
        )
        return copy.deepcopy(data)
    if len(keys) == 1:
        log.debug(
            f"get_document: {table} {item_id} in {time()-time_start:.2f} seconds. Key {keys}. {show_cache_occupancy()}"
        )
        return copy.deepcopy(data.get(keys[0], None))
    log.debug(
        f"get_document: {table} {item_id} in {time()-time_start:.2f} seconds. Keys {keys}. {show_cache_occupancy()}"
    )
    data_keys = {key: data[key] for key in keys if key in data}
    return copy.deepcopy(data_keys)
    # return (
    #     {key: data[key] for key in keys if key in data}.copy()
    #     if data is not None
    #     else {}
    # )


@cached(cache=cache)
def get_cached(table, item_id):
    try:
        with app.app_context():
            data = r.table(table).get(item_id).without("password").run(db.conn)
        return data
    except ReqlNonExistenceError:
        return None


def invalidate_cache(table, item_id):
    cache_key = (table, item_id)
    if cache_key in cache:
        del cache[cache_key]


def show_cache_occupancy():
    current_size = len(cache)
    max_size = cache.maxsize
    return f"Cache occupancy: {current_size}/{max_size}"


## User with names


def get_cached_user_with_names(user_id):
    user = get_cached("users", user_id)
    if user is None:
        return None
    return dict(
        user,
        **{
            "role_name": get_document("roles", user["role"], ["name"]),
            "category_name": get_document("categories", user["category"], ["name"]),
            "group_name": get_document("groups", user["group"], ["name"]),
            "user_name": get_document("users", user_id, ["name"]),
        },
    )


@cached(cache=TTLCache(maxsize=200, ttl=5))
def get_cached_user_used(user_id):
    with app.app_context():
        user_desktops = (
            r.table("domains")
            .get_all(
                ["desktop", user_id, False],
                index="kind_user_tag",
            )
            .filter({"persistent": True})
            .count()
            .run(db.conn)
        )
    with app.app_context():
        user_volatile = (
            r.table("domains")
            .get_all(["desktop", user_id], index="kind_user")
            .filter({"persistent": False})
            .count()
            .run(db.conn)
        )
    with app.app_context():
        user_templates = (
            r.table("domains")
            .get_all(["template", user_id, False], index="kind_user_tag")
            .filter({"enabled": True})
            .count()
            .run(db.conn)
        )
    with app.app_context():
        user_media = (
            r.table("media")
            .get_all(["Downloaded", user_id], index="status_user")
            .count()
            .run(db.conn)
        )
    with app.app_context():
        ready_storage_size = (
            r.table("storage")
            .get_all([user_id, "ready"], index="user_status")
            .sum(lambda size: size["qemu-img-info"]["actual-size"].default(0))
            .run(db.conn)
        )
    with app.app_context():
        recycled_storage_size = (
            r.table("storage")
            .get_all([user_id, "recycled"], index="user_status")
            .sum(lambda size: size["qemu-img-info"]["actual-size"].default(0))
            .run(db.conn)
        )
    user_total_storage_size = (ready_storage_size + recycled_storage_size) / 1073741824
    with app.app_context():
        user_total_media_size = (
            r.table("media")
            .get_all(["Downloaded", user_id], index="status_user")
            .sum(lambda size: size["progress"]["total_bytes"].default(0))
            .run(db.conn)
        ) / 1073741824

    user_total_size = user_total_storage_size + user_total_media_size

    return {
        "desktops": user_desktops,
        "volatile": user_volatile,
        "templates": user_templates,
        "isos": user_media,
        "total_size": user_total_size,
        "media_size": user_total_media_size,
        "storage_size": user_total_storage_size,
    }


@cached(cache=TTLCache(maxsize=200, ttl=5))
def get_cached_started_desktops(item_id, index):
    # Status that are considered in the running quota
    started_status = [
        "Started",
        "Starting",
        "StartingPaused",
        "CreatingAndStarting",
        "Shutting-down",
    ]

    started_desktops = {
        "count": 0,
        "vcpus": 0,
        "memory": 0,
    }

    try:
        with app.app_context():
            started_desktops = (
                r.table("domains")
                .get_all(
                    [
                        "desktop",
                        item_id,
                    ],
                    index=index,
                )
                .filter(
                    lambda desktop: r.expr(started_status).contains(desktop["status"])
                )
                .map(
                    lambda domain: {
                        "count": 1,
                        "memory": domain["create_dict"]["hardware"]["memory"],
                        "vcpus": domain["create_dict"]["hardware"]["vcpus"],
                    }
                )
                .reduce(
                    lambda left, right: {
                        "count": left["count"] + right["count"],
                        "vcpus": left["vcpus"].add(right["vcpus"]),
                        "memory": left["memory"].add(right["memory"]),
                    }
                )
                .run(db.conn)
            )
    except ReqlNonExistenceError:
        pass

    started_desktops["memory"] = started_desktops["memory"] / 1048576

    return started_desktops


## Deployment desktops


@cached(cache=TTLCache(maxsize=10, ttl=1))
def get_cached_deployment_desktops(deployment_id):
    with app.app_context():
        deployment_desktops = list(
            r.table("domains").get_all(deployment_id, index="tag").run(db.conn)
        )
    return deployment_desktops


## Bookings


@cached(cache=TTLCache(maxsize=200, ttl=5))
def get_cached_desktop_bookings(desktop_id):
    with app.app_context():
        booking = (
            r.table("bookings")
            .get_all(["desktop", desktop_id], index="item_type-id")
            .filter(lambda b: b["end"] > r.now())
            .order_by("start")
            .run(db.conn)
        )
    return booking


@cached(cache=TTLCache(maxsize=200, ttl=5))
def get_cached_deployment_bookings(deployment_id):
    with app.app_context():
        booking = (
            r.table("bookings")
            .get_all(["deployment", deployment_id], index="item_type-id")
            .filter(lambda b: b["end"] > r.now())
            .order_by("start")
            .run(db.conn)
        )
    return booking


## Hypervisors


@cached(cache=TTLCache(maxsize=64, ttl=10))
def get_cached_hypervisors_online():
    with app.app_context():
        return list(
            r.table("hypervisors")
            .filter({"status": "Online", "enabled": True})
            .run(db.conn)
        )


## Storage pools


@cached(cache=TTLCache(maxsize=1, ttl=3600))
def get_cached_default_storage_pool():
    with app.app_context():
        default_storage_pool = (
            r.table("storage_pool").get(DEFAULT_STORAGE_POOL_ID).run(db.conn)
        )
    return default_storage_pool


@cached(cache=TTLCache(maxsize=10, ttl=10))
def get_cached_enabled_storage_pools():
    with app.app_context():
        storage_pools = list(
            r.table("storage_pool")
            .filter(
                {"enabled": True},
            )
            .run(db.conn)
        )
    return storage_pools


@cached(cache=TTLCache(maxsize=10, ttl=10))
def get_cached_enabled_virt_pools():
    with app.app_context():
        virt_pools = list(
            r.table("storage_pool")
            .filter(
                {"enabled_virt": True},
            )
            .run(db.conn)
        )
    # It can be done with this query filter when the enabled_virt is always there
    return virt_pools


@cached(cache=TTLCache(maxsize=200, ttl=10))
def get_cached_available_category_storage_pool_id(category_id):
    # Used for create actions where the category is not yet assigned to the domain
    with app.app_context():
        storage_pools = list(
            r.table("storage_pool")
            .filter(lambda pool: pool["categories"].contains(category_id))
            .run(db.conn)
        )
    if len(storage_pools) == 0:
        if DEFAULT_STORAGE_POOL_ID in [
            esp["id"] for esp in get_cached_enabled_storage_pools()
        ]:
            return DEFAULT_STORAGE_POOL_ID
        raise Error(
            "precondition_required",
            f"Storage pool {DEFAULT_STORAGE_POOL_ID} is disabled so no storage pool available for category {category_id}",
            description_code="storage_pool_disabled",
        )
    if len(storage_pools) == 1:
        if storage_pools[0]["enabled"]:
            return storage_pools[0]["id"]
        raise Error(
            "precondition_required",
            f"Storage pool {storage_pools[0]['id']} is disabled",
            description_code="storage_pool_disabled",
        )
    raise Error(
        "internal_server",
        f"Multiple storage pools found for category {category_id}",
        description_code="multiple_storage_pools",
    )


@cached(cache=TTLCache(maxsize=200, ttl=10))
def get_cached_available_domain_storage_pool_id(domain_id):
    # Used to virtualize the storage pool for the domain
    # No virtualitzation for a disabled storage_pool should be available
    if Domain.exists(domain_id):
        domain_obj = Domain(domain_id)
    else:
        raise Error(
            "not_found",
            f"Domain {domain_id} not found",
            description_code="not_found",
        )
    if not domain_obj.storage_ready:
        raise Error(
            "precondition_required",
            f"Domain {domain_id} storage not ready",
            description_code="storage_not_ready",
        )
    domain_storage_objs = domain_obj.storages
    if len(domain_storage_objs) == 0:
        raise Error(
            "precondition_required",
            f"Domain {domain_id} storage not found",
            description_code="storage_not_found",
        )
    domain_storage_pool_obj = domain_storage_objs[0].pool
    if not domain_storage_pool_obj:
        ## This can only happen if we created it in an storage pool that has been deleted
        # Default storage pool is used if no storage pool matches the domain storage_id,
        # but likely will fail
        # This can lead to allowing a domain to be started in any hypervisor with default storage pool
        virt_pool_id = DEFAULT_STORAGE_POOL_ID
    else:
        virt_pool_id = domain_storage_pool_obj.id

    # Check if the virt_pool is enabled
    log.debug(f"Checking if virt_pool {virt_pool_id} is enabled")
    if virt_pool_id not in [esp["id"] for esp in get_cached_enabled_virt_pools()]:
        raise Error(
            "precondition_required",
            f"Virt pool {virt_pool_id} is disabled so no storage pool available for domain {domain_id}",
            description_code="storage_pool_disabled",
        )
    return virt_pool_id


## Config


@cached(cache=TTLCache(maxsize=1, ttl=60))
def get_config():
    with app.app_context():
        return r.table("config").get(1).run(db.conn)


## Desktops priorities


@cached(cache=TTLCache(maxsize=1, ttl=60))
def get_cached_desktops_priority():
    with app.app_context():
        return list(
            r.table("desktops_priority").order_by(r.desc("priority")).run(db.conn)
        )
