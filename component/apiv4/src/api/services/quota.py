#
#   Copyright © 2025 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Service layer for the ``/admin/quota/{kind}[/{item_id}]`` admin
endpoints. The route was previously calling the common ``Quotas``
helper directly, which violated the routes → services → common
pattern. This module wraps the dispatch logic so the route stays a
thin HTTP layer.
"""

import traceback

from api.services.error import Error
from isardvdi_common.helpers.quotas import Quotas


class QuotaService:
    @staticmethod
    def get_max_quota(payload: dict, kind: str, item_id: str | None = None) -> dict:
        """Return the configured quota / limits dict for the requested
        entity.

        ``@is_admin_or_manager``: when ``item_id`` is omitted the lookup
        defaults to the caller's own user/category/group as resolved
        from the JWT payload.

        ``kind`` must be one of ``user``, ``category`` or ``group`` —
        anything else raises a typed ``bad_request`` ``Error`` so the
        route layer can map it to a 400.
        """
        if kind == "user":
            target = item_id or payload["user_id"]
            return Quotas.GetUserQuota(target)
        if kind == "category":
            target = item_id or payload["category_id"]
            return Quotas.GetCategoryQuota(target)
        if kind == "group":
            target = item_id or payload["group_id"]
            return Quotas.GetGroupQuota(target)
        raise Error(
            "bad_request",
            f"Unknown quota kind '{kind}'",
            traceback.format_exc(),
        )
