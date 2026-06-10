# User migrations in webapp

Human-readable functional specification of the admin **Migrations** screen:
the read-only migrations DataTable, its expandable per-row **detail** sub-table,
the global/per-column **search**, and the per-row **Revoke** and **Delete**
actions. Serves as the contract for the future E2E test
`tests/webapp/migrations.spec.js`.

## Scope

- **Component**: administration panel (`isard-admin`).
- **Screen**: **Migration** section, under **Users**
  (`/isard-admin/admin/users/migration`).
- **Role**: **admin only** — the route is guarded by `@login_required`
  + `@isAdmin` ([AdminViews.py:367](../../../../webapp/webapp/webapp/views/AdminViews.py#L367)).
- **Actions covered**:
  - List user-migration rows (one per started self-migration), one row per
    possible status.
  - Expand a row's detail to inspect the *Migration items* sub-table
    (Desktops, Templates, Media, Deployments) with migrated counts and per-type
    failure detail.
  - Filter via the global search box and the per-column footer inputs.
  - **Revoke** a migration in status `exported` / `imported` / `migrating`.
  - **Delete** a migration in status `migrated`.
- **Out of scope**:
  - The end-user self-migration flow itself (export / import / migrate-user) —
    that produces the data but is not driven through this screen.
  - The admin **Migrate user** action in *Users management* (a different
    modal). Per product rule, only self-migrations are recorded in this table,
    so we never generate test data through that button.

## Page facts (source of truth)

| Element | Value |
| --- | --- |
| URL | `/isard-admin/admin/users/migration` |
| Table id | `#migration-table` |
| Data source | `GET /api/v4/admin/item/user-migrations` (DataTable AJAX, data prop `migrations`) |
| Row id | `id` field (`rowId`) |
| Default sort | column 4 (**Status**), descending |
| Detail trigger | click on `td.details-control` (first column `+` button) |
| Detail template | `.template-migration-detail` (cloned per expand) |

Reference: [migration.js](../../../../webapp/webapp/webapp/static/admin/js/migration.js),
[migration.html](../../../../webapp/webapp/webapp/templates/admin/pages/migration.html).

### Columns

| # | Header | Field | Render |
| --- | --- | --- | --- |
| 0 | (expand) | — | `+` button, `details-control` |
| 1 | Origin User | `origin_username` | raw |
| 2 | Target User | `target_username` | `data ? data : "-"` |
| 3 | Category | `category` | `data ? data : "-"` |
| 4 | Status | `status` | raw (default sort) |
| 5 | Created time | `created` | `moment.fromNow()` or `"-"` |
| 6 | Import time | `import_time` | `moment.fromNow()` or `"-"` |
| 7 | Migration start time | `migration_start_time` | `moment.fromNow()` or `"-"` |
| 8 | Migration end time | `migration_end_time` | `moment.fromNow()` or `"-"` |
| 9 | Action | — | Revoke / Delete / empty (status-dependent) |

`origin_username`, `target_username` and `category` are **enriched at read
time** by joining the `users` / `categories` tables. They fall back to the
literal string `"[DELETED]"` (never `undefined`) when the referenced
user/category is missing or not yet set
([user_migrations.py `get_migrations`](../../../../component/_common/src/isardvdi_common/lib/users/users/user_migrations.py)).

### Timestamp presence by status

Each timestamp is written at a specific lifecycle step (`import_time` on import,
`migration_start_time` on entering `migrating`, `migration_end_time` on reaching
`migrated`/`failed`), so a column is populated or empty deterministically per
status. Empty timestamps render `"-"` (never `undefined`). The lifecycle is
`exported → imported → migrating → migrated | failed`; `revoked` branches off
`exported`/`imported`/`migrating`.

| Status | Created | Import time | Migration start | Migration end |
| --- | :---: | :---: | :---: | :---: |
| `exported` | ✅ | — | — | — |
| `imported` | ✅ | ✅ | — | — |
| `migrating` | ✅ | ✅ | ✅ | — |
| `migrated` | ✅ | ✅ | ✅ | ✅ |
| `failed` | ✅ | ✅ | ✅ | ✅ |
| `revoked` | ✅ | depends¹ | depends¹ | — |

¹ `revoked` keeps whatever timestamps the migration had when it was revoked:
from `exported` → only `created`; from `imported` → `+ import_time`; from
`migrating` → `+ migration_start_time`. It never has `migration_end_time`
(revoke does not close the migration). **The seed `e2e-mig-ro-revoked` row is
revoked-from-`exported`, so it carries only `created`** (Target renders `"-"`).

### Action column (status → button)

| Status | Button rendered | Selector |
| --- | --- | --- |
| `exported`, `imported`, `migrating` | **Revoke** (red) | `.btn-revoke` |
| `migrated` | **Delete** (red trash) | `.btn-delete` |
| `failed`, `revoked` | *(empty cell)* | — |

### Backend action endpoints

| Action | Call | Guard | Success |
| --- | --- | --- | --- |
| Revoke | `PUT /api/v4/admin/item/user-migration/{id}/revoke` | only `exported`/`imported`/`migrating` (else 400) | `204` |
| Delete | `DELETE /api/v4/admin/item/user-migration/{id}` | any status | `204` |

---

## Common role and prerequisites

| Element | Expected value |
| --- | --- |
| Role | Administrator (`admin_e2e_<worker>`), bridged `isard-admin` session — same `authenticatedPage` fixture used by `gpus.spec.js` |
| Session | Logged in to the webapp **and** the `isard-admin` Flask session bridged |
| Data | `users_migrations` table seeded (see *Preconditions / fixture*) |
| Table state | `#migration-table` loaded and visible |

## Preconditions / fixture

There is **no API to create a migration row** — rows only appear via the real
self-migration flow. Test data is therefore provided as a **static seed**,
`testing/db/data/users_migrations.json`, auto-loaded by
[populate_test_db.py](../../../../testing/db/populate_test_db.py) (it inserts
every `data/*.json` by table name with `conflict="update"`, so each full reseed
restores the canonical state).

The seed was **authentically generated once** (this has already been done): the
real export → import → migrate flow was run a single time against a dev stack and
the resulting genuine `users_migrations` rows were frozen into the JSON. Statuses
the real flow cannot easily snapshot are derived by minimal edits of a captured
row:

- `migrating` — captured `imported` row + `status:"migrating"` + `migration_start_time` + the `migrated_items` snapshot (no per-type flags yet, matching the real mid-migration moment).
- `failed` — captured `migrated` row with one type set to `migrated_<type>:false` + a realistic `migrated_<type>_error`, `status:"failed"`.
- `revoked` — captured `exported` row + `status:"revoked"`.

**One-time authentic-generation procedure that was used** (authoring only, not
part of CI — recorded for reproducibility; `tmp/insert_fixture.py` +
`tmp/build_seed.py`):

1. `auth.local.migration` in RethinkDB `config` id:1 was already
   `export:true, import:true, action_after_migrate:"none"` — no change needed.
2. Two dedicated **manager** users (`e2e-mig-origin`, `e2e-mig-target`, category
   `default`) were created, and the origin was given one desktop, template,
   media and deployment via direct DB insert. **Manager** role is required
   because `change_owner_templates/medias/deployments` reject a role-`user`
   target, so a full all-four-types migration needs a non-`user` owner.
   `migrate-user` only reassigns ownership in DB (no disk operations), so the
   inserted resources need no real storage.
3. As origin: `PUT /api/v4/item/user-migration/export-user` → token. As target:
   `PUT /api/v4/item/user-migration/import-user {token}`, then
   `POST /api/v4/item/user-migration/migrate-user`. The same row was read after
   each step to capture genuine `exported` / `imported` / `migrated` snapshots.

**Referenced users**: the two dedicated local **manager** users (`e2e-mig-origin`
"E2E Migration Origin", `e2e-mig-target` "E2E Migration Target", category
`default`) are added to `testing/db/data/users.json` so
`origin_username` / `target_username` / `category` enrich to stable, searchable
values (`"E2E Migration Origin"`, `"E2E Migration Target"`, `"Default"`).
`migrated_items` holds opaque ID strings — the detail panel only counts list
length and the enrichment only joins `users`/`categories`, so the referenced
desktops/media need not exist (the scaffolding resources were deleted after
generation).

### Read-only rows (shared, never mutated)

The frozen seed `testing/db/data/users_migrations.json` holds **six** canonical
rows, one per status, used by A1–A6. Verified end-to-end through
`GET /api/v4/admin/item/user-migrations`:

| Seed id | status | Enriched Target User | Notes |
| --- | --- | --- | --- |
| `e2e-mig-ro-exported` | `exported` | `null` → cell shows `"-"` | no `target_user`; only `created`/`token` set besides status |
| `e2e-mig-ro-imported` | `imported` | `E2E Migration Target` | has `import_time` + `target_user` |
| `e2e-mig-ro-migrating` | `migrating` | `E2E Migration Target` | `migration_start_time` set; `migrated_items` present, per-type flags absent |
| `e2e-mig-ro-migrated` | `migrated` | `E2E Migration Target` | all 4 `migrated_<type> = true`, full `migrated_items` (1 each) |
| `e2e-mig-ro-failed` | `failed` | `E2E Migration Target` | `migrated_media = false` + `migrated_media_error`, others `true` |
| `e2e-mig-ro-revoked` | `revoked` | `null` → cell shows `"-"` | empty action cell |

### Mutating rows (seeded, one distinct row per test)

A7/A8 consume their row (Delete removes it, Revoke flips its status). Each test
owns its **own** seeded row (no sharing, so each Playwright test — which runs
once — never collides with another), all carried in the same committed seed:

| Seed id | status | Used by |
| --- | --- | --- |
| `e2e-mig-del-ok` | `migrated` | A7 — Delete confirm |
| `e2e-mig-del-cancel` | `migrated` | A7 — Delete cancel |
| `e2e-mig-rev-ok` | `exported` | A8 — Revoke confirm |
| `e2e-mig-rev-cancel` | `exported` | A8 — Revoke cancel |

These rows are created by `populate` like everything else (no runtime DB writes,
no helper). Cleanup is the **SDK** admin delete endpoint
(`deleteMigration`) in `afterEach`, like the rest of the suite; `populate`
restores the canonical rows on the next reseed.

Because a consumed row can only return via a reseed, an attempt that finds its
action button already gone — a retry after a mid-test failure, or a re-run
without reseed — calls `test.skip()` instead of failing: we assume the action
already happened and flag it for manual review rather than reporting a false
bug. (Verified: a fresh-seed run is `12 passed`; an immediate re-run without
reseed is `8 passed, 4 skipped`.)

---

## Scenario A1 — *admin opens Migration and sees all statuses, no `undefined` cells*

### Given

1. The admin is authenticated (webapp + bridged `isard-admin` session).
2. The `users_migrations` seed is loaded.

### When

1. Navigate to `/isard-admin/admin/users/migration`.
2. Wait for `GET /api/v4/admin/item/user-migrations` (status `< 400`) and the
   `#migration-table` to render rows.

### Then

1. The table shows the seeded read-only rows, one per status
   (`exported`, `imported`, `migrating`, `migrated`, `failed`, `revoked`).
2. **No body cell renders the literal text `undefined`** (columns 1–8). Empty
   dates render `"-"`; enriched columns render a name or `"[DELETED]"`.
3. The **Action** column matches the status:
   - `exported` / `imported` / `migrating` row → a `.btn-revoke` button.
   - `migrated` row → a `.btn-delete` button.
   - `failed` / `revoked` row → empty action cell (no `.btn-revoke`/`.btn-delete`).
4. The `exported` and `revoked` rows' **Target User** cell shows `"-"` (the API
   sends `target_username: null` when there is no `target_user`; see *Notes*).
5. The timestamp columns are populated or show `"-"` per the
   *Timestamp presence by status* table — e.g. `exported` shows `"-"` in Import
   / Migration start / Migration end; `migrated` and `failed` show all four
   dates; `migrating` shows `"-"` only in Migration end.

---

## Scenario A2 — *global search filters the table*

### Given

1. A1 preconditions; table loaded.

### When

1. Type a known unique value (e.g. the seeded `origin_username`
   `e2e-mig-origin`) into the DataTables **global** search box.

### Then

1. The table narrows to only the rows whose any column matches the term.
2. Clearing the box restores all rows.

---

## Scenario A3 — *per-column footer search filters by status*

### Given

1. A1 preconditions; table loaded.

### When

1. In the **Status** column footer input, type an exact status (e.g.
   `migrated`).

### Then

1. Only rows with that status remain visible.
2. Clearing the footer input restores the other rows.
3. Footer inputs are independent per column (each column has its own
   `Search <Column>` placeholder input).

---

> **Detail-panel selectors (read before A4–A6).** The detail panel is cloned
> from `.template-migration-detail`, which renders the **Migration Items**
> sub-table from
> [migration_items_result.html](../../../../webapp/webapp/webapp/templates/snippets/migration_items_result.html).
> Each type has three cells: `<strong id="<type>-migrated">` (count),
> `<strong id="<type>-failed">` (failure indicator holder) and
> `<p id="<type>-detail">` (error text), for `<type>` ∈
> `desktops|templates|media|deployments`.
>
> **Those cell ids are NOT unique**: the empty template lives hidden in the page
> *and* a copy is injected on expand, so a bare `#media-failed` matches ≥2
> elements (Playwright strict-mode violation). **Always scope under the cloned
> table**, whose id *is* unique: the JS replaces `d.id`, so the expanded table
> is `#migration-<rowId>` (e.g. `#migration-e2e-mig-ro-failed`). All assertions
> below use `#migration-<rowId> >> #<type>-…`.
>
> The red circle is injected as
> `<i class="fa fa-circle" aria-hidden="true" style="color:red"></i>` **only**
> when `migrated_<type> === false`; the detail `<p>` is filled with
> `migrated_<type>_error` whenever that key exists
> ([migration.js:151-165](../../../../webapp/webapp/webapp/static/admin/js/migration.js#L151-L165)).

## Scenario A4 — *expand details of a fully successful migration*

### Given

1. The seeded `migrated` row (`e2e-mig-ro-migrated`) is visible, with all four
   `migrated_<type> = true` and a populated `migrated_items` (1 id each).

### When

1. Click the row's `td.details-control` (`+`) button.

### Then

1. The row expands; `#migration-e2e-mig-ro-migrated` (the Migration Items table)
   appears with **four** body rows: Desktops, Templates, Media, Deployments.
2. Each `#<type>-migrated` cell shows a **number** (length of
   `migrated_items.<type>`, here `"1"`) or `"-"` when that list is empty.
3. **No** red circle for any type: for every `<type>`,
   `#migration-…-migrated >> #<type>-failed i.fa-circle` has **count 0**.
4. Each `#<type>-detail` is empty (no error text).
5. Clicking `td.details-control` again collapses the row (the detail row is
   removed).

---

## Scenario A5 — *expand details of a failed migration*

### Given

1. The seeded `failed` row (`e2e-mig-ro-failed`) has `migrated_media = false` +
   a non-empty `migrated_media_error`; the other three types are `true`.

### When

1. Click the row's `td.details-control` (`+`) button.

### Then

Scope every locator under `#migration-e2e-mig-ro-failed`:

1. The Media row shows the **red circle** — this is how we assert it renders:
   - `#media-failed i.fa-circle` has **count 1** (`toHaveCount(1)`), and
   - it computes red: `toHaveCSS('color', 'rgb(255, 0, 0)')` (CSS `color:red`).
   Assert count + colour rather than `toBeVisible()` — the `<i>` is an empty
   icon glyph, so count/colour is the robust check.
2. `#media-detail` shows the error text, i.e.
   `"User E2E Migration Target already has media with name e2e-mig media"`
   (equals `migrated_media_error`).
3. The succeeded types render **no** circle: `#desktops-failed i.fa-circle`,
   `#templates-failed i.fa-circle`, `#deployments-failed i.fa-circle` each have
   **count 0**, and their `#<type>-detail` is empty.

---

## Scenario A6 — *expand details of a non-migrated row*

### Given

1. The seeded `exported` row (`e2e-mig-ro-exported`) has **no** `migrated_items`.

### When

1. Click the row's `td.details-control` (`+`) button.

### Then

Scope under `#migration-e2e-mig-ro-exported`:

1. The sub-table renders without a JavaScript error (the page does not break).
2. All four `#<type>-migrated` cells show `"-"`, every `#<type>-failed i.fa-circle`
   has count 0, and every `#<type>-detail` is empty.

> **Note**: this works because optional chaining short-circuits when
> `migrated_items` is absent. See the *Known issues* note about partial
> `migrated_items` dicts (not exercised here — the seed never produces one).

---

## Scenario A7 — *admin deletes a `migrated` migration*

### Given

1. The seeded `migrated` rows `e2e-mig-del-ok` (confirm) / `e2e-mig-del-cancel`
   (cancel) exist. If a row's **Delete** button is already gone (row consumed by
   a prior attempt/run), the test `test.skip()`s instead of failing.

### When

1. On that row, press the **Delete** button (`.btn-delete`).
2. A PNotify confirm appears: title *"Are you sure you want to delete this
   migration?"*, text *"The user will be able to migrate this user again."*,
   with **Ok** / **Cancel**.
3. Press **Ok**.

### Then

1. `DELETE /api/v4/admin/item/user-migration/<id>` is called and responds `204`.
2. A success PNotify *"Migration deleted"* appears.
3. The table reloads (`ajax.reload()`) and the row is gone.
4. Verify via the list endpoint that the id is no longer present.

### Cancel branch

1. Pressing **Cancel** on the confirm fires **no** DELETE request and the row
   stays in the table.

---

## Scenario A8 — *admin revokes an `exported` migration*

### Given

1. The seeded `exported` rows `e2e-mig-rev-ok` (confirm) / `e2e-mig-rev-cancel`
   (cancel) exist. If a row's **Revoke** button is already gone (row consumed by
   a prior attempt/run), the test `test.skip()`s instead of failing.

### When

1. On that row, press the **Revoke** button (`.btn-revoke`).
2. A PNotify confirm appears: title *"Revoke Migration"*, asking to change the
   status to `"revoked"`, with **Ok** / **Cancel**.
3. Press **Ok**.

### Then

1. `PUT /api/v4/admin/item/user-migration/<id>/revoke` is called and responds
   `204`.
2. A success PNotify *"Migration revoked"* appears.
3. The table reloads; the row now has status `revoked` and its action cell is
   **empty** (the `.btn-revoke` button is gone).
4. Verify via the list endpoint that the row's `status` is `revoked`.

### Cancel branch

1. Pressing **Cancel** fires **no** PUT request; the row keeps status
   `exported` and still shows the Revoke button.

---

## Scenario A9 — *non-admin cannot reach the Migration screen*

### Given

1. A non-admin session: a `user` (and, separately, a `manager`).

### When

1. Navigate to `/isard-admin/admin/users/migration`.

### Then

1. Access is denied — the `@isAdmin` guard redirects to login (or returns
   403); the migrations table is not rendered.
2. The **Migration** sidebar entry is not available to the non-admin.

> If the denial behaviour cannot be asserted cleanly through the webapp for a
> given role, flag it at implementation time and cover the authorization at the
> API layer (`GET /api/v4/admin/item/user-migrations` must reject non-admins).

---

## Cleanup

- **A1–A6** mutate nothing — no cleanup.
- **A7 / A8** delete their seeded row via the SDK admin delete endpoint
  (`deleteMigration`) in `afterEach`, like the rest of the suite (ignore 404 if
  the confirm test already removed it). A full `populate` reseed restores all
  rows to canonical state; consumed rows that have not been reseeded cause the
  owning test to `test.skip()` (see *Mutating rows*).

---

## Expected results — global summary

| Scenario | Covered | Key checks |
| --- | --- | --- |
| A1 — Table loads, all statuses | ✅ | All status rows visible; no `undefined` cell; per-status action button; `exported`/`revoked` Target = `"-"` |
| A2 — Global search | ✅ | Typing a known value narrows rows; clearing restores |
| A3 — Per-column footer search | ✅ | Status footer input filters to one status |
| A4 — Details: success | ✅ | 4-row sub-table; counts or `"-"`; no red/error |
| A5 — Details: failed | ✅ | Red circle + error text on failed type |
| A6 — Details: non-migrated | ✅ | All `"-"`, no JS error |
| A7 — Delete (`migrated`) | ✅ | Confirm → `DELETE` 204 → row gone; Cancel → no request |
| A8 — Revoke (`exported`) | ✅ | Confirm → `PUT …/revoke` 204 → status `revoked`; Cancel → no request |
| A9 — Permissions | ⚠️ | Non-admin denied (redirect/403); sidebar item absent — verify at impl, fall back to API-layer check |

## APIs touched by the flows (reference)

- `GET    /api/v4/admin/item/user-migrations` — DataTable source. Response
  `{ "migrations": [ … ] }` (admin only).
- `PUT    /api/v4/admin/item/user-migration/{id}/revoke` — revoke. `204`;
  `400` if status not in `exported/imported/migrating`; `404` if not found.
- `DELETE /api/v4/admin/item/user-migration/{id}` — delete. `204`; `404` if
  not found.

> The user-facing self-migration endpoints
> (`PUT /api/v4/item/user-migration/export-user`,
> `PUT /api/v4/item/user-migration/import-user`,
> `POST /api/v4/item/user-migration/migrate-user`) are used **only** in the
> one-time authentic seed generation, not by the tests.

## Relevant database state

- `users_migrations` — the table behind the screen. Stored fields:
  `id`, `token`, `origin_user`, `target_user`, `status`, `created`,
  `export_time`, `import_time`, `migration_start_time`, `migration_end_time`,
  `migrated_items` (`{desktops,templates,media,deployments}` lists of ids),
  and per-type `migrated_<type>` (bool) + `migrated_<type>_error` (str).
- `origin_username` / `target_username` / `category` are **not stored** here —
  they are joined from `users` / `categories` at read time.

## Notes / known issues

- **Target `"-"` vs `"[DELETED]"`** (verified against the live API): for rows
  with no `target_user` (e.g. `exported`, `revoked`), the backend sends
  `target_username: null`, so the JS `data ? data : "-"` fallback renders `"-"`.
  `"[DELETED]"` only appears when a `target_user`/`origin_user`/`category` *is*
  set but the referenced record was deleted. So assert `"-"` for the
  no-target rows, never `undefined`.
- **Detail-panel fragility (documented, not tested)**: the render uses
  `d?.migrated_items?.desktops.length` — optional chaining guards only
  `migrated_items`, so a row where `migrated_items` exists but a type key is
  missing would throw. The seed always includes all four keys, so this is
  avoided; flagged as a latent product issue.
- **Status values**: `exported`, `imported`, `migrating`, `migrated`, `failed`,
  `revoked`.
- **Auth**: the page is an `isard-admin` Flask route — the bridged admin
  session is required (the `authenticatedPage` fixture), not just an apiv4 JWT.

## Cases not covered (future)

- The full end-user self-migration flow as an E2E journey (export → import →
  migrate-user), including `action_after_migrate` side effects on the origin
  user.
- The `migrating → migrated/failed` transition observed live (the failed/
  migrating states are seeded, not produced in real time).
