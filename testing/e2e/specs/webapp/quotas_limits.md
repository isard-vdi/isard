# Quotas & Limits management in webapp

Human-readable functional specification of the **view** and **edit** flows
for **user**, **group**, and **category** quotas and limits from the legacy
admin, for both **administrators** and **managers**. Serves as the contract
for the E2E test `tests/webapp/quotas_limits.spec.js`.

## Scope

- **Component**: administration panel.
- **Screen**: **Quotas / Limits** section, route
  `/isard-admin/admin/users/QuotasLimits` (template
  `admin/pages/users_quotas_limits.html`). The page renders three DataTables
  — **Users** (`#users`), **Categories** (`#categories`) and **Groups**
  (`#groups`).
- **Actions covered**:
  - Preview a user's effective quota without editing.
  - Edit a user's quota: *apply the group quota* (inherit) or *apply a custom
    quota*.
  - Edit a group's quota: *apply the category quota*, *apply a custom quota*,
    *apply to a specific role*, *override the group users' current quota*.
  - Edit a group's limits: *apply the category limits*, *apply custom limits*.
  - Edit a category's quota: *apply unlimited quota*, *apply a custom quota*,
    *apply to a specific role*, *override the category users' current quota*.
  - Edit a category's limits: *apply unlimited limits*, *apply custom limits*.
  - Manager role: the same user/group view+edit flows as the admin (within its
    own category); only own-category users/groups/categories are visible; and
    editing its own quota logs it out. Category quota/limits editing is
    admin-only — the webapp does not render the category edit controls for a
    manager.
- **Out of scope**: the enforcement of quotas/limits at desktop/template/media
  creation time, the storage/size accounting columns, the user-migration
  quota-check toggle (`#migration-check-quotas-checkbox`), and group/user
  *management* (create/edit/delete of the entities themselves — that is the
  `users_management` screen).

## Quota vs Limits

- **Quota** = the per-entity *allowance* (what one user — or each user of a
  group/category — may create/run). Resolution is **user → group → category**:
  a user with `quota = false` inherits its group quota; a group with
  `quota = false` inherits its category quota; a category with `quota = false`
  is **unlimited**.
- **Limits** = the *aggregate cap* for a whole group or category (e.g. the
  maximum number of users, or total resources across the group/category).
  Limits exist for groups and categories only, not for individual users.

A single **`#unlimited`** checkbox (label *"Apply &lt;…&gt;"*) toggles between
inherit/unlimited and custom in every edit modal:

| Modal | `.apply` label | Checkbox checked ⇒ request | Checkbox unchecked ⇒ request |
| --- | --- | --- | --- |
| User quota | "Apply group quota" | `quota: false` (inherit group) | `quota: {…}` |
| Group quota | "Apply category quota" | `quota: false` (inherit category) | `quota: {…}` |
| Group limits | "Apply category limits" | `limits: false` (inherit category) | `limits: {…}` |
| Category quota | "Apply unlimited quota" | `quota: false` (unlimited) | `quota: {…}` |
| Category limits | "Apply unlimited" | `limits: false` (unlimited) | `limits: {…}` |

When checked, the `quota-*` / `limits-*` number inputs are disabled; when
unchecked they are enabled and serialised by `quota2dict` / `userQuota2dict`.

### Quota/limits hierarchy

A child's quota/limits may **not exceed** its parent's: **`user ≤ group ≤
category`**, and every quota field is capped by the entity's effective
**limits**. This is enforced on both sides:

- **Webapp** — when an edit modal opens, `setQuotaMax` / `setLimitsMax`
  (`static/js/snippets/quota.js`) read the parent's effective limits from
  `GET /api/v4/admin/quota/{kind}/{id}` and set each input's `max`; Parsley then
  blocks **Update** if a value exceeds it (and the `PUT` never fires).
- **Backend** — `update_group_quota` / `update_group_limits`
  (`_common/.../groups.py`) and the user-quota check in apiv4
  `services/admin/users.py` reject an over-parent value with
  `precondition_required` (HTTP 428).

Consequently the tests pick **sample values that nest**: the custom-limits
sample is a complete, generous dict (every field at/above the quota samples), so
a group/category whose limits a scenario sets never caps a later child quota
edit below its sample (see *Sample values*).

## Session revocation on a user edit (important)

`PUT /api/v4/admin/item/user/{id}` revokes the edited user's session as a side
effect (`update_user(..., revoke=True)` → `revoke_user_session(user_id)` via the
`isard-sessions` gRPC service). This fires on **any** user edit, not just a
quota change. The JWT cookie stays in the browser but its `session_id` is now
invalid, so the **next** authenticated request returns **HTTP 401
`unauthorized` ("Session expired")** and the webapp's global `auth.js`
`ajaxError` handler redirects to `/isard-admin/logout`. The edit PUT itself
returns **204** with no logout signal — the logout only surfaces after a
follow-up action. This is exercised in **SM8** and is the reason the suite
must never edit the quota of an account that is (or will remain) logged in.

## Common roles and prerequisites

| Element | Admin scenarios (SA…) | Manager scenarios (SM…) |
| --- | --- | --- |
| Account | `admin_e2e_NN` (per worker), role `admin`, category `default` | `qle2e-manager`, role `manager`, category `qle2e` (SM8 uses `qle2e-logout-mgr`) |
| Fixture | `authenticatedPage` + `apiv4Admin` (with `bridgeAdminSession`) | a worker login as `qle2e-manager` (+ `bridgeAdminSession`); SM8 logs in fresh |
| Session | Logged in to the webapp; Flask admin session bridged | same |
| Page | On **Quotas / Limits**; the relevant `#users` / `#groups` / `#categories` table has loaded | same |
| Order | Run **first** | Run **after** the admin suite (shared fixtures) |

> The manager is seeded **inside** the dedicated non-Default test category
> `qle2e` precisely so it can edit the *same* fixtures the admin edits and so
> the **Default** category is never touched. A login fixture for
> `qle2e-manager` must be added (mirror the `managerE2EPage` worker fixture in
> `fixtures/login.js`), plus `qle2e` in the `categories` map and `qle2e-manager`
> in the `users` map.

### Safety rules (mandatory)

1. **Never** edit the **Default** category's quota or limits. (With the design
   below it is never the target of any scenario.)
2. **Never** mutate the quota of an account that is/stays logged in — it logs
   them out (see above). Admins log in as `admin_e2e_NN` and never appear in
   `qle2e`; the manager `qle2e-manager` lives in `qle2e-mgr-home` (never an
   override target) and its own quota is never edited; the self-edit logout test
   uses the throwaway `qle2e-logout-mgr`.
3. The manager suite runs **after** the admin suite so the two roles never
   mutate the shared `qle2e` fixtures concurrently and the manager is not
   logged in while the admin mutates state.

## Common data

### Dedicated seed fixtures (prerequisite)

All edit targets live in **one dedicated, non-Default, non-login category**
`qle2e`, referenced by **no other spec**. Both the admin and `qle2e-manager`
edit the **same** `qle2e-group` / `qle2e-user` / `qle2e-adv`. The managers live
in a **separate** group `qle2e-mgr-home`, so the group-/category-override
scenarios never clobber a logged-in manager's own quota. All entities are
seeded via `testing/db` (populated by `testing/e2e/global-setup.js` →
`testing/db/populate_test_db.py`) and start fully inherited (`quota: false`,
`limits: false`).

| Entity | id / name | Category | Group | Role | Notes |
| --- | --- | --- | --- | --- | --- |
| Category | `qle2e` / "QuotasLimits E2E" (`frontend: false`, has login `url`) | — | — | — | category-level target (admin); manager's own category |
| Group | `qle2e-group` / "QL E2E Group" | `qle2e` | — | — | shared user/group edit target |
| User | `qle2e-user` / "ql_user" | `qle2e` | `qle2e-group` | `user` | role-scoped + override target |
| User | `qle2e-adv` / "ql_adv" | `qle2e` | `qle2e-group` | `advanced` | second role; proves role-scoping isolates roles |
| Group | `qle2e-mgr-home` / "QL E2E Mgr Home" | `qle2e` | — | — | hosts the managers only; never an override target |
| User (manager) | `qle2e-manager` / "ql_manager" | `qle2e` | `qle2e-mgr-home` | `manager` | main manager account (own quota never edited ⇒ stable session for SM1–SM7) |
| User (manager) | `qle2e-logout-mgr` / "ql_logout_mgr" | `qle2e` | `qle2e-mgr-home` | `manager` | throwaway for the self-edit logout test (SM8) |

`frontend: false` keeps `qle2e` out of the login dropdown; a login `url` is
still required so the managers can sign in via `/login/all/<url>`.

### Quota fields (`quota-*`, all entities)

`desktops`, `volatile`, `templates`, `isos`, `deployments_total`,
`deployment_users`, `running`, `vcpus`, `memory`, `started_deployment_desktops`,
`desktops_disk_size`, `total_size`, `total_soft_size`.

> **Template bug** — `quota_edit.html` renders the *"Deploy users"* field
> twice (both `id/name="quota-deployment_users"`) and never renders
> `quota-deployment_desktops`; that field cannot be set from this form, so
> custom-quota scenarios assert only the editable fields and treat
> `deployment_desktops` as out of scope.

### Limits fields (`limits-*`, groups & categories)

`users`, `desktops`, `volatile`, `templates`, `isos`, `deployments_total`,
`running`, `vcpus`, `memory`, `desktops_disk_size`, `total_size`,
`total_soft_size`.

### Sample values

| Field | Sample | Notes |
| --- | --- | --- |
| Custom quota | `{desktops: 7, running: 3, vcpus: 4, memory: 6, …}` (SM2b uses a distinct `{desktops: 9, running: 5, vcpus: 6, memory: 8}`) | distinct from defaults so a change is observable; nests **below** the custom-limits ceiling |
| Custom limits | complete, generous dict — `{users: 9, desktops: 12, volatile: 12, running: 10, templates: 12, isos: 12, memory: 64, vcpus: 32, desktops_disk_size: 200, total_size: 500, total_soft_size: 400, deployments_total: 12}` | every field is set explicitly and sits **at/above** the quota samples, so the parent-derived form cap never blocks a child quota edit (a partial dict would leave the rest at the restrictive form defaults — e.g. `vcpus:1`, `memory:2` — and cap children) |
| Role | `all_roles` (default) or `user` | `#add-role` select; `all_roles` ⇒ backend `role = False` |
| Override | `#propagate` checkbox | only shown when role = `all_roles` (quota); always shown for category limits |

The id of every entity whose quota/limits a test mutates is stored in
`testInfo.annotations` (types `ql-user`, `ql-group`, `ql-category`) so
`afterEach` can reset it even if assertions fail.

### Key selectors

| Area | Selector |
| --- | --- |
| User row expand | `#users td.details-control` |
| User preview panel | `#show-users-quota-<id>` (quota only; **no** limits panel is rendered for users) |
| User edit button | `.template-detail-users .btn-edit` → modal `#modalEditUser`, submit `#modalEditUser #send` |
| Group row expand | `#groups td.details-show` |
| Group edit quota / limits | `.template-detail-groups .btn-edit-group-quotas` / `.template-detail-groups .btn-edit-limits` |
| Category row expand | `#categories td.details-show` |
| Category edit quota / limits | `.template-detail-categories .btn-edit-category-quotas` / `.template-detail-categories .btn-edit-limits` |
| Shared quota modal | `#modalEditQuota` (role `#add-role`, override `#propagate`), submit `#modalEditQuota #send` |
| Shared limits modal | `#modalEditLimits` (override `#propagate`), submit `#modalEditLimits #send` |
| Inherit/unlimited toggle | `#unlimited` (iCheck) inside the open modal/panel |

> **Binding quirk** — `.btn-edit-limits`, `#modalEditLimits #send` and the
> `#add-role` change handler are bound by **both** `groups_quotas_limits.js`
> and `categories_quotas_limits.js` (each with `.off().on()`), so the
> last-expanded detail panel wins. Tests must keep only **one** row expanded
> at a time and target buttons inside the specific
> `.template-detail-{groups|categories}` panel.

---

# Admin scenarios (run first)

## Scenario SA1 — *admin previews a user's quota without editing*

### Given
1. The admin is on **Quotas / Limits**, the `#users` table has loaded.

### When
1. They click the expand control (`td.details-control`) on the `qle2e-user`
   row.
2. The detail panel renders.

### Then
1. The panel `#show-users-quota-<id>` is visible and its `quota-*` inputs are
   **disabled** (read-only); the `.apply` label reads "group quota".
2. The displayed values match `GET /api/v4/admin/quota/user/<id>` — the
   effective quota resolved through group → category (if the user inherits,
   the `#unlimited` checkbox is shown checked).
3. **No** `PUT /api/v4/admin/item/user/<id>` call is made (pure read).
4. (Users have no limits preview panel — only the quota panel is rendered.)

---

## Scenario SA2 — *admin edits a user's quota*

> Target: `qle2e-user`. `afterEach` resets it to `quota: false`.

### Scenario SA2a — *apply the group quota (inherit)*

#### Given
1. `qle2e-user` has a custom quota (the test sets one first, or it is seeded so).

#### When
1. On the user row, press **Edit** (`.btn-edit`) → `#modalEditUser` opens
   ("Edit user quota").
2. Check the **`#unlimited`** checkbox (label "Apply group quota").
3. Press **Update user** (`#modalEditUser #send`).

#### Then
1. `PUT /api/v4/admin/item/user/<id>` is called with body
   `{ id, quota: false }` and status `< 400`.
2. A "User updated successfully" notification appears and the modal closes.
3. Queried via API, `qle2e-user.quota === false` (it now inherits the group
   quota).

### Scenario SA2b — *apply a custom quota*

#### When
1. Open the edit modal; ensure `#unlimited` is **unchecked**; set the
   `quota-*` fields to the sample custom quota.
2. Press **Update user**.

#### Then
1. `PUT /api/v4/admin/item/user/<id>` is called with body
   `{ id, quota: { … } }` and status `< 400`.
2. Queried via API, `qle2e-user.quota` equals the entered dict (on the
   editable fields).

---

## Scenario SA3 — *admin edits a group's quota*

> Target group `qle2e-group`; member users `qle2e-user` (role `user`) and
> `qle2e-adv` (role `advanced`). `afterEach` resets the group to
> `quota: false` and both users to `quota: false`.

### Scenario SA3a — *apply the category quota (inherit)*

#### When
1. Expand `qle2e-group` (`td.details-show`), press **Quotas**
   (`.btn-edit-group-quotas`) → `#modalEditQuota` opens (`.kind` = "group",
   `.apply` = "category quota", `#add-role` defaulted to "All roles").
2. Check `#unlimited`; press **Update quotas** (`#modalEditQuota #send`).

#### Then
1. `PUT /api/v4/admin/item/quota/group/<id>` body
   `{ quota: false, role: "all_roles" }`, status `< 400`.
2. Group queried via API has `quota === false`.

### Scenario SA3b — *apply a custom quota (group default only)*

#### When
1. Open the group quota modal; uncheck `#unlimited`; keep role **All roles**;
   leave `#propagate` **unchecked**; set the custom quota; submit.

#### Then
1. `PUT …/quota/group/<id>` body `{ quota: {…}, role: "all_roles" }`,
   status `< 400`.
2. The group's `quota` equals the entered dict.
3. The existing members `qle2e-user` and `qle2e-adv` are **unchanged**
   (propagate off ⇒ only the group default is set).

### Scenario SA3c — *apply the changes to a specific role*

#### When
1. Open the group quota modal; uncheck `#unlimited`; select **role = `user`**
   in `#add-role` (this hides `#propagate`); set the custom quota; submit.

#### Then
1. `PUT …/quota/group/<id>` body `{ quota: {…}, role: "user" }`,
   status `< 400`.
2. `qle2e-user` (role `user`) now has the new quota; `qle2e-adv` (role
   `advanced`) is **unchanged**; the group document's `quota` is **unchanged**
   (a specific role updates only the matching existing users, not the group
   default).

### Scenario SA3d — *override the group users' current quota*

#### When
1. Open the group quota modal; uncheck `#unlimited`; keep role **All roles**;
   **check `#propagate`** (label "Override group users current quota"); set the
   custom quota; submit.

#### Then
1. `PUT …/quota/group/<id>` body
   `{ quota: {…}, role: "all_roles", propagate: true }`, status `< 400`.
2. The group's `quota` is set **and** both `qle2e-user` and `qle2e-adv`
   have their `quota` overwritten with the new dict.

---

## Scenario SA4 — *admin edits a group's limits*

> Target `qle2e-group`. The group-limits modal hides `#propagate` and has no
> role selector. `afterEach` resets to `limits: false`.

### Scenario SA4a — *apply the category limits (inherit)*

#### When
1. Expand `qle2e-group`, press **Limits**
   (`.template-detail-groups .btn-edit-limits`) → `#modalEditLimits`
   (`.apply` = "category limits"); check `#unlimited`; submit
   (`#modalEditLimits #send`).

#### Then
1. `PUT /api/v4/admin/item/limits/group/<id>` body `{ limits: false }`,
   status `< 400`.
2. Group `limits === false`.

### Scenario SA4b — *apply custom limits*

#### When
1. Open the group limits modal; uncheck `#unlimited`; set `limits-*` (incl.
   `limits-users`); submit.

#### Then
1. `PUT …/limits/group/<id>` body `{ limits: {…} }`, status `< 400`.
2. Group `limits` equals the entered dict.

---

## Scenario SA5 — *admin edits a category's quota*

> Target the dedicated `qle2e` category. **Admin only** — the endpoint is on
> the admin router. `afterEach` resets the category to `quota: false` and (for
> SA5c/SA5d) the affected `qle2e` users to `quota: false`.

### Scenario SA5a — *apply unlimited quota*

#### When
1. Expand `qle2e` in `#categories`, press **Quotas**
   (`.btn-edit-category-quotas`) → `#modalEditQuota` (`.kind` = "category",
   `.apply` = "unlimited quota"); check `#unlimited`; submit.

#### Then
1. `PUT /api/v4/admin/item/quota/category/<id>` body
   `{ quota: false, role: "all_roles", table: "categories" }`, status `< 400`.
2. Category `quota === false` (unlimited).

### Scenario SA5b — *apply a custom quota (category default only)*

#### When
1. Open the category quota modal; uncheck `#unlimited`; role **All roles**;
   `#propagate` **unchecked**; set the custom quota; submit.

#### Then
1. `PUT …/quota/category/<id>` body
   `{ quota: {…}, role: "all_roles", table: "categories" }`, status `< 400`.
2. Category `quota` equals the entered dict; its groups and users
   (`qle2e-group`, `qle2e-user`, `qle2e-adv`) are **unchanged**.

### Scenario SA5c — *apply the changes to a specific role*

#### When
1. Open the category quota modal; uncheck `#unlimited`; select **role =
   `user`**; set the custom quota; submit.

#### Then
1. `PUT …/quota/category/<id>` body
   `{ quota: {…}, role: "user", table: "categories" }`, status `< 400`.
2. The change cascades to the category's groups → only role-`user` users
   (`qle2e-user`) get the new quota; `qle2e-adv` and the category document's
   `quota` are **unchanged**.

### Scenario SA5d — *override the category users' current quota*

#### When
1. Open the category quota modal; uncheck `#unlimited`; role **All roles**;
   **check `#propagate`** (label "Override category users current quota"); set
   the custom quota; submit.

#### Then
1. `PUT …/quota/category/<id>` body
   `{ quota: {…}, role: "all_roles", propagate: true, table: "categories" }`,
   status `< 400`.
2. The category `quota` is set **and** `qle2e-user` / `qle2e-adv` quotas are
   overwritten with the new dict.

> **Cleanup note** — this category-wide propagate also reaches
> `qle2e-mgr-home` → `qle2e-manager` / `qle2e-logout-mgr`; the `afterEach`
> must reset every `qle2e` user to `quota: false`. This is safe because the
> managers only log in **after** the admin suite (and its cleanup) completes.

---

## Scenario SA6 — *admin edits a category's limits*

> Target `qle2e`. The category-limits modal **shows** `#propagate` (label
> "Override category groups current limits"). `afterEach` resets to
> `limits: false`.

### Scenario SA6a — *apply unlimited limits*

#### When
1. Expand `qle2e`, press **Limits**
   (`.template-detail-categories .btn-edit-limits`) → `#modalEditLimits`
   (`.kind` = "category groups", `.apply` = "unlimited"); check `#unlimited`;
   submit.

#### Then
1. `PUT /api/v4/admin/item/limits/category/<id>` body `{ limits: false }`,
   status `< 400`.
2. Category `limits === false`.

### Scenario SA6b — *apply custom limits*

#### When
1. Open the category limits modal; uncheck `#unlimited`; set `limits-*`;
   leave `#propagate` unchecked; submit.

#### Then
1. `PUT …/limits/category/<id>` body `{ limits: {…} }`, status `< 400`.
2. Category `limits` equals the entered dict.

---

# Manager scenarios (run after the admin suite)

> Logged in as `qle2e-manager` (category **`qle2e`**). Managers re-run the same
> user/group view+edit flows as the admin, on the **same** `qle2e` fixtures,
> proving managers hold that authority within their own category — plus the
> scoping checks. (Category quota/limits editing is admin-only and the webapp
> does not render those edit controls for a manager, so there is no manager
> category-edit scenario.) Each mutating SM scenario verifies via API and resets
> the target back to inherited in `afterEach`.

## Scenario SM1 — *manager previews a user's quota without editing*

Mirror of SA1 on `qle2e-user`: expanding the row shows the read-only
`#show-users-quota-<id>` panel (`quota-*` disabled) with values equal to
`GET …/quota/user/<id>`; **no** `PUT` is fired.

---

## Scenario SM2 — *manager edits a user's quota* (target `qle2e-user`)

- **SM2a — apply the group quota:** check `#unlimited` → `PUT …/item/user/<id>`
  `{ id, quota: false }`, status `< 400`; persisted `quota === false`.
- **SM2b — apply a custom quota:** uncheck, set fields → `{ id, quota: {…} }`;
  persisted `quota` equals the entered dict.

---

## Scenario SM3 — *manager edits a group's quota* (target `qle2e-group`)

> The manager is in `qle2e-mgr-home`, **not** in `qle2e-group`, so the override
> case never touches the manager's own quota.

- **SM3a — apply the category quota:** `#unlimited` → `{ quota: false,
  role: "all_roles" }`; group `quota === false`.
- **SM3b — apply a custom quota:** custom, All roles, propagate off →
  `{ quota: {…}, role: "all_roles" }`; group default set; members unchanged.
- **SM3c — apply to a specific role:** role `user` → `{ quota: {…}, role:
  "user" }`; only `qle2e-user` updated; `qle2e-adv` + group default unchanged.
- **SM3d — override the group users' current quota:** All roles + `#propagate`
  → `{ quota: {…}, role: "all_roles", propagate: true }`; group default + both
  members overwritten.

---

## Scenario SM4 — *manager edits a group's limits* (target `qle2e-group`)

- **SM4a — apply the category limits:** `#unlimited` → `{ limits: false }`;
  group `limits === false`.
- **SM4b — apply custom limits:** `{ limits: {…} }` (incl. `limits-users`);
  persisted dict.

---

## Scenario SM5 — *manager only sees users from its own category*

### Then
1. `GET /api/v4/admin/items/users/quotas_limits/users` returns only users
   whose `category === "qle2e"` (`qle2e-user`, `qle2e-adv`, `qle2e-manager`,
   `qle2e-logout-mgr`); users from **Default** and every other category are
   **absent**.
2. In the table, every visible row is a `qle2e` user; the **Category** column
   is hidden for managers.

---

## Scenario SM6 — *manager only sees groups from its own category*

### Then
1. `GET …/quotas_limits/groups` returns only `qle2e` groups
   (`qle2e-group`, `qle2e-mgr-home`); groups of other categories are **absent**.
2. The **Category** column is hidden in `#groups`.

---

## Scenario SM7 — *manager only sees its own category*

### Then
1. `GET …/quotas_limits/categories` returns exactly **one** category
   (`qle2e`); **Default** and every other category are **absent**.
2. The `#categories` table shows a single row, `qle2e`.

---

## Manager category edits — not exposed in the UI

The category quota/limits edit endpoints are **admin-only**, and for a manager
the webapp **does not render** the category **Quotas** / **Limits** edit buttons
on its own category row — so there is no manager-facing category-edit flow to
exercise. The manager's category coverage is therefore the read-only scoping
check (SM7) only.

---

## Scenario SM8 — *editing its own quota logs the manager out*

> Runs as a **dedicated fresh login** as `qle2e-logout-mgr` (its own browser
> context, **not** the shared manager fixture), so logging it out never poisons
> SM1–SM7. Order-independent.

### Given
1. `qle2e-logout-mgr` is logged in and on the **Quotas / Limits** page; the
   `#users` table has loaded.

### When
1. The manager locates its **own** row (`qle2e-logout-mgr`) in `#users`, presses
   **Edit** (`.btn-edit`), changes its quota (any change — e.g. a custom quota),
   and presses **Update user**.
2. `PUT /api/v4/admin/item/user/<qle2e-logout-mgr>` returns **204** and a
   "User updated successfully" notification appears — **no immediate logout**.
3. The test triggers an **extra authenticated action**: reload the
   Quotas / Limits page (so its DataTables re-fetch from
   `/api/v4/admin/items/...`), or perform a row action / navigation.

### Then
1. The follow-up `/api/v4/...` request returns **HTTP 401** with
   `error: "unauthorized"` / `description: "Session expired"`.
2. The webapp's global `ajaxError` handler redirects to `/isard-admin/logout`,
   and the browser ends up on the **login** page (the session is rejected even
   though the JWT cookie is still present).
3. Assert the redirect to login (and/or capture the 401 on the follow-up
   request).

### Cleanup
1. Reset `qle2e-logout-mgr.quota` back to `false` via **`apiv4Admin`** — the
   manager is now logged out and cannot reset itself.

> The logout is triggered by *any* user edit (not specifically a quota change);
> this scenario exercises it through a quota edit per the requirement.

---

## Cleanup (afterEach)

1. Recover the mutated entity ids from `testInfo.annotations`
   (`ql-user` / `ql-group` / `ql-category`).
2. Reset each target back to its seeded inherited state:
   - user → `PUT /api/v4/admin/item/user/<id>` with `{ quota: false }`.
   - group → `PUT …/quota/group/<id>` `{ quota: false, role: "all_roles" }`
     and `PUT …/limits/group/<id>` `{ limits: false }`.
   - category → `PUT …/quota/category/<id>`
     `{ quota: false, role: "all_roles", table: "categories" }` and
     `PUT …/limits/category/<id>` `{ limits: false }`.
   - Override scenarios (SA3d/SA5d, SM3d) additionally reset the affected member
     users (`qle2e-user`, `qle2e-adv`) to `{ quota: false }`. The category-wide
     SA5d cleanup also resets `qle2e-manager` / `qle2e-logout-mgr`.
   - SM8 resets `qle2e-logout-mgr` via the **admin** client.
3. Cleanup errors are silenced so they do not mask the real failure.
4. The **Default** category and the admin login accounts are **never**
   edited.

## Concurrency & ordering

- The admin scenarios and the manager scenarios edit the **same** `qle2e`
  fixtures, so they must not run concurrently. The **manager suite runs strictly
  after the admin suite** — e.g. a serial top-level `test.describe.serial` with
  the admin describe(s) ordered before the manager describe(s), or two
  Playwright projects with `manager` depending on `admin`. This also guarantees
  `qle2e-manager` is **not** logged in while the admin mutates state (and the
  admin cleanup has reset its quota to `false` before the manager signs in).
- Mutating scenarios within each suite also share the single `qle2e` fixture, so
  they run serially. (Alternative for parallelism: per-worker `qle2e-*-NN`
  fixture sets.)

---

## Expected results — global summary

| Scenario | Role | Covered? | Key checks |
| --- | --- | --- | --- |
| SA1 — Preview user quota | admin | ✅ | Panel read-only (disabled), values = `GET /admin/quota/user/<id>`, no PUT |
| SA2a — User apply group quota | admin | ✅ | `PUT user` `{quota:false}`, persisted `quota===false` |
| SA2b — User custom quota | admin | ✅ | `PUT user` `{quota:{…}}`, persisted dict |
| SA3a — Group apply category quota | admin | ✅ | `PUT quota/group` `{quota:false}`, group `quota===false` |
| SA3b — Group custom quota | admin | ✅ | group `quota` set; members unchanged |
| SA3c — Group apply to role | admin | ✅ | role `user` updated; `advanced` + group default unchanged |
| SA3d — Group override users | admin | ✅ | `propagate:true`; group + all members overwritten |
| SA4a — Group apply category limits | admin | ✅ | `PUT limits/group` `{limits:false}` |
| SA4b — Group custom limits | admin | ✅ | `PUT limits/group` `{limits:{…}}` incl. `users` |
| SA5a — Category unlimited quota | admin | ✅ | `PUT quota/category` `{quota:false}` |
| SA5b — Category custom quota | admin | ✅ | category `quota` set; groups/users unchanged |
| SA5c — Category apply to role | admin | ✅ | cascades to role `user` only; `advanced`/category default unchanged |
| SA5d — Category override users | admin | ✅ | `propagate:true`; category + users overwritten |
| SA6a — Category unlimited limits | admin | ✅ | `PUT limits/category` `{limits:false}` |
| SA6b — Category custom limits | admin | ✅ | `PUT limits/category` `{limits:{…}}` |
| SM1 — Manager preview user quota | manager | ✅ | read-only panel; no PUT |
| SM2a/b — Manager user quota (group / custom) | manager | ✅ | `PUT user` ok within own category |
| SM3a–d — Manager group quota (category/custom/role/override) | manager | ✅ | same semantics as SA3, own category |
| SM4a/b — Manager group limits (category / custom) | manager | ✅ | `PUT limits/group` ok |
| SM5 — Manager sees own users only | manager | ✅ | list scoped to `qle2e`; other categories absent; Category col hidden |
| SM6 — Manager sees own groups only | manager | ✅ | list scoped to `qle2e` |
| SM7 — Manager sees own category only | manager | ✅ | exactly `qle2e` returned; Default absent |
| SM8 — Self-edit logs the manager out | manager | ✅ | edit own quota → next request 401 `unauthorized` → redirect to login |

> Mark any scenario as `test.skip` / `test.fail` once the project confirms it
> depends on a still-open bug (see Known issues).

## APIs touched by the flows (reference)

| Method | Path | Purpose | Router / who |
| --- | --- | --- | --- |
| GET | `/api/v4/admin/items/users/quotas_limits/users` | Users table (manager-scoped) | manager + admin |
| GET | `/api/v4/admin/items/users/quotas_limits/groups` | Groups table (manager-scoped) | manager + admin |
| GET | `/api/v4/admin/items/users/quotas_limits/categories` | Categories table (manager-scoped) | manager + admin |
| GET | `/api/v4/admin/quota/{kind}/{id}` | Prefill/preview quota+limits (`kind` = user/group/category) | manager + admin |
| GET | `/api/v4/admin/item/user/{id}` | Prefill the user edit modal | manager + admin |
| PUT | `/api/v4/admin/item/user/{id}` | Update user quota; body `{id, quota:false\|{…}}` → 204; **revokes the user's session** | manager + admin (owns user) |
| PUT | `/api/v4/admin/item/quota/group/{id}` | Update group quota; body `{quota, role, propagate?}` → 204 | manager + admin (owns category) |
| PUT | `/api/v4/admin/item/limits/group/{id}` | Update group limits; body `{limits}` → 204 | manager + admin (owns category) |
| PUT | `/api/v4/admin/item/quota/category/{id}` | Update category quota; body `{quota, role, propagate?, table}` → 204 | **admin only** |
| PUT | `/api/v4/admin/item/limits/category/{id}` | Update category limits; body `{limits, propagate?}` → 204 | **admin only** |

Semantics (verified in `_common` `groups.py` / `categories.py`):
`role = "all_roles"` ⇒ backend `role = False`. With `all_roles` and no
`propagate`, only the group/category **document** quota is set (the default for
future users). With `propagate`, the default **and** every existing user's quota
are overwritten. With a **specific role**, the document default is left
untouched and only the existing users of that role are updated. Category quota
with `propagate`/`role` cascades into each child group. Authorization:
`owns_category_id` (admin always; manager only its own category); category
quota/limits endpoints are **admin-only**, and the webapp does not expose those
edit controls to managers.

## Relevant database state

- `users.quota` — `false` (inherit group/category) or a quota dict.
- `groups.quota` / `groups.limits` — `false` (inherit) or a dict.
- `categories.quota` / `categories.limits` — `false` (unlimited) or a dict.
- The `isard-sessions` store — a user edit revokes that user's session, so its
  JWT's `session_id` no longer validates (SM8).
- After each test the dedicated `qle2e*` fixtures and their members are reset
  to inherited; **Default** and the admin accounts remain untouched throughout.

## Known issues / cases not covered

1. **Manager category edits are not exposed.** The category quota/limits edit
   endpoints are admin-only, and the webapp does not render the category
   **Quotas**/**Limits** edit buttons for a manager on its own category row, so
   there is no manager category-edit flow to exercise (the manager's category
   coverage is the read-only scoping check, SM7).
2. **Duplicate "Deploy users" field.** `quota_edit.html` renders
   `quota-deployment_users` twice and omits `quota-deployment_desktops`; the
   latter cannot be set via the UI, so custom-quota scenarios do not assert on
   it.
3. **Shared limits handlers.** `.btn-edit-limits` / `#modalEditLimits #send` /
   the `#add-role` change handler are bound by both the groups and categories
   scripts; tests keep a single row expanded and scope to the correct
   `.template-detail-*` panel.
4. **Not covered:** runtime enforcement of quotas/limits (creation/run blocked
   when exceeded), the storage-size accounting columns, and the
   user-migration quota-check toggle.
