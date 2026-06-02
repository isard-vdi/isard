# Users management in webapp

Human-readable functional specification of the **user**, **category**,
**group**, **external app**, and **role** management flows on the
Management screen of the legacy admin webapp, for both the **admin** and
**manager** roles. Serves as the contract for the E2E test
`tests/webapp/users_management.spec.js`.

## Scope

- **Component**: administration panel (legacy webapp).
- **Screen**: `/isard-admin/admin/users/Management`, with the **Users**,
  **Categories**, **Groups**, **External apps**, and **Roles** panels.
- **Actions covered**:
  - User CRUD plus lifecycle actions (reset password, enable/disable,
    reset VPN, impersonate, logout, migrate, logs).
  - Bulk actions (bulk edit/delete, CSV update, CSV bulk create, export
    CSV).
  - Category and group CRUD plus group-specific actions (empty group,
    enrollment).
  - Category feature modals (authentication, branding, login
    notification, bastion domain).
  - Per-category manager permissions (authentication / branding / login
    notification / GPU plannings) — saved by the admin and gated for managers.
  - External-app (secret) and role actions.
  - Role-based behaviour differences for managers.
- **Out of scope**:
  - Ephemeral-desktops configuration (ignored per request).
  - Full identity-provider enrollment redemption after logout
    (Google/LDAP/SAML) — needs dedicated IdP fixtures/stubs.
  - Deep DB-only side effects that the browser cannot observe (flagged
    per scenario).

## Common role and prerequisites

| Element | Expected value |
| --- | --- |
| Admin role | Administrator of the `default` category (`admin_e2e_NN`, one per worker) |
| Manager role | `manager_e2e_01` — role `manager`, bound to the `default` category |
| Session | Logged in to the webapp **and** bridged into the Flask admin (`POST /isard-admin/login`) |
| Users table | Loaded; a specific user's row is reached by searching its username (see note below) |
| Categories / Groups | At least one category and one group exist |

## Common data

| Field | Sample value | Notes |
| --- | --- | --- |
| Username | `e2e_umgmt_<timestamp>` | Created via API in each test |
| Name | `E2E Mgmt <timestamp>` | Human-readable |
| Email | `<username>@example.test` | Must pass the email-format validation |
| Password (default category) | `IsardTest1!` | Satisfies the `default` password policy |
| Password (new category) | 34+ char compliant value | Freshly created categories ship a strict (≥34) password policy |
| Category | `default` (or the manager's own) | Managers cannot switch category |
| Group | `default-default` (or the category's auto-group) | Required by add/edit |

> **Why created users get a VPN.** A user created via
> `POST /api/v4/admin/item/user` comes back with `vpn: null`. The users
> datatable VPN column render reads `full.vpn.wireguard.connected`
> without a null guard, so a single `vpn:null` row throws and the whole
> table fails to render ("No matching records found"). The setup helper
> therefore calls `PUT /api/v4/admin/item/user/reset-vpn/{id}` right
> after creating, so the row carries a real VPN object. This is a
> product bug (the render should null-check `full.vpn`).

> **Why tests filter the users table before acting on a row.** The users
> datatable renders 10 rows per page with `deferRender` and exposes **no
> "show all" length option**, so a freshly created user's row may sit on a
> later page and never enter the DOM. Any scenario that opens a *specific*
> user's detail panel first filters the table by that user's **username**
> (the table's Username column search — the same column the app's
> `?searchUser=` deep-link drives) so the target row is guaranteed to render
> on the first page regardless of how many other users exist. The
> **bulk-selection** scenarios (A7 bulk delete, A8 bulk edit) do the same with
> a username token shared by the target users: bulk selection reads only the
> *rendered* rows (`getSelectedUserList` checks the `active` class on
> DataTables' drawn nodes), so an un-rendered row can never be selected.

Created IDs (users / categories / groups / secrets) are kept in test
state so cleanup can remove them in reverse dependency order even if
assertions fail.

## Capability matrix

| Action | Admin | Manager | Notes |
| --- | --- | --- | --- |
| Users CRUD | Yes | Own category only | Manager category select offers only the manager's category |
| Reset password | Yes | Own category | Reset password PUT bug fixed (was 405) |
| Enable/disable | Yes | Own category | PUT currently 405 for everyone (known bug) |
| Reset VPN | Yes | Denied on admin targets (4xx) | — |
| Impersonate / logout | Yes | Impersonate-admin denied (manager) | — |
| Bulk edit/delete | Yes | Bulk-delete of an admin target rejected | — |
| Categories | Full CRUD | Read-only, own category only | Create/Delete admin-only (`.btn-edit-category`/`.btn-delete` hidden) |
| Groups | Full CRUD | Own-category listing | Empty/enrollment included |
| External apps (secrets) | Yes | Hidden | Whole panel gated server-side (`role != 'manager'`) |
| Roles | Read-only table | Read-only, no expand control | Edit-role modal is admin-only; column 0 hidden for managers |

---

# Admin scenarios

## Scenario A1 — *admin adds a user and it appears in the table*

### Given

1. The admin is on the Management screen with the users table loaded.

### When

1. They click **Add new** and fill the full form (username, name, valid
   email, password + confirmation), then **Send**.

### Then

1. `POST /api/v4/admin/item/user` responds with status `< 400`.
2. A "Created" PNotify is shown and the new row appears in `#users`.

## Scenario A2 — *admin add-user form rejects invalid email and password*

### Given

1. The add-user modal is open.

### When

1. They enter a malformed email and a policy-invalid password and press
   **Send**.

### Then

1. Parsley blocks submission; `#modalAddUser` stays open.
2. No `POST /api/v4/admin/item/user` request is made.

## Scenario A3 — *admin sees the users table loaded and searchable*

### Given

1. The admin navigates to the Management screen.

### When

1. The page loads.

### Then

1. `GET /api/v4/admin/items/users/management/users` responds `< 400`.
2. `#users` renders at least one row.

## Scenario A4 — *admin edits a user's editable fields*

### Given

1. An editable non-admin user exists.

### When

1. They open the user details, click **Edit**, wait for the modal to
   populate (`GET /api/v4/admin/item/user/{id}`), change the **name**,
   and **Send**.

### Then

1. `PUT /api/v4/admin/item/user/{id}` responds `< 400`.
2. The new name is persisted (verified via
   `GET /api/v4/admin/items/users/management/users`, the cache the edit
   PUT invalidates).

## Scenario A5 — *admin deletes a user with the "delete user and items" path*

### Given

1. A user exists.

### When

1. Details → **Delete** opens `#modalDeleteUser`; the preview is
   populated by `POST /api/v4/admin/item/user/delete/check`.
2. They pick **Delete user and items** and **Send**.

### Then

1. `DELETE /api/v4/admin/items/users` responds `< 400`.
2. The user no longer appears in
   `GET /api/v4/admin/items/users/management/users`.

> The "keep user, delete items" path keeps the user, so it cannot share
> this removal assertion.

## Scenario A6 — *admin reset password*

### Given

1. A local user exists.

### When

1. Details → **Reset passwd**, enter a valid password twice, **Send**.

### Then

1. `PUT /api/v4/admin/item/user/{id}` responds `< 400` (bug fixed — was 405).

## Scenario A7 — *admin bulk-deletes selected users*

### Given

1. Two editable users exist.

### When

1. They mark both rows (the `active` row class drives
   `getSelectedUserList`), click the general **Delete**, pick **delete
   user and items**, and **Send**.

### Then

1. `DELETE /api/v4/admin/items/users` responds `< 400`.

## Scenario A8 — *admin bulk-edits the active toggle*

### Given

1. Two editable users are selected.

### When

1. They open **Bulk edit**, enable the **active/inactive** toggle
   (iCheck), and **Send**.

### Then

1. `PUT /api/v4/admin/items/users/bulk` responds `< 400`.

> **Known bugs to layer in later**: linked secondary groups are not
> persisted; the `email verified` checkbox may not persist.

## Scenario A9 — *admin enable/disable*

### Given

1. A normal non-admin user exists.

### When

1. Details → **Enable/Disable**, confirm the PNotify.

### Then

1. `PUT /api/v4/admin/item/user/{id}` responds `< 400`.

## Scenario A10 — *admin resets a user's VPN*

### Given

1. A user with an existing `user.vpn` payload exists.

### When

1. Details → **Reset VPN**, confirm the PNotify dialog.

### Then

1. `PUT /api/v4/admin/item/user/reset-vpn/{id}` responds `< 400`; a
   "Success" PNotify shows.
2. The `vpn.wireguard.public_key` differs from the pre-reset snapshot.

## Scenario A11 — *admin creates a category*

### Given

1. The admin is on the Management screen.

### When

1. Categories panel → **Add new**, fill the form, **Send**.

### Then

1. `POST /api/v4/admin/item/category` responds `< 400`.
2. The category appears in
   `GET /api/v4/admin/items/users/management/categories`.

> **Known bug**: the `maintenance` field is sent but not persisted.

## Scenario A12 — *admin sees the categories table loaded*

### Given

1. The categories endpoint is reachable.

### When

1. The categories panel renders.

### Then

1. `GET /api/v4/admin/items/users/management/categories` responds `< 400`.
2. `#categories` renders at least one row.

## Scenario A13 — *admin edits a category's editable fields*

### Given

1. A throwaway category is created via API (not `default`, which is
   protected and returns `409` on edit).

### When

1. Details → **Edit** (`.btn-edit-category`), change name + description,
   **Send**.

### Then

1. `PUT /api/v4/admin/item/category/{id}` responds `< 400`.

> **Known bug**: the `maintenance` field is sent but not persisted.

## Scenario A14 — *admin deletes a category and its descendant users (DB cascade)*

### Given

1. A throwaway category with a child user (placed in its auto-group,
   created with a ≥34-char password) is created via API.

### When

1. Details → **Delete**; the preview is populated by
   `POST /api/v4/admin/item/category/delete/check`; confirm with **Send**.

### Then

1. `DELETE /api/v4/admin/item/category/{id}` responds `< 400`.
2. The category disappears from the categories listing **and** its child
   user disappears from `GET /api/v4/admin/items/users` (cascade).

## Scenario A15 — *admin creates a group*

### Given

1. A parent category exists.

### When

1. Groups panel → **Add new**, fill the name, **Send**.

### Then

1. `POST /api/v4/admin/item/group` responds `< 400`.
2. The group appears in
   `GET /api/v4/admin/items/users/management/groups`.

## Scenario A16 — *admin sees the groups table loaded*

### Given

1. The admin is on the Management screen.

### When

1. The groups panel renders.

### Then

1. `GET /api/v4/admin/items/users/management/groups` responds `< 400`.
2. `#groups` renders at least one row.

## Scenario A17 — *admin edits a group's editable fields*

### Given

1. A group exists.

### When

1. Details → **Edit** (`.btn-edit-group`), modify the description, **Send**.

### Then

1. `PUT /api/v4/admin/item/group/{id}` responds `< 400`.

## Scenario A18 — *admin deletes a group and its descendant users (DB cascade)*

### Given

1. A throwaway group in `default` with a child user is created via API.

### When

1. Details → **Delete**; preview via
   `POST /api/v4/admin/item/group/delete/check`; confirm with **Send**.

### Then

1. `DELETE /api/v4/admin/item/group/{id}` responds `< 400`.
2. The group disappears from the groups listing **and** its child user
   disappears from `GET /api/v4/admin/items/users` (cascade).

## Scenario A19 — *admin empties a group* — **expected failure (DELETE 400)**

### Given

1. A throwaway group in `default` with a child user exists.

### When

1. Details → **Empty**, tick the confirmation checkbox, **Send**.

### Then

1. The Empty flow sends the group's user ids to
   `DELETE /api/v4/admin/items/users` (delete_user:true) and responds `< 400`.

## Scenario A20 — *admin opens the group enrollment modal*

### Given

1. A group exists.

### When

1. Details → **Enrollment** opens `#modalEnrollment`.
2. Each role checkbox (`#user-check`, `#manager-check`, `#advanced-check`)
   is enabled via the iCheck API.

### Then

1. For every enabled checkbox, its code field (`#user-key`, `#manager-key`,
   `#advanced-key`) becomes visible with a 6-character alphanumeric code.
2. Closing and reopening the modal shows the same codes (persisted in the DB).

## Scenario A21 — *admin sees the secrets table load with HTTP 200*

### Given

1. The admin is on the Management screen.

### When

1. The External apps panel renders.

### Then

1. `GET /api/v4/admin/items/secrets` responds `< 400`.

## Scenario A22 — *admin adds an external app*

### Given

1. The admin is on the Management screen.

### When

1. External apps → **Add new**, fill name/domain/category, **Send**.

### Then

1. `POST /api/v4/admin/item/secret` responds `< 400`.

## Scenario A23 — *admin edits a role*

### Given

1. The admin is on the Management screen; the roles table is visible.

### When

1. Roles row details → **Edit** (`.btn-edit-role`).

### Then

1. `#modalEditRole` renders the name and description fields.

## Scenario A24 — *admin sees the Export CSV control*

### Given

1. The users table is loaded.

### When

1. The users action bar renders.

### Then

1. The CSV export button is visible.

## Scenario A25 — *admin runs the CSV update flow* — **expected failure (empty password corrupts the password)**

### Given

1. A throwaway user (`e2e_a25_<timestamp>`) is created via API with a known
   password (the CSV must never reference the real `admin` account — a CSV
   update can overwrite fields and corrupt authentication).

### When

1. **Update from CSV**, upload a CSV referencing the throwaway user that
   changes the `name` but leaves the `password` column **empty**, **Send**.

### Then

1. `PUT /api/v4/admin/items/users/csv` responds `< 400`.
2. The change applied: the user's `name` now matches the CSV value.
3. **Empty password is a no-op:** the user can still log in with the original
   password (verified end-to-end). The update CSV uses the columns the modal
   documents — `active / name / provider / category / uid / group /
   secondary_groups / password` — and "Leave the parameters you don't want to
   update blank", so a blank password column skips it.

## Scenario A26 — *admin runs the CSV bulk-create flow*

Companion to A25 (CSV *update*): this is the CSV *create* flow.

### Given

1. The bulk-create modal (`#modalAddBulkUsers`) is open.

### When

1. A CSV is uploaded with the bulk-create schema — EXACTLY six columns, in
   order: `username,name,email,group,category,role` (no `password` column;
   `UserFromCSV`). Category/group are matched **by name**, so the seeded
   `Default` category + `Default` group names are used.

### Then

1. `POST /api/v4/admin/items/users/csv/validate` responds `< 400` and the
   preview datatable (`#csv_preview`) lists the parsed rows.
2. **Safety property:** every validated row comes back with a generated,
   **non-blank** `password`. The backend ignores any submitted password and
   always generates a policy-compliant one (`bulk_user_check`, `item_type="csv"`),
   so bulk-created users are **never passwordless**.
3. Submitting the validated rows to `POST /api/v4/admin/items/bulk/user`
   responds `< 400` with `created == 2`, and both users appear in the
   management listing.

> The bulk-add modal's **Send** button stays disabled after a CSV upload (the
> re-enable line in `csv2datatables` is commented out), so the test issues the
> same POST the handler would rather than clicking it.

## Scenario A27 — *admin impersonates a user and lands on /Desktops*

### Given

1. A target user exists. The test runs in an **isolated browser context**
   so the impersonation cookie swap does not corrupt the shared admin
   session.

### When

1. Details → **Impersonate**, confirm.

### Then

1. `GET /api/v4/admin/item/jwt/{id}` responds `< 400`.
2. The page redirects to `/Desktops` as the impersonated user.

## Scenario A28 — *admin logs a user out*

### Given

1. A target user with an active session exists.

### When

1. Details → **Log Out**, confirm.

### Then

1. `PUT /api/v4/admin/item/user/{id}/logout` responds `< 400`.

## Scenario A29 — *admin migrates a user's resources to a target (DB-verified)*

### Given

1. Source and target users in the same category are created via API; a
   persistent desktop owned by the source is seeded (logged in as the
   source). The desktop is created directly via the API and stays in
   "Waiting" (no hypervisor brings it to Stopped in this environment), so
   the test does not wait for it to start — migration reassigns ownership
   regardless of desktop status.

### When

1. The migrate modal is opened (UI fidelity: the resources summary
   renders), then the migration is triggered via
   `PUT /api/v4/admin/item/user/migrate/{source}/{target}` (the same
   endpoint the **Send** button issues; the select2 target picker is
   AJAX-flaky).

### Then

1. The migration PUT responds `< 400`.
2. The seeded desktop is reassigned to the target user (polled via the
   admin `domains` table — `domains.user == target`).

> The migration BackgroundTask also stops running desktops, deletes
> non-persistent desktops and bookings, clears deployment co-owners, and
> enqueues recycle-bin deletion (`helpers.py` change_owner_desktops /
> change_owner_deployments). Those rules live in the same code path;
> seeding a persistent desktop is what is feasible end-to-end via the
> public API without virt-start. **TODO**: extend coverage for the other
> rules.

## Scenario A30 — *admin opens user logs*

### Given

1. A user row exists.

### When

1. Details → **Logs**.

### Then

1. The logs DataTable POSTs to `/api/v4/admin/items/logs_users` (the endpoint
   moved under `/items/`) and responds `< 400`.

## Scenario A31 — *admin opens the category Authentication modal*

### Given

1. A category row is available.

### When

1. Category details → **Authentication** (`.btn-authentication`).

### Then

1. `#modalAuthentication` is visible.

## Scenario A32 — *admin opens the category Branding modal*

### Given

1. A category row is available.

### When

1. Category details → **Branding** (`.btn-branding`).

### Then

1. `div#modal-branding` is visible (the modal id is hyphenated and
   duplicated on a child `<h4>`, so scope to the `<div>`).

## Scenario A33 — *admin opens the category Login Notification modal*

### Given

1. A category row is available.

### When

1. Category details → **Login Notification** (`.btn-login_notification`
   — note the underscore).

### Then

1. The login-notification modal is visible.

## Scenario A34 — *admin opens the category Bastion domain modal (when Bastion is enabled)*

### Given

1. A category row is available; Bastion may or may not be enabled
   installation-wide.

### When

1. Category details → **Bastion domain** (`.btn-bastion-domain`).

### Then

1. If `GET /api/v4/bastion` responds `< 400`, the modal is usable.
2. If it returns `403/404` (or the request fails), Bastion is disabled —
   the scenario is skipped with a clear reason.

> **Implementation note**: the categories tab is clicked and its first row
> is awaited before `expandFirstRow` is called. Without this, the tab
> panel is hidden (`display:none`) under parallel load and the 15 s
> `waitFor` in `expandFirstRow` times out before the test can reach the
> skip logic. The button triggers `GET /api/v4/admin/item/config/bastion`
> first; the response URL and status determine whether to pass or skip.

## Scenario A35 — *user `email_verified` is persisted on create*

### Given

1. A user is created via `POST /api/v4/admin/item/user` with
   `email_verified: true`.

### When

1. The created user is read back from the users listing.

### Then

1. `email_verified` comes back `true`.

## Scenario A36 — *category `maintenance` is persisted (via update)*

### Given

1. A category is created, then updated via
   `PUT /api/v4/admin/item/category/{id}` with `maintenance: true`
   (`maintenance` is dropped by create but persisted by update).

### When

1. The category is read back via `GET /api/v4/admin/item/category/{id}`.

### Then

1. `maintenance` comes back `true`.

## Scenario A37 — *group `linked_groups` are saved (via update)*

### Given

1. A throwaway "linked" group exists; a new group is created, then updated
   via `PUT /api/v4/admin/item/group/{id}` with `linked_groups: [linked.id]`
   (`linked_groups` is in the update body, not create).

### When

1. The new group is read back via `GET /api/v4/admin/item/group/{id}`.

### Then

1. `linked_groups` includes the linked group's id.

## Scenario A38 — *users table renders correctly with a `vpn:null` row* (bug fixed)

### Given

1. A user is created with `resetVpn:false`, so it keeps the `vpn:null`
   that `POST /api/v4/admin/item/user` returns.

### When

1. The Management screen loads with that user in the table.

### Then

1. `#users tbody` renders real rows and does **not** show
   "No matching records found" — the VPN column null-guard is working.
   (Fixed in `users_management.js`: `"data": null` + explicit null-check
   in the render function, replacing `"data": "vpn.wireguard.connected"`.)

## Scenario A39 — *no management table cell renders the literal string "undefined"* — **expected failure (categories authentication column bug)**

### Given

1. The admin is on the Management screen; all four datatables (`#users`,
   `#categories`, `#groups`, `#roles`) have rendered at least one row.

### When

1. The page loads and each tab (Users, Categories, Groups) is activated so
   DataTables fetches and renders its data.

### Then

1. No `<td>` cell in `#users tbody`, `#categories tbody`, `#groups tbody`,
   or `#roles tbody` contains the literal text `"undefined"` — a symptom
   of a missing null-guard or unresolved JS property in a DataTables
   render function.

> **Known bug**: the `#categories` authentication column render function
> (`categories_management.js`, `columnDefs` target 5) falls through
> without returning when `full.authentication` is falsy. DataTables then
> renders the cell as the literal string `"undefined"`. Fix: add
> `return ""` at the end of that render function. Marked `test.fail`
> (bug #17).

## Scenario A40 — *admin edits a category's manager permissions and they persist*

Covers the four per-category manager-permission toggles —
**Authentication**, **Branding**, **Login Notification**, and **GPU
Plannings** — saved through the category Edit modal. This is the **only**
coverage of GPU Plannings: persistence is asserted via the API read-back; it
has no manager-facing button, so it is not verified from the manager side
(the gating loop in `categories_management.js` covers only the other three —
see A39/M11/M16).

### Given

1. A throwaway category is created via API (`createTestCategory`); its
   `manager_permissions` default to all-`false` on create.

### When

1. Categories panel → expand the category → **Edit** (`.btn-edit-category`).
2. In the **Manager Permissions** panel, toggle the four iCheck checkboxes to a
   known mix — enable **Authentication**
   (`#category-permissions-edit-authentication`), **Login Notification**
   (`#category-permissions-edit-login_notification`) and **GPU Plannings**
   (`#category-permissions-edit-plannings`); leave **Branding**
   (`#category-permissions-edit-branding`) off — then **Send**.

### Then

1. `PUT /api/v4/admin/item/category/{id}` responds `< 400`. The edit form
   serialises the panel as
   `manager_permissions: {authentication, branding, login_notification, plannings}`
   and PUTs it to the same apiv4 endpoint.
2. `GET /api/v4/admin/item/category/{id}` returns `manager_permissions` exactly
   as set: `authentication: true`, `branding: false`,
   `login_notification: true`, `plannings: true`.

> The four keys are `authentication`, `branding`, `login_notification`, and
> `plannings` (GPU Plannings → `plannings`). They are accepted and persisted by
> `POST`/`PUT /api/v4/admin/item/category` (`ManagerPermissionsData`) and
> returned by `GET` — correcting the earlier assumption that the API ignored
> them.

---

# Manager scenarios

> Managers log in as `manager_e2e_01` (role `manager`, `default`
> category) via `loginHelpers.login` + `bridgeAdminSession`. The **entire**
> Users Management suite runs **sequentially in a single worker**
> (`test.describe.configure({ mode: "default" })` at file scope, which overrides
> the project's `fullyParallel: true`). This is required because every test
> shares global state — the per-worker admin account, the seeded `default`
> category and users table, and the single seeded manager account — so running
> them in parallel makes them flaky (concurrent `manager_e2e_01` logins contend
> on the same Redis session and drop the JWT cookie; concurrent table mutations
> race). `default` mode keeps tests independent (each retries on its own, no
> serial cascade-skip).

## Scenario M2 — *manager can add users only in their own category*

### Given

1. The add-user modal is open as a manager.

### When

1. They inspect the category select.

### Then

1. The category select offers only the manager's own category (≤ 2
   options including any placeholder).

## Scenario M3 — *manager cannot edit an admin user* — **expected failure (GET 500)**

### Given

1. An admin row is visible to the manager.

### When

1. Details → **Edit**.

### Then

1. **Known bug**: `GET /api/v4/admin/item/user/{id}` returns `500`.
   Marked `test.fail`.

## Scenario M4 — *manager cannot reset an admin's password* — **expected failure (GET 500)**

### Given

1. An admin row is visible.

### When

1. Details → **Reset passwd**.

### Then

1. **Known bug**: `GET /api/v4/admin/item/user/password-policy/{id}`
   returns `500`. Marked `test.fail`.

## Scenario M5 — *manager cannot impersonate an admin* — **expected failure (GET 500)**

### Given

1. An admin row is visible.

### When

1. Details → **Impersonate**, confirm.

### Then

1. **Known bug**: `GET /api/v4/admin/item/jwt/{id}` returns `500`.
   Marked `test.fail`.

## Scenario M6 — *manager cannot delete an admin user* — **expected failure (POST 500)**

### Given

1. An admin row is visible.

### When

1. Details → **Delete**.

### Then

1. **Known bug**: `POST /api/v4/admin/item/user/delete/check` returns
   `500`. Marked `test.fail`.

## Scenario M7 — *manager cannot reset VPN of an admin user*

### Given

1. A throwaway admin target (same `default` category) is created via the
   worker's admin context.

### When

1. The manager calls `PUT /api/v4/admin/item/user/reset-vpn/{id}` for
   that admin.

### Then

1. The request is denied (status `>= 400`).

## Scenario M8 — *manager cannot bulk-delete an admin target*

### Given

1. A throwaway admin target exists.

### When

1. The manager calls
   `DELETE /api/v4/admin/items/users` with that admin id.

### Then

1. The request is rejected (status `>= 400`).

## Scenario M9 — *manager cannot disable an admin, self, or the default admin*

### Given

1. The default admin (`local-default-admin-admin`) and a throwaway admin
   target are available.

### When

1. The manager attempts `PUT /api/v4/admin/item/user/{id}` with
   `active:false` for those targets.

### Then

1. No disable succeeds (status `>= 400`); the default admin stays active.

> Enable/disable is currently 405-broken for everyone (see A9), so this
> also guards against a regression once that is fixed.

## Scenario M10 — *manager sees only own category in Categories and Groups*

### Given

1. The manager is on the Management screen.

### When

1. The categories and groups panels load.

### Then

1. `GET .../management/categories` and `GET .../management/groups` both
   respond `< 400`.

## Scenario M11 — *manager category actions follow `manager_permissions`*

### Given

1. The manager is on the Management screen. The `default` category's
   `manager_permissions` is **not assumed** to be `null` — this deployment may
   grant some permissions, and the e2e environment does not guarantee a value.

### When

1. The manager expands their own category. The test reads the category's actual
   `manager_permissions` from the categories listing the page already loaded
   (the same data the gating in `renderCategoriesDetailPannel` consumes).

### Then

1. For each gated action (`.btn-authentication`, `.btn-branding`,
   `.btn-login_notification`), the button is **visible if and only if** its
   `manager_permissions[<key>]` is truthy, and **hidden** otherwise. This
   verifies both the deny and grant paths against whatever the category
   actually grants.

> **Note**: M11 is the *passive* check — it asserts visible-iff-granted against
> the category's **current** `manager_permissions` without changing them. The
> *active* grant/deny path (admin sets a permission → the manager's button
> appears/disappears) is covered by **M16**, and persistence of all four keys
> (including GPU Plannings) by **A40**. (`manager_permissions` **is** settable
> via `POST`/`PUT /api/v4/admin/item/category` — `ManagerPermissionsData`.)

## Scenario M12 — *manager can use Bastion domain*

### Given

1. A category row is visible to the manager.

### When

1. Category details → **Bastion domain**.

### Then

1. A modal appears containing the text **"Bastion Domain"**.

## Scenario M13 — *manager cannot edit roles (no expand control, no edit action)*

### Given

1. The manager is on the Management screen.

### When

1. The roles table renders.

### Then

1. `#roles` has rows, but the details-control column is hidden
   (`roles.js`: `column(0).visible(false)` for non-admins), so the
   expand button is not visible and `.btn-edit-role` is absent.

## Scenario M14 — *manager cannot see the External apps panel*

### Given

1. The manager is on the Management screen.

### When

1. The page renders.

### Then

1. The External apps panel is not present (gated server-side by
   `role != 'manager'`).

## Scenario M15 — *manager logs action* — **expected failure (POST 500)**

### Given

1. A user row is visible to the manager.

### When

1. Details → **Logs**.

### Then

1. **Known bug**: for a manager, `POST /api/v4/admin/items/logs_users` returns
   `500` (admin logs work — see A30). The test asserts the desired `< 400` and
   is wrapped in `test.fail`, so it is an expected failure until the manager
   logs path is fixed.

## Scenario M16 — *manager sees category action buttons only for enabled permissions*

The active grant/deny counterpart to M11 (which only asserts visible-iff-granted
against whatever the category currently grants). Here an admin **sets**
`default`'s `manager_permissions` and the manager's detail-panel buttons change
accordingly, for the three button-backed permissions. Lives in the M11 "manager
category permission gating" describe block (shares the manager-login setup; the
suite runs sequentially, so the mutate+restore is safe).

### Given

1. The seeded manager `manager_e2e_01` belongs to the `default` category. The
   test first records `default`'s current `name` and `manager_permissions` (via
   `GET /api/v4/admin/item/category/default`) so it can restore them afterward.

### When

1. As admin, `PUT /api/v4/admin/item/category/default` with the **same `name`**
   (so no `409`) and `manager_permissions` enabling `authentication` +
   `login_notification` and disabling `branding`.
2. The manager logs in (`loginHelpers.login(manager_e2e_01)` +
   `bridgeAdminSession`), opens the Management screen, and expands their own
   (`default`) category.

### Then

1. `.btn-authentication` and `.btn-login_notification` are **visible**;
   `.btn-branding` is **hidden** — each button shown if and only if its
   `manager_permissions[<key>]` is truthy.
2. A second pass with the inverse configuration (enable `branding`, disable the
   other two) flips the visibility accordingly, exercising both the grant and
   the deny path.

### Cleanup

1. `default`'s original `manager_permissions` is restored via
   `PUT /api/v4/admin/item/category/default` in `afterEach`/`finally`, leaving
   the shared category and `manager_e2e_01` untouched for other tests.

> **GPU Plannings** (`plannings`) is intentionally not asserted here — the
> category detail panel has no plannings button (the manager gating loop covers
> only `authentication`/`branding`/`login_notification`). Its persistence is
> covered by A40.

---

## Known bugs (expected-failure policy)

The 15 bugs below currently reproduce. Each is covered by a scenario —
mostly `test.fail` (with a TODO to remove the marker once fixed); `#10`
is a critical positive guard, and `#15` is additionally worked around in
setup so the rest of the suite can run.

1. Manager edit-user modal — `GET /api/v4/admin/item/user/{id}` → `500` (M3).
2. Manager password-policy — `GET .../item/user/password-policy/{id}` → `500` (M4).
3. Manager impersonation — `GET /api/v4/admin/item/jwt/{id}` → `500` (M5).
4. Enable/disable — `PUT .../item/user/{id}` → `405` (A9). *(Reset password bug fixed — A6 now passes normally.)*
5. Manager logs — `POST /api/v4/admin/items/logs_users` → `500` for a manager
   (M15, marked `test.fail`). Admin logs work at the same `/items/` path (A30 passes).
6. Manager delete-user preview — `POST .../item/user/delete/check` → `500` (M6).
7. Manager Bastion — modal opens with "Bastion Domain" title (M12).
8. Edit-role modal shows corrupted migration/merge content (A23).
9. **Linked groups not saved** — `POST/PUT /api/v4/admin/item/group`
   silently drops `linked_groups` (the model omits it) (A37).
10. **CSV bulk create** must never persist an empty password (critical
    safety guard) (A26).
11. **Category `maintenance` not persisted** — the value is sent but the
    admin category model drops it (A36).
12. **`email_verified` not persisted** — the create accepts the field but
    it (and the form checkbox) is not saved (A35).
13. **Empty group** sends user objects instead of id strings →
    `DELETE /api/v4/admin/items/users` `400 validation_error` (A19).
14. **Add external app** POSTs `{id,domain,category_id}` but the API
    requires `secret` → `POST /api/v4/admin/item/secret` `400` (A22).
15. ~~**Users datatable VPN render** throws on `vpn:null` rows, blanking
    the whole table (A38)~~ — **fixed** (`"data": null` + null-guard in
    render function). Setup still resets VPN on each created user so the
    VPN icon shows the correct state, but the crash no longer occurs.
16. **Group enrollment UI** — `manager` and `advanced` codes are generated
    in the DB (POST succeeds) but `#manager-key` / `#advanced-key` remain
    empty in the UI (A20). Marked `test.fail`.
17. **Categories authentication column renders `"undefined"`** —
    `categories_management.js` `columnDefs` target 5 (authentication
    column) render function falls through without a `return` when
    `full.authentication` is falsy; DataTables renders those cells as the
    literal string `"undefined"`. Fix: add `return ""` at the end of that
    render function (A39). Marked `test.fail`.

Bugs no longer reproducing on this branch (now normal passing tests):
group enrollment `[object Object]` rendering (old A20 bug), CSV update
`404` (A25), reset password `405` (A6), users table `vpn:null` crash
(A38).

## Cleanup (afterEach)

1. Created users/categories/groups/secrets are deleted via API in reverse
   dependency order (users → groups → categories).
2. Disposable admin/category fixtures (M7–M9) are removed in `afterAll`.
   M16 mutates the `default` category's `manager_permissions` and restores the
   original value in `afterEach`/`finally`; M11 reads but does not mutate them.
3. Cleanup errors are silenced so they do not mask the primary assertion.

## Expected results — global summary

| Area | Admin | Manager | Notes |
| --- | --- | --- | --- |
| Users CRUD | ✅ | ✅ own-category | Manager admin-target ops have known 500s |
| Lifecycle (passwd, active, vpn, impersonate, logout, migrate, logs) | ⚠️ | ⚠️ | Passwd/active/logs broken by backend bugs |
| Bulk + CSV | ✅ / ⚠️ | — | CSV bulk-create password guard is critical |
| Categories / Groups core | ✅ | ✅ scoped | Manager scoped to own category |
| Category extras (auth/branding/login-notif/bastion) | ✅ | ✅ gated | Manager can open Bastion Domain modal |
| External apps / roles | ⚠️ / ✅ | ❌ | Role-edit modal broken; external apps hidden for manager |

## APIs touched by the flows (reference)

- Users listing: `GET /api/v4/admin/items/users/management/users`
- User CRUD/lifecycle:
  - `POST /api/v4/admin/item/user`
  - `GET|PUT /api/v4/admin/item/user/{id}`
  - `POST /api/v4/admin/item/user/delete/check`
  - `DELETE /api/v4/admin/items/users`
  - `GET /api/v4/admin/item/user/password-policy/{id}`
  - `PUT /api/v4/admin/item/user/reset-vpn/{id}`
  - `GET /api/v4/admin/item/jwt/{id}`
  - `PUT /api/v4/admin/item/user/{id}/logout`
  - `GET /api/v4/admin/item/user/migrate/check/{source}/{target}`
  - `PUT /api/v4/admin/item/user/migrate/{source}/{target}`
  - `POST /api/v4/admin/logs_users`
- Bulk / CSV:
  - `PUT /api/v4/admin/items/users/bulk`
  - `PUT|POST /api/v4/admin/items/users/csv/validate`
  - `PUT /api/v4/admin/items/users/csv`
- Categories / Groups:
  - `GET /api/v4/admin/items/users/management/categories`
  - `POST|GET|PUT /api/v4/admin/item/category/{id}` — accepts/returns
    `manager_permissions {authentication, branding, login_notification, plannings}`
    (`ManagerPermissionsData`; A40 / M16)
  - `POST /api/v4/admin/item/category/delete/check`
  - `DELETE /api/v4/admin/item/category/{id}`
  - `GET /api/v4/admin/items/users/management/groups`
  - `POST|GET|PUT /api/v4/admin/item/group/{id}`
  - `POST /api/v4/admin/item/group/delete/check`
  - `DELETE /api/v4/admin/item/group/{id}`
  - `GET /api/v4/admin/items/group/{id}/users/`
- External apps / roles / bastion:
  - `GET /api/v4/admin/items/secrets`
  - `POST /api/v4/admin/item/secret`
  - `GET|PUT /api/v4/admin/item/role/{id}`
  - `GET /api/v4/bastion`

## Relevant database state

- `users`: `active`, `email_verified`, `role`, `category`, `group`,
  `vpn`, password-hash fields.
- `categories`: `manager_permissions`
  (`{authentication, branding, login_notification, plannings}` — settable on
  create/update, A40/M16), branding / login-notification,
  `maintenance` (not persisted — bug).
- `groups`: linked groups, enrollment codes/settings.
- `domains` (desktops), `deployments` (co-owners), `bookings`,
  recycle-bin entries — impacted by delete/migrate/empty flows.

## Cases not covered (future)

- Full enrollment-code redemption via real IdP login (Google/LDAP/SAML).
- Deterministic assertion of every migration side effect from the UI.
- Complete enrollment-code format assertion (currently verified as non-empty; the 6-char alphanumeric format is not enforced).
