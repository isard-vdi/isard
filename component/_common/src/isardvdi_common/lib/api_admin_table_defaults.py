#
#   Copyright © 2026 IsardVDI
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

"""Per-table default-setters for ``/admin/table/add/{table}``.

apiv3 (``api/src/api/schemas/*.yml``) declared field-level
``default_setter: <name>`` and the ``IsardValidator`` Cerberus subclass
auto-filled them via ``.normalized(data)`` before insert. apiv4 dropped
the YAML+Cerberus pipeline; this module ports the same matrix as a
plain registry so ``AdminTablesService.insert_table_item`` can apply
the apiv3 defaults uniformly.

Every entry mirrors a row from the apiv3 schema sweep:

| schema (apiv3) → rdb table | field | setter |
|---|---|---|
| analytics_graph → analytics_graph | id | genuuid |
| bookings_priority → bookings_priority | id | genuuid |
| category → categories | id | genuuid |
| deployment → deployments | id | genuuid |
| desktops_priority → desktops_priority | id | genuuid |
| domains → domains | id | genuuid |
| gpus → gpus | id | genuuid |
| graphics → graphics | id | genuuid |
| group → groups | id | genuuid |
| group → groups | uid | genuuid |
| hypervisors → hypervisors | storage_pools | storagepools |
| hypervisors → hypervisors | virt_pools | storagepools |
| interfaces → interfaces | id | genuuid |
| media → media | id | genuuid |
| media → media | icon | mediaicon |
| notification → notifications | id | genuuid |
| notification_templates → notification_tmpls | id | genuuid |
| policy → user_policies | id | genuuid |
| qos_disk → qos_disk | id | genuuid |
| qos_net → qos_net | id | genuuid |
| remotevpn → remotevpn | id | genuuid |
| secrets → secrets | secret | gensecret |
| storage_pool → storage_pool | id | genuuid |
| unused_item_timeout → unused_item_timeout | id | genuuid |
| usage_credit → usage_credit | id | genuuid |
| usage_grouping → usage_grouping | id | genuuid |
| usage_limit → usage_limit | id | genuuid |
| usage_parameters → usage_parameters | id | genuuid |
| user → users | id | genuuid |
| user → users | uid | genuuid |
| user_storage → user_storage | id | genuuid |
| videos → videos | id | genuuid |

Schemas that are input-validation only (``desktop_from_media``,
``desktop_from_template``, ``template`` extra ``template_id``) don't
map to a single rdb table on the ``/admin/table/add`` path; they're
handled by their own typed routes that pass through dedicated
services. They're excluded here on purpose.
"""

import uuid
from base64 import b64encode
from secrets import token_bytes
from typing import Callable

from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID

# ── Setters ──────────────────────────────────────────────────────────────


def gen_uuid(_data: dict) -> str:
    """apiv3 ``_normalize_default_setter_genuuid``."""
    return str(uuid.uuid4())


def gen_secret(_data: dict) -> str:
    """apiv3 ``_normalize_default_setter_gensecret`` — 32 random bytes,
    base64-url-safe encoded."""
    return b64encode(token_bytes(32)).decode()


def default_storage_pools(_data: dict) -> list[str]:
    """apiv3 ``_normalize_default_setter_storagepools`` — for
    ``hypervisors.storage_pools`` and ``hypervisors.virt_pools``,
    which are list fields."""
    return [DEFAULT_STORAGE_POOL_ID]


def media_icon(data: dict) -> str:
    """apiv3 ``_normalize_default_setter_mediaicon``. Branches on
    ``data["kind"]``: ``iso`` → CD icon, anything else → floppy."""
    return "fa-circle-o" if data.get("kind") == "iso" else "fa-floppy-o"


# ── Per-table registry ───────────────────────────────────────────────────

Setter = Callable[[dict], object]

TABLE_DEFAULTS: dict[str, dict[str, Setter]] = {
    "analytics_graph": {"id": gen_uuid},
    "bookings_priority": {"id": gen_uuid},
    "categories": {"id": gen_uuid},
    "deployments": {"id": gen_uuid},
    "desktops_priority": {"id": gen_uuid},
    "domains": {"id": gen_uuid},
    "gpus": {"id": gen_uuid},
    "graphics": {"id": gen_uuid},
    "groups": {"id": gen_uuid, "uid": gen_uuid},
    "hypervisors": {
        "storage_pools": default_storage_pools,
        "virt_pools": default_storage_pools,
    },
    "interfaces": {"id": gen_uuid},
    "media": {"id": gen_uuid, "icon": media_icon},
    "notifications": {"id": gen_uuid},
    "notification_tmpls": {"id": gen_uuid},
    "user_policies": {"id": gen_uuid},
    "qos_disk": {"id": gen_uuid},
    "qos_net": {"id": gen_uuid},
    "remotevpn": {"id": gen_uuid},
    "secrets": {"secret": gen_secret},
    "storage_pool": {"id": gen_uuid},
    "unused_item_timeout": {"id": gen_uuid},
    "usage_credit": {"id": gen_uuid},
    "usage_grouping": {"id": gen_uuid},
    "usage_limit": {"id": gen_uuid},
    "usage_parameters": {"id": gen_uuid},
    "users": {"id": gen_uuid, "uid": gen_uuid},
    "user_storage": {"id": gen_uuid},
    "videos": {"id": gen_uuid},
}


def apply_table_defaults(table: str, data: dict) -> None:
    """Apply per-field defaults registered for ``table`` to ``data``
    in place. Existing keys are left untouched (``setdefault`` semantics
    matching apiv3 Cerberus normalisation: ``default_setter`` only fires
    when the field is absent)."""
    for field, setter in TABLE_DEFAULTS.get(table, {}).items():
        if field not in data:
            data[field] = setter(data)
