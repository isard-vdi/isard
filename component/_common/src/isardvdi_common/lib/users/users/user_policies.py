from typing import Literal

from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r

_get_policies_category_role_provider_cache: TTLCache = TTLCache(maxsize=200, ttl=30)


class UserPolicies(RethinkSharedConnection):

    _rdb_table = "users"

    @classmethod
    @cached(cache=_get_policies_category_role_provider_cache)
    def get_policies_category_role_provider(
        cls, category_id: str, role_id: str, provider: str
    ) -> list:
        """
        Get all policies for a specific category and role.
        """
        with cls._rdb_context():
            return list(
                r.table("authentication")
                .filter(
                    (r.row["type"] == provider)
                    & (
                        (r.row["category"] in [category_id, "all"])
                        | (r.row["role"] in [role_id, "all"])
                    )
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_policies_category_role_provider_cache(cls):
        _get_policies_category_role_provider_cache.clear()

    @classmethod
    @cached(
        TTLCache(maxsize=100, ttl=10),
        key=lambda cls, subtype, category_id=None, role_id=None, provider=None, user_id=None: (
            cls,
            subtype,
            category_id,
            role_id,
            provider,
            user_id,
        ),
    )
    def get_user_policy(
        cls,
        subtype: Literal["disclaimer", "email_verification", "password"],
        category_id: str = None,
        role_id: str = None,
        provider: str = None,
        user_id: str = None,
    ) -> dict:
        """
        Get the password policy for a user based on category_id, role_id, provider or user_id.
        """
        if user_id:
            user = Caches.get_document(
                cls._rdb_table, user_id, ["category", "role", "provider"]
            )
            category_id = user["category"]
            role_id = user["role"]
            provider = user["provider"]
        else:
            if not category_id or not role_id:
                raise Error(
                    "internal_server",
                    "Category and role must be provided if user_id is not given",
                    description_code="category_role_required",
                )

        policies = cls.get_policies_category_role_provider(
            category_id, role_id, provider
        )
        matching_policies = []
        for policy in policies:
            if policy["category"] == category_id and policy["role"] == role_id:
                return policy.get(subtype)
            elif policy["category"] == category_id and policy["role"] == "all":
                matching_policies.append({"priority": 0, "policy": policy.get(subtype)})
            elif policy["category"] == "all" and policy["role"] == role_id:
                matching_policies.append({"priority": 1, "policy": policy.get(subtype)})
            elif policy["category"] == "all" and policy["role"] == "all":
                matching_policies.append({"priority": 2, "policy": policy.get(subtype)})

        matching_policies.sort(key=lambda x: x["priority"])
        if matching_policies:
            return matching_policies[0]["policy"]
        else:
            return False
