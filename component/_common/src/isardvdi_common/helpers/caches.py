import copy
import logging as log
import traceback
from time import time

from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from rethinkdb import r
from rethinkdb.errors import ReqlNonExistenceError


class Caches(RethinkSharedConnection):

    cache = TTLCache(maxsize=5000, ttl=10)

    @classmethod
    def get_document(cls, table, item_id, keys=[], invalidate=False):
        try:
            if invalidate:
                cls.invalidate_cache(table, item_id)
        except Exception as e:
            pass
        try:
            time_start = time()
            data = cls.get_cached(table, item_id)
        except ReqlNonExistenceError:
            # raise Error(
            #     "not_found",
            #     f"Document {table} {item_id} not found",
            #     traceback.format_exc(),
            #     description_code="not_found",
            # )
            raise ValueError(f"Document {table} {item_id} not found")
        if data is None:
            log.debug(
                f"get_document: {table} {item_id} in {time()-time_start:.2f} seconds. Document not found. {cls.show_cache_occupancy()}"
            )
            return None
        if len(keys) == 0:
            log.debug(
                f"get_document: {table} {item_id} in {time()-time_start:.2f} seconds. Document full. {cls.show_cache_occupancy()}"
            )
            return copy.deepcopy(data)
        if len(keys) == 1:
            log.debug(
                f"get_document: {table} {item_id} in {time()-time_start:.2f} seconds. Key {keys}. {cls.show_cache_occupancy()}"
            )
            return copy.deepcopy(data.get(keys[0], None))
        log.debug(
            f"get_document: {table} {item_id} in {time()-time_start:.2f} seconds. Keys {keys}. {cls.show_cache_occupancy()}"
        )
        data_keys = {key: data[key] for key in keys if key in data}
        return copy.deepcopy(data_keys)
        # return (
        #     {key: data[key] for key in keys if key in data}.copy()
        #     if data is not None
        #     else {}
        # )

    @classmethod
    @cached(cache=cache)
    def get_cached(cls, table, item_id):
        try:
            with cls._rdb_context():
                data = (
                    r.table(table)
                    .get(item_id)
                    .without(["password", "api_key"])
                    .run(cls._rdb_connection)
                )
            return data
        except ReqlNonExistenceError:
            return None

    @classmethod
    def invalidate_caches(cls, table, item_ids: list):
        for item_id in item_ids:
            cls.invalidate_cache(table, item_id)

    @classmethod
    def invalidate_cache(cls, table, item_id):
        cache_key = (table, item_id)
        if cache_key in cls.cache:
            del cls.cache[cache_key]

    @classmethod
    def show_cache_occupancy(cls):
        current_size = len(cls.cache)
        max_size = cls.cache.maxsize
        if current_size >= max_size:
            log.error(f"Cache occupancy full: {current_size}/{max_size}")
        return f"Cache occupancy: {current_size}/{max_size}"

    ## User with names

    @classmethod
    def get_cached_user_with_names(cls, user_id):
        user = cls.get_cached("users", user_id)
        if user is None:
            return None
        return dict(
            user,
            **{
                "role_name": cls.get_document("roles", user["role"], ["name"]),
                "category_name": cls.get_document(
                    "categories", user["category"], ["name"]
                ),
                "group_name": cls.get_document("groups", user["group"], ["name"]),
                "user_name": user["name"],
                "secondary_groups_names": [
                    cls.get_document("groups", group_id, ["name"])
                    for group_id in user["secondary_groups"]
                ],
                "secondary_groups_data": [
                    {
                        "id": group_id,
                        "name": cls.get_document("groups", group_id, ["name"]),
                    }
                    for group_id in user["secondary_groups"]
                ],
            },
        )

    ## Desktops priorities

    @classmethod
    @cached(cache=TTLCache(maxsize=1, ttl=60))
    def get_cached_desktops_priority(cls):
        with cls._rdb_context():
            return list(
                r.table("desktops_priority")
                .order_by(r.desc("priority"))
                .run(cls._rdb_connection)
            )

    ## Config

    config_cache = TTLCache(maxsize=1, ttl=60)

    @classmethod
    @cached(config_cache)
    def get_config(cls):
        with cls._rdb_context():
            return r.table("config").get(1).run(cls._rdb_connection)

    @classmethod
    def clear_config_cache(cls):
        cls.config_cache.clear()

    ## Unused item timeout

    @classmethod
    @cached(cache=TTLCache(maxsize=5, ttl=60))
    def get_cached_unused_item_timeout_by_op(cls, op):
        with cls._rdb_context():
            return list(
                r.table("unused_item_timeout")
                .filter({"op": op})
                .order_by(r.desc("priority"))
                .run(cls._rdb_connection)
            )

    ## Domains wg mac

    wg_mac_domain_cache = TTLCache(maxsize=50, ttl=200)

    @classmethod
    def set_cached_domain_wg_mac(cls, domain_id, interfaces):
        wg_mac = next(
            (iface["mac"] for iface in interfaces if iface["id"] == "wireguard"),
            None,
        )
        if wg_mac is None:
            return None
        cls.wg_mac_domain_cache[wg_mac] = domain_id

    @classmethod
    def invalidate_cached_domain_wg_mac(cls, wg_mac):
        if wg_mac in cls.wg_mac_domain_cache:
            del cls.wg_mac_domain_cache[wg_mac]

    @classmethod
    def get_domain_id_from_wg_mac(cls, wg_mac):
        if wg_mac in cls.wg_mac_domain_cache:
            return cls.wg_mac_domain_cache[wg_mac]
        # DB fallback: the cache may be cold if populated by a different
        # process (e.g. change-handler populates but apiv4 reads).
        with cls._rdb_context():
            results = list(
                r.table("domains")
                .get_all(wg_mac, index="wg_mac")
                .filter(
                    lambda d: r.expr(
                        ["Starting", "StartingDomainDisposable", "Started"]
                    ).contains(d["status"])
                )
                .pluck("id")
                .limit(1)
                .run(cls._rdb_connection)
            )
        if results:
            domain_id = results[0]["id"]
            cls.wg_mac_domain_cache[wg_mac] = domain_id
            return domain_id
        return None

    ## Deployment desktops

    @classmethod
    @cached(cache=TTLCache(maxsize=10, ttl=1))
    def get_cached_deployment_desktops(cls, deployment_id):
        with cls._rdb_context():
            deployment_desktops = list(
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .run(cls._rdb_connection)
            )
        return deployment_desktops

    ### Users migrations exceptions

    @classmethod
    @cached(cache=TTLCache(maxsize=1, ttl=60))
    def get_cached_users_migrations_exceptions(cls):
        with cls._rdb_context():
            data = list(r.table("users_migrations_exceptions").run(cls._rdb_connection))
        roles = [item["item_id"] for item in data if item["item_type"] == "roles"]
        categories = [
            item["item_id"] for item in data if item["item_type"] == "categories"
        ]
        groups = [item["item_id"] for item in data if item["item_type"] == "groups"]
        users = [item["item_id"] for item in data if item["item_type"] == "users"]
        return {
            "roles": roles,
            "categories": categories,
            "groups": groups,
            "users": users,
        }

    ## Hypervisors

    @classmethod
    @cached(cache=TTLCache(maxsize=64, ttl=10))
    def get_cached_hypervisors_online(cls):
        with cls._rdb_context():
            return list(
                r.table("hypervisors")
                .filter({"status": "Online", "enabled": True})
                .run(cls._rdb_connection)
            )

    ## Storage pools

    @classmethod
    @cached(cache=TTLCache(maxsize=1, ttl=3600))
    def get_cached_default_storage_pool(cls):
        with cls._rdb_context():
            default_storage_pool = (
                r.table("storage_pool")
                .get(DEFAULT_STORAGE_POOL_ID)
                .run(cls._rdb_connection)
            )
        return default_storage_pool

    @classmethod
    @cached(cache=TTLCache(maxsize=10, ttl=10))
    def get_cached_enabled_storage_pools(cls):
        with cls._rdb_context():
            storage_pools = list(
                r.table("storage_pool")
                .filter(
                    {"enabled": True},
                )
                .run(cls._rdb_connection)
            )
        return storage_pools

    @classmethod
    @cached(cache=TTLCache(maxsize=10, ttl=10))
    def get_cached_enabled_virt_pools(cls):
        with cls._rdb_context():
            virt_pools = list(
                r.table("storage_pool")
                .filter(
                    {"enabled_virt": True},
                )
                .run(cls._rdb_connection)
            )
        # It can be done with this query filter when the enabled_virt is always there
        return virt_pools

    @classmethod
    @cached(cache=TTLCache(maxsize=200, ttl=10))
    def get_cached_available_category_storage_pool_id(cls, category_id):
        # Used for create actions where the category is not yet assigned to the domain
        with cls._rdb_context():
            storage_pools = list(
                r.table("storage_pool")
                .filter(lambda pool: pool["categories"].contains(category_id))
                .run(cls._rdb_connection)
            )
        from isardvdi_common.helpers.error_factory import Error

        if len(storage_pools) == 0:
            if DEFAULT_STORAGE_POOL_ID in [
                esp["id"] for esp in cls.get_cached_enabled_storage_pools()
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
