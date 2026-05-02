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

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

# ── User CRUD ────────────────────────────────────────────────────────────


class AdminUserCreateData(BaseModel):
    """Request body for creating a user."""

    username: str
    name: str
    uid: Optional[str] = None
    provider: str = "local"
    category: str
    group: str
    role: str
    password: str
    email: Optional[str] = ""
    photo: Optional[str] = ""
    bulk: bool = False
    secondary_groups: List[str] = Field(default_factory=list)


class AdminUserUpdateData(BaseModel):
    """Request body for updating one or more users."""

    ids: Optional[List[str]] = None
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    category: Optional[str] = None
    group: Optional[str] = None
    password: Optional[str] = None
    active: Optional[bool] = None
    quota: Optional[Union[bool, dict]] = None
    secondary_groups: Optional[List[str]] = None
    bulk: bool = False


class AdminUserDeleteData(BaseModel):
    """Request body for deleting users."""

    user: List[str]
    delete_user: bool = True


class AdminBulkUserCreateData(BaseModel):
    """Request body for bulk user creation."""

    users: List[dict]
    email_verified: bool = False


# ── CSV Operations ───────────────────────────────────────────────────────


class AdminCSVUserEditRow(BaseModel):
    """One row of PUT ``/admin/users/csv`` — an enriched user record
    returned by ``/admin/users/csv/validate`` (PUT). Webapp/k6
    round-trip the validate output back into the edit endpoint; ``id``
    is the only load-bearing field. Anything else is optional so a
    minimal rename ``{"id": "...", "name": "new"}`` is also accepted.
    Pre-typed so a missing ``id`` yields 422 at the boundary instead
    of falling into the service and surfacing as 500."""

    id: str
    username: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    category: Optional[str] = None
    group: Optional[str] = None
    provider: Optional[str] = None
    uid: Optional[str] = None
    category_id: Optional[str] = None
    group_id: Optional[str] = None
    secondary_groups: Optional[List[str]] = None
    secondary_groups_names: Optional[List[str]] = None
    password: Optional[str] = None
    photo: Optional[str] = None
    active: Optional[bool] = None

    model_config = {"extra": "allow"}


class AdminCSVUserEditData(BaseModel):
    """Request body for editing users via CSV (PUT ``/admin/users/csv``)."""

    users: List[AdminCSVUserEditRow]


class AdminCSVUserImportData(BaseModel):
    """Request body for importing new users from CSV (POST
    ``/admin/users/csv``). Rows here have no ``id`` yet — that's
    assigned by ``CommonUsers.generate_users``. Kept as ``List[dict]``
    so the upstream validate-create flow's permissive shape still
    applies."""

    users: List[dict]


# ── Secondary Groups ────────────────────────────────────────────────────


class AdminSecondaryGroupsData(BaseModel):
    """Request body for secondary group operations."""

    ids: List[str]
    secondary_groups: List[str]


# ── Password & Security ─────────────────────────────────────────────────


class AdminPasswordResetData(BaseModel):
    """Request body for resetting a user's password."""

    user_id: str
    password: str


# ── Groups ───────────────────────────────────────────────────────────────


class AdminGroupCreateData(BaseModel):
    """Request body for creating a group."""

    uid: Optional[str] = None
    name: str
    description: str = ""
    parent_category: Optional[str] = None
    external_app_id: Optional[str] = None
    external_gid: Optional[str] = None


class AdminGroupUpdateData(BaseModel):
    """Request body for updating a group."""

    id: str
    name: str
    description: Optional[str] = None


class AdminGroupEnrollmentData(BaseModel):
    """Request body for group enrollment actions."""

    id: str
    action: str
    role: Optional[str] = None


# ── Categories ───────────────────────────────────────────────────────────


class AdminCategoryCreateData(BaseModel):
    """Request body for creating a category."""

    name: str
    description: str = ""
    frontend: bool = True
    custom_url_name: str = ""
    uid: Optional[str] = None
    photo: Optional[str] = None
    storage_pool: Optional[str] = None


class AdminCategoryUpdateData(BaseModel):
    """Request body for updating a category."""

    id: str
    name: str
    description: Optional[str] = None
    frontend: Optional[bool] = None
    custom_url_name: Optional[str] = None
    uid: Optional[str] = None
    photo: Optional[str] = None


class AdminCategoryAuthenticationData(BaseModel):
    """Request body for updating category authentication."""

    authentication: dict


# ── Quotas & Limits ──────────────────────────────────────────────────────


class AdminQuotaUpdateData(BaseModel):
    """Request body for updating quotas."""

    quota: Union[bool, dict]
    propagate: Optional[bool] = False
    role: Optional[str] = "all_roles"


class AdminLimitsUpdateData(BaseModel):
    """Request body for updating limits."""

    limits: Union[bool, dict]
    propagate: Optional[bool] = False


class AdminRoleUpdateData(BaseModel):
    """Request body for updating a role.

    The route forces ``id`` from the URL path, so any ``id`` on the
    body is ignored — declared optional so callers that include it for
    symmetry don't 4xx, and the service receives the URL-derived id.
    """

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    sortorder: Optional[int] = None


# ── Delete Checks ────────────────────────────────────────────────────────


class AdminDeleteChecksData(BaseModel):
    """Request body for delete dependency checks."""

    ids: List[str]


# ── Secrets ──────────────────────────────────────────────────────────────


class AdminSecretCreateData(BaseModel):
    """Request body for creating a secret."""

    category_id: str
    secret: str
    description: Optional[str] = ""


# ── Search ───────────────────────────────────────────────────────────────


class AdminUserSearchData(BaseModel):
    """Request body for searching users."""

    term: str


# ── Broadcast ────────────────────────────────────────────────────────────


class AdminBroadcastData(BaseModel):
    """Request body for broadcasting a message."""

    type: str
    message: str


# ── Migration ────────────────────────────────────────────────────────────


class AdminCheckMigratedData(BaseModel):
    """Request body for checking migrated users."""

    users: List[str]


# ── Check Group Category ────────────────────────────────────────────────


class AdminCheckGroupCategoryData(BaseModel):
    """Request body for checking group/category association."""

    category: Optional[str] = None
    group: Optional[str] = None


# ── Bastion Domain ──────────────────────────────────────────────────────


class AdminBastionDomainData(BaseModel):
    """Request body for updating bastion domain."""

    bastion_domain: Union[str, bool, None]


# ── User Schema ──────────────────────────────────────────────────────────


class AdminUserSchemaResponse(BaseModel):
    """Response for user schema (roles, categories, groups)."""

    role: list
    category: Optional[list] = None
    group: Optional[list] = None


# -- Response models --


class AdminUserVpn(BaseModel):
    wireguard: Optional[dict] = None


class AdminUserStorage(BaseModel):
    provider_quota: Optional[dict] = None


class AdminUser(BaseModel):
    # ``id`` is the only field every row in the ``users`` table must
    # carry — every other field can land as ``None`` or be missing for
    # half-deleted rows, partial-sync SSO users, and historical seeds
    # that pre-dated newer schemas. The admin UI lists those rows so
    # an operator can clean them up; making the response model strict
    # here would 500 the entire list on the first such row, hiding the
    # bad rows from the only flow that surfaces them. Same pattern as
    # the ``email_verified`` relaxation tracked in Bug 37.
    id: str
    name: Optional[str] = None
    provider: Optional[str] = None
    category: Optional[str] = None
    uid: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None
    group: Optional[str] = None
    active: Optional[bool] = True
    secondary_groups: Optional[list[str]] = []
    email: Optional[str] = None
    accessed: Optional[float] = None
    # ``email_verified`` is ``False`` for never-verified, ``True`` for
    # password-flow self-verified, or an epoch ``int`` for email-link-
    # verified. The same field can land in the DB as ``None`` for users
    # created via paths that skipped the input Pydantic validation
    # (SAML auto-register, user-migration, direct seeds). Without
    # ``None`` in the response union, ``GET /api/v4/admin/users`` 500s
    # on the first such row — the route's ``except Exception`` swallows
    # the ResponseValidationError into "Failed to list users".
    # Tracked as Bug 37 in APIV4_LOAD_TESTING_BUGS_FOUND.md.
    email_verified: bool | int | None = None
    disclaimer_acknowledged: Optional[bool] = None
    vpn: Optional[AdminUserVpn] = None
    user_storage: Optional[AdminUserStorage] = None


class RequiredCheckResponse(BaseModel):
    required: bool


class AutoRegisterRequest(BaseModel):
    role_id: str
    group_id: str
    secondary_groups: Optional[List[str]] = None


class AutoRegisterResponse(BaseModel):
    id: str


class AdminUserDeleteResponse(BaseModel):
    exceptions: Optional[list[str]] = None


class AdminGroup(BaseModel):
    id: str
    uid: Optional[str] = None
    name: str
    parent_category: str
    auto: bool = False
    description: str = ""
    # ``AdminGroupCreateData`` exposes these as Optional[str] so the
    # webapp can omit them. The response model has to accept the same
    # shape — declaring them as ``str`` rejected ``None`` and surfaced
    # as a 500 "Failed to create group" on every plain-form submit.
    external_app_id: Optional[str] = None
    external_gid: Optional[str] = None
    limits: bool | dict = False


class AdminTemplateItem(BaseModel):
    id: str
    name: str
    icon: Optional[str] = None
    user: Optional[str] = None
    category: Optional[str] = None
