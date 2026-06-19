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

from typing import List, Literal, Optional, Union

from isardvdi_common.schemas.shared.quotas import Limits, Quota
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
    email_verified: bool = False
    photo: Optional[str] = ""
    bulk: bool = False
    secondary_groups: List[str] = Field(default_factory=list)


class AdminUserUpdateData(BaseModel):
    """Request body for updating one or more users."""

    ids: Optional[List[str]] = None
    name: Optional[str] = None
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    role: Optional[str] = None
    category: Optional[str] = None
    group: Optional[str] = None
    password: Optional[str] = None
    active: Optional[bool] = None
    quota: Optional[Union[bool, Quota]] = None
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
    """One row of PUT ``/admin/items/users/csv`` — an enriched user record
    returned by ``/admin/items/users/csv/validate`` (PUT). Webapp/k6
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
    """Request body for editing users via CSV (PUT ``/admin/items/users/csv``)."""

    users: List[AdminCSVUserEditRow]


class AdminCSVUserImportData(BaseModel):
    """Request body for importing new users from CSV (POST
    ``/admin/items/users/csv``). Rows here have no ``id`` yet — that's
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


class EphimeralDesktopsData(BaseModel):
    minutes: int
    action: Literal["Stopping", "StoppingAndDeleting"]


class AdminGroupUpdateData(BaseModel):
    """Request body for updating a group."""

    id: str
    name: str
    description: Optional[str] = None
    ephimeral: EphimeralDesktopsData | bool | None = None
    linked_groups: Optional[List[str]] = None


class AdminGroupEnrollmentData(BaseModel):
    """Request body for group enrollment actions."""

    id: str
    action: str
    role: Optional[str] = None


# ── Categories ───────────────────────────────────────────────────────────


class ManagerPermissionsData(BaseModel):
    authentication: bool = False
    branding: bool = False
    login_notification: bool = False
    plannings: bool = False


class AdminCategoryCreateData(BaseModel):
    """Request body for creating a category."""

    name: str
    description: str = ""
    frontend: bool = True
    custom_url_name: str = ""
    uid: Optional[str] = None
    photo: Optional[str] = None
    storage_pool: Optional[str] = None
    maintenance: bool = False
    manager_permissions: ManagerPermissionsData
    recycle_bin_cutoff_time: int | None = None
    ephimeral: Optional[EphimeralDesktopsData | bool] = False
    storage_pool: Optional[str] = None
    gpu_use_global_pool: Optional[bool] = None


class AdminCategoryUpdateData(BaseModel):
    """Request body for updating a category."""

    id: str
    name: str
    description: Optional[str] = None
    frontend: Optional[bool] = None
    custom_url_name: Optional[str] = None
    uid: Optional[str] = None
    recycle_bin_cutoff_time: int | None = None
    ephimeral: Optional[EphimeralDesktopsData | bool] = None
    maintenance: Optional[bool] = None
    manager_permissions: Optional[ManagerPermissionsData] = None
    gpu_use_global_pool: Optional[bool] = None


class AdminCategoryAuthenticationData(BaseModel):
    """Request body for updating category authentication."""

    authentication: dict


# ── Quotas & Limits ──────────────────────────────────────────────────────


class AdminQuotaUpdateData(BaseModel):
    """Request body for updating quotas."""

    quota: Union[bool, Quota]
    propagate: Optional[bool] = False
    role: Optional[str] = "all_roles"


class AdminLimitsUpdateData(BaseModel):
    """Request body for updating limits."""

    limits: Union[bool, Limits]
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

    id: str
    description: Optional[str] = ""
    domain: str
    category_id: str


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
    # ``None`` in the response union, ``GET /api/v4/admin/items/users`` 500s
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
    # Legacy rows persist ``auto`` as a dict from the retired auto-desktops UI.
    auto: bool | dict = False
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


# ── Per-endpoint focused response models ─────────────────────────────────


class AdminUserImpersonateJwtResponse(BaseModel):
    """Response for ``GET /admin/item/jwt/{user_id}`` — a single signed JWT."""

    jwt: str


class AdminSecondaryGroupRef(BaseModel):
    """Lightweight ``{id, name}`` group reference used by the user-full-data
    response. Same pluck as ``GroupsProcessed.get_secondary_groups_data``."""

    id: str
    name: Optional[str] = None
    category_name: Optional[str] = None


class AdminUserFullDataResponse(AdminUser):
    """Response for ``GET /admin/item/user/{user_id}`` and ``/raw``.

    ``UsersProcessed.get_user_full_data`` enriches the cached user row with
    ``category_name``, ``group_name`` and ``secondary_groups_data``. Inherits
    every ``AdminUser`` field (so half-deleted rows still serialize) and
    surfaces the two name lookups + the secondary-group expansion. The raw
    variant goes through ``Caches.get_cached_user_with_names`` which already
    merges the same name fields, so a single model covers both."""

    category_name: Optional[str] = None
    group_name: Optional[str] = None
    secondary_groups_data: Optional[list[AdminSecondaryGroupRef]] = None
    email_verified: Optional[bool] = False


class AdminUserNavItem(BaseModel):
    """Row shape for ``GET /admin/items/users/{nav}/users``.

    ``UsersProcessed.admin_list_users`` plucks the ``AdminUser`` fields and,
    depending on ``nav``, merges either the ``*_name`` lookups
    (``management``) or quota usage counters (``quotas_limits``). Both nav
    branches share the base id/name columns; the divergent fields are kept
    optional so a single model covers both shapes."""

    id: str
    name: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None
    category: Optional[str] = None
    group: Optional[str] = None
    active: Optional[bool] = None
    provider: Optional[str] = None
    uid: Optional[str] = None
    secondary_groups: Optional[list[str]] = None
    email: Optional[str] = None
    accessed: Optional[float] = None
    email_verified: bool | int | None = None
    disclaimer_acknowledged: Optional[bool] = None
    vpn: Optional[AdminUserVpn] = None
    user_storage: Optional[AdminUserStorage] = None
    # ``management`` nav merges
    group_name: Optional[str] = None
    role_name: Optional[str] = None
    category_name: Optional[str] = None
    secondary_groups_names: Optional[list[str]] = None
    # ``quotas_limits`` nav merges
    volatile: Optional[int] = None
    desktops: Optional[int] = None
    templates: Optional[int] = None
    media_size: Optional[float] = None
    domains_size: Optional[float] = None


class AdminUserSearchItem(BaseModel):
    """Row shape for ``POST /admin/items/users/search``.

    ``Alloweds.get_table_term`` plucks ``id``/``name``/``uid`` for admins
    and adds ``category`` for managers. Both fields kept optional so a
    single model handles either pluck variant."""

    id: str
    name: Optional[str] = None
    uid: Optional[str] = None
    category: Optional[str] = None


class AdminCSVValidateCreateResponse(BaseModel):
    """Response for ``POST /admin/items/users/csv/validate`` — the bulk-create
    pre-flight. Service returns the enriched row list under ``users`` and
    a parallel ``errors`` list of human-readable strings for the rows that
    were skipped. Rows are kept as ``list[dict]`` because each row mirrors
    the permissive create-input shape (``UserFromCSV``); narrowing here
    would 500 on edge fields the webapp tolerates."""

    users: list[dict]
    errors: list[str]


class AdminCSVImportResponse(BaseModel):
    """Response for ``POST /admin/items/users/csv`` and ``/admin/items/bulk/user``.

    The route reshapes the service's ``{users, errors}`` into a count +
    error list — keeping the shape so the OAS documents the same payload
    the webapp consumes."""

    created: int
    errors: list[str]


class AdminPasswordPolicyResponse(BaseModel):
    """Response for ``GET /admin/item/user/password-policy/{user_id}``.

    ``UserPolicies.get_user_policy(subtype="password", ...)`` returns the
    policy dict (or ``False`` when no policy applies). The route only ever
    calls it with ``subtype="password"``, so the shape is the password
    policy. ``False`` is normalised to ``{}`` by the route's
    ``isinstance(result, dict)`` guard so we don't have to model the
    bool variant."""

    length: Optional[int] = None
    uppercase: Optional[int] = None
    lowercase: Optional[int] = None
    digits: Optional[int] = None
    special_characters: Optional[int] = None
    not_username: Optional[bool] = None
    expiration: Optional[int] = None
    old_passwords: Optional[int] = None
    digits_last_password: Optional[int] = None


class AdminGroupListItem(AdminGroup):
    """Row shape for ``GET /admin/items/groups``.

    ``GroupsProcessed.admin_get_groups`` returns the full ``groups`` row
    merged with ``linked_groups_data`` (a denormalised array of
    ``{id, name}`` pairs from the linked groups). Inherits ``AdminGroup``
    so the canonical group fields stay strict and only the two extra
    columns are added on top."""

    linked_groups: Optional[list[str]] = None
    linked_groups_data: Optional[list[AdminSecondaryGroupRef]] = None
    quota: Optional[bool | dict] = None
    enrollment: Optional[dict] = None


class AdminLinkedGroupNamed(BaseModel):
    """``{id, name, category_name}`` lookup row used by the management nav
    response for the ``linked_groups_data`` array."""

    id: str
    name: Optional[str] = None
    category_name: Optional[str] = None


class AdminGroupNavItem(BaseModel):
    """Row shape for ``GET /admin/items/users/{nav}/groups``.

    ``UsersProcessed.admin_list_groups`` returns the full groups row with
    extra merges: ``management`` adds ``linked_groups_data``
    (with ``category_name``) and ``parent_category_name``;
    ``quotas_limits`` adds ``media_size`` / ``domains_size``. Fields kept
    optional + the ``without`` strip on ``quotas_limits`` is reflected by
    making ``enrollment``/``external_*``/``linked_groups`` optional here."""

    id: str
    uid: Optional[str] = None
    name: str
    parent_category: str
    auto: Optional[bool | dict] = None
    description: Optional[str] = None
    external_app_id: Optional[str] = None
    external_gid: Optional[str] = None
    linked_groups: Optional[list[str]] = None
    linked_groups_data: Optional[list[AdminLinkedGroupNamed]] = None
    parent_category_name: Optional[str] = None
    enrollment: Optional[dict] = None
    quota: Optional[bool | dict] = None
    limits: Optional[bool | dict] = None
    media_size: Optional[float] = None
    domains_size: Optional[float] = None


class AdminGroupFullDataResponse(AdminGroup):
    """Response for ``GET /admin/item/group/{group_id}``.

    ``GroupsProcessed.group_get_full_data`` returns the row merged with
    ``linked_groups_data``. Inherits ``AdminGroup`` and adds the two
    enrichment fields."""

    linked_groups: Optional[list[str]] = None
    linked_groups_data: Optional[list[AdminSecondaryGroupRef]] = None
    quota: Optional[bool | dict] = None
    enrollment: Optional[dict] = None
    ephimeral: Optional[EphimeralDesktopsData | bool] = None


class AdminGroupUserItem(BaseModel):
    """Row shape for ``GET /admin/items/group/{group_id}/users``.

    ``GroupsProcessed.get_users_in_group`` plucks ``id``, ``name``,
    ``username`` and ``photo`` only."""

    id: str
    name: Optional[str] = None
    username: Optional[str] = None
    photo: Optional[str] = None


class AdminGroupEnrollmentResponse(BaseModel):
    """Response for ``POST /admin/item/group/enrollment``: the new enrollment
    code (reset) or ``True`` (disable)."""

    code: Optional[str | bool] = None


class AdminCategoryItem(BaseModel):
    """Row shape for ``GET /admin/items/categories``.

    ``UsersProcessed.categories_get`` plucks ``id``/``name``/``frontend``
    only. Kept tight — the admin categories panel does not consume
    additional fields from this endpoint."""

    id: str
    name: str
    frontend: Optional[bool] = None


class AdminCategoryFrontendItem(BaseModel):
    """Row shape for ``GET /admin/items/categories/{frontend}``.

    Mirrors ``CategoriesProcessed.get_categories_frontend`` — pluck of
    ``id``, ``name``, ``custom_url_name`` (and ``frontend`` on the
    branding-domain branch). ``custom_url_name`` is always returned but
    may be empty."""

    id: str
    name: str
    custom_url_name: Optional[str] = None
    frontend: Optional[bool] = None


class AdminCategoryNavItem(BaseModel):
    """Row shape for ``GET /admin/items/users/{nav}/categories``.

    ``UsersProcessed.admin_list_categories`` returns the categories row
    (with ``quota``/``limits`` stripped on ``management``) and merges
    ``media_size``/``domains_size`` on ``quotas_limits``. The trailing
    fields stay optional so both nav variants serialise through the same
    model."""

    id: str
    name: str
    description: Optional[str] = None
    frontend: Optional[bool] = None
    custom_url_name: Optional[str] = None
    uid: Optional[str] = None
    photo: Optional[str] = None
    authentication: Optional[dict] = None
    manager_permissions: Optional[dict] = None
    quota: Optional[bool | dict] = None
    limits: Optional[bool | dict] = None
    media_size: Optional[float] = None
    domains_size: Optional[float] = None
    bastion_domain: Optional[str] = None
    ephimeral: Optional[EphimeralDesktopsData | bool] = None
    maintenance: Optional[bool] = None


class AdminCategoryDetailResponse(BaseModel):
    """Response for ``GET /admin/item/category/{category_id}`` and the create
    endpoint.

    ``ApiAdmin.get_table_item("categories", ...)`` returns the full row;
    the service then strips the authentication-secret fields and adds an
    ``is_default`` flag. ``create_category`` returns the freshly built
    document (id/name/description/frontend/custom_url_name/photo/uid +
    the four-provider authentication shell). Kept permissive on quota /
    limits / branding so legacy categories serialize cleanly."""

    id: str
    name: str
    description: Optional[str] = None
    frontend: Optional[bool] = None
    custom_url_name: Optional[str] = None
    uid: Optional[str] = None
    photo: Optional[str] = None
    authentication: Optional[dict] = None
    is_default: Optional[bool] = None
    quota: Optional[bool | dict] = None
    limits: Optional[bool | dict] = None
    branding: Optional[dict] = None
    manager_permissions: Optional[dict] = None
    maintenance: Optional[bool] = None
    recycle_bin_cutoff_time: int | None = None


class AdminCategoryUserItem(BaseModel):
    """Row shape for ``GET /admin/items/category/{category_id}/users``.

    ``UsersProcessed.list_by_category`` returns the user row enriched with
    role/group/category names + a denormalised ``secondary_groups_data``
    list — same shape as ``AdminUserFullDataResponse`` minus the
    ``photo``/``api_key``/``vpn`` columns the admin list view does not
    render."""

    id: str
    name: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None
    role_name: Optional[str] = None
    category: Optional[str] = None
    category_name: Optional[str] = None
    group: Optional[str] = None
    group_name: Optional[str] = None
    secondary_groups: Optional[list[str]] = None
    secondary_groups_data: Optional[list[AdminSecondaryGroupRef]] = None
    email: Optional[str] = None
    active: Optional[bool] = None
    provider: Optional[str] = None
    uid: Optional[str] = None
    accessed: Optional[float] = None


class AdminDeleteCheckUser(BaseModel):
    id: str
    name: Optional[str] = None
    username: Optional[str] = None
    provider: Optional[str] = None


class AdminDeleteCheckGroup(BaseModel):
    id: str
    name: Optional[str] = None


class AdminDeleteCheckDesktop(BaseModel):
    """Row shape for the ``desktops`` array of every delete-check response.

    ``UsersProcessed.user_delete_checks`` plucks ``id``/``name``/``kind``/
    ``user``/``status``/``parents`` (+ ``persistent`` /
    ``duplicate_parent_template`` on the user-table branch) and merges
    ``username``/``user_name``. Optional everywhere because the merge
    paths differ per kind."""

    id: str
    name: Optional[str] = None
    kind: Optional[str] = None
    user: Optional[str] = None
    user_name: Optional[str] = None
    username: Optional[str] = None
    status: Optional[str] = None
    parents: Optional[list[str]] = None
    persistent: Optional[bool] = None
    duplicate_parent_template: Optional[Union[str, bool]] = None


class AdminDeleteCheckTemplate(BaseModel):
    id: str
    name: Optional[str] = None
    kind: Optional[str] = None
    user: Optional[str] = None
    user_name: Optional[str] = None
    username: Optional[str] = None
    category: Optional[str] = None
    group: Optional[str] = None
    duplicate_parent_template: Optional[Union[str, bool]] = None


class AdminDeleteCheckMedia(BaseModel):
    id: str
    name: Optional[str] = None
    user: Optional[str] = None
    user_name: Optional[str] = None
    username: Optional[str] = None


class AdminDeleteCheckDeployment(BaseModel):
    id: str
    name: Optional[str] = None
    user: Optional[str] = None
    user_name: Optional[str] = None
    username: Optional[str] = None


class AdminDeleteChecksResponse(BaseModel):
    """Response for the three ``POST /admin/{user|group|category}/delete/check``
    endpoints. Service helper ``UsersProcessed.user_delete_checks`` returns
    six parallel arrays of cascaded items, plus ``storage_pools`` (count)
    on the category branch."""

    desktops: list[AdminDeleteCheckDesktop] = Field(default_factory=list)
    templates: list[AdminDeleteCheckTemplate] = Field(default_factory=list)
    deployments: list[AdminDeleteCheckDeployment] = Field(default_factory=list)
    media: list[AdminDeleteCheckMedia] = Field(default_factory=list)
    users: list[AdminDeleteCheckUser] = Field(default_factory=list)
    groups: list[AdminDeleteCheckGroup] = Field(default_factory=list)
    storage_pools: Optional[int] = None


class AdminUserTemplateItem(BaseModel):
    """Row shape for ``GET /admin/items/user/{user_id}/templates``.

    The service builds each row as ``{id, name, icon, image,
    description}`` from a ``DomainsProcessed.list_by_kind_user`` pluck.
    ``image`` is hard-coded to ``""`` for now."""

    id: str
    name: str
    icon: Optional[str] = None
    image: Optional[str] = None
    description: Optional[str] = None


class AdminUserDesktopItem(BaseModel):
    """Row shape for ``GET /admin/items/user/{user_id}/desktops``.

    ``DomainsProcessed.list_by_kind_user("desktop", ...)`` plucks the
    listed fields. ``status`` may be missing on freshly-created
    desktops."""

    id: str
    name: Optional[str] = None
    status: Optional[str] = None
    icon: Optional[str] = None
    image: Optional[str] = None
    kind: Optional[str] = None


class AdminRoleItem(BaseModel):
    """Row shape for ``GET /admin/items/roles``.

    ``UsersProcessed.get_roles`` plucks ``id``, ``name``,
    ``description`` (and orders by ``sortorder``)."""

    id: str
    name: str
    description: Optional[str] = None


class AdminSecretItem(BaseModel):
    """Row shape for ``GET /admin/items/secrets``.

    Backed by ``ApiAdmin.admin_table_list("secrets")`` — the secrets
    table carries the same fields the create-endpoint advertises
    (``id``/``kid``, ``category_id``, ``secret``, ``description``,
    ``role_id``)."""

    id: Optional[str] = None
    kid: Optional[str] = None
    category_id: Optional[str] = None
    secret: Optional[str] = None
    description: Optional[str] = None
    role_id: Optional[str] = None


class AdminSecretCreateResponse(BaseModel):
    """Response for ``POST /admin/item/secret``.

    Service returns ``{secret: <raw>}`` only — the JWT-signing key is
    surfaced once and never read back."""

    secret: str


class AdminUserVpnFileResponse(BaseModel):
    """Response for the two VPN config/install endpoints.

    ``IsardVpn.vpn_data`` returns ``{kind: "file", name, ext, mime,
    content}`` for both ``config`` (wireguard ``.conf``) and ``install``
    (a ``sh``/``vb`` setup script)."""

    kind: Literal["file"]
    name: str
    ext: str
    mime: str
    content: str


class AdminQuotaUserUsage(BaseModel):
    """Per-user quota usage block from ``QuotasProcess.process_user_quota``.

    All ``q``/``qp`` fields are emitted unconditionally — when the user
    has no quota set the service writes ``9999`` / ``0`` placeholders,
    so the int variant covers both cases."""

    user: dict
    d: int
    dq: int
    dqp: int
    r: int
    rq: int
    rqp: int
    t: int
    tq: int
    tqp: int
    i: int
    iq: int
    iqp: int
    v: int
    vq: int
    vqp: int
    m: int
    mq: int
    mqp: int
    deployments: int
    deploymentsq: int
    deploymentsqp: int
    dktpDeployment: int
    dktpDeploymentq: int
    dktpDeploymentqp: int
    startDeploymentDktp: int
    startDeploymentDktpq: int
    startDeploymentDktpqp: int


class AdminQuotaCategoryLimits(BaseModel):
    """Category- (or group-) scoped limits block returned by
    ``QuotasProcess.process_category_limits`` /
    ``get_manager_usage`` / ``get_admin_usage``.

    The two ``process_*_limits`` paths emit the full ``q``/``qp`` set;
    the manager/admin-usage paths return only the counters
    (``d``/``r``/``t``/``i``/``v``/``m``/``u``/``deployments``). All
    ``q``/``qp`` fields kept optional so the lighter shapes don't 500
    here."""

    category: Optional[dict] = None
    group: Optional[dict] = None
    d: int
    r: int
    t: int
    i: int
    v: int
    m: int
    u: Optional[int] = None
    deployments: int
    dq: Optional[int] = None
    dqp: Optional[int] = None
    rq: Optional[int] = None
    rqp: Optional[int] = None
    tq: Optional[int] = None
    tqp: Optional[int] = None
    iq: Optional[int] = None
    iqp: Optional[int] = None
    vq: Optional[int] = None
    vqp: Optional[int] = None
    mq: Optional[int] = None
    mqp: Optional[int] = None
    uq: Optional[int] = None
    uqp: Optional[int] = None
    deploymentsq: Optional[int] = None
    deploymentsqp: Optional[int] = None


class AdminQuotasResponse(BaseModel):
    """Response for ``GET /admin/items/quotas``.

    ``QuotasProcess.get`` always returns a ``user`` block and adds either
    ``limits`` (managers) or ``global`` (admins)."""

    user: AdminQuotaUserUsage
    limits: Optional[AdminQuotaCategoryLimits] = None
    global_: Optional[AdminQuotaCategoryLimits] = Field(default=None, alias="global")

    model_config = {"populate_by_name": True}


class AdminAppliedQuotaResponse(BaseModel):
    """Response for ``GET /admin/item/user/appliedquota/{user_id}``.

    ``Quotas.get_applied_quota`` returns ``{quota, restriction_applied}``
    where ``quota`` is either ``False`` or the quota dict and
    ``restriction_applied`` is one of ``user_quota`` / ``group_quota`` /
    ``category_quota``."""

    quota: bool | dict
    restriction_applied: str


class AdminUserIdResponse(BaseModel):
    """Response for ``GET /admin/item/user/email-category/{email}/{category}``.

    Returns ``{id: <user-id-or-None>}`` — service may return ``None`` when
    no user matches."""

    id: Optional[str] = None


class AdminMigrationStartedResponse(BaseModel):
    """Response for ``PUT /admin/item/user/migrate/{user_id}/{target_user_id}``.

    On success the service returns ``({}, 200)``; on validation failure it
    returns ``({"errors": [...]}, 428)``. Both shapes serialise through a
    single optional-``errors`` model."""

    errors: Optional[list] = None


class AdminMigrationErrorsResponse(BaseModel):
    """Response for ``GET /admin/item/user/migrate/check/{user_id}/{target_user_id}``.

    Service returns the raw error list; the route wraps it as
    ``{"errors": [...]}``."""

    errors: list


class AdminCheckMigratedResponse(BaseModel):
    """Response for ``POST /admin/item/user/check/migrated``.

    Service returns a single boolean; the route wraps it as
    ``{"migrated": <bool>}``."""

    migrated: bool


class AdminBastionDomainResponse(BaseModel):
    """Response for the two ``/admin/item/category/{category_id}/bastion_domain``
    endpoints.

    GET returns ``{bastion_domain: <str|False|None>}`` — string when set,
    ``False`` when explicitly unset, ``None`` when missing. PUT echoes the
    request body shape (same union)."""

    bastion_domain: Union[str, bool, None] = None
