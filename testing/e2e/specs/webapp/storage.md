# Storage management in webapp

Human-readable functional specification for the **Storage** admin page at
`/isard-admin/admin/domains/render/Storage`. Serves as the contract for the
E2E test `tests/webapp/storage.spec.js`.

## Scope

- **Component**: administration panel.
- **Screen**: **Storage** view (`/isard-admin/admin/domains/render/Storage`).
- **Sections covered**:
  - Three-table layout: **Ready**, **Maintenance**, and **Other status**.
  - Column filters (category, user, parent, path).
  - Global actions on the Ready and Other Status tables.
  - UUID quick-search bar in the page header.
  - Row detail expansion (backing chain + UUID-duplicate subtables).
  - Info icon → **Storage search modal** (`#modalSearchStorage`) with per-storage
    data and action buttons.
  - **Create storage** modal (`#modalCreateStorage`).
  - Per-row admin action buttons: Find, Delete scheduler, Retry task.
  - **Other status** dropdown (non-ready / non-maintenance storages).
  - **Duplicated UUIDs** section (`#storagesUUID`).
- **Out of scope**: disk operation results that require a running hypervisor
  (Sparsify completion, Move completion, Increase result).
  Those operations are triggered and the API call is verified; the resulting
  storage-status transition is not awaited.

## Common role and prerequisites

| Element | Expected value |
| --- | --- |
| Role | Administrator of the `default` category |
| Session | Logged in to the webapp |
| Page | `/isard-admin/admin/domains/render/Storage` |
| Seed storage A (ready, non-UUID id) | `storage-template-test-001` · status `ready` · path `/isard/templates` · format `qcow2` · user `local-default-admin-admin` |
| Seed storage B (ready, UUID id) | `e2e00000-0000-0000-0000-000000000001` · status `ready` · path `/isard/templates` · format `qcow2` · user `local-default-admin-admin` |
| Seed storage C (ready, UUID id, disposable) | `e2e00000-0000-0000-0000-000000000002` · status `ready` · path `/isard/templates` · format `qcow2` · user `local-default-admin-admin` — deleted by S23 |

> **Why three seeds?** The `#modalSearchStorage` search field validates UUID format with a strict
> regex (`/^[0-9a-f]{8}-[0-9a-f]{4}-…$/i`). Seed A (`storage-template-test-001`) fails this
> check and cannot be loaded into the modal. All scenarios that go through the modal
> (actions: Move, Windows Registry, Increase, Add Disk, Sparsify, Disconnect, Find from modal,
> Delete from modal) use **Seed B** which has a proper UUID-format id. **Seed C** is an
> identical, disposable UUID-format row that S23 deletes, so Seed B stays intact for the
> other tests. All three are seeded in `testing/db/data/storage.json`.

## Common data

| Field | Sample value | Notes |
| --- | --- | --- |
| Seed A id | `storage-template-test-001` | Non-UUID; used for row-level tests (find, detail expand) |
| Seed B id | `e2e00000-0000-0000-0000-000000000001` | UUID format; used for all modal-based action tests |
| Seed C id | `e2e00000-0000-0000-0000-000000000002` | UUID format; disposable row deleted by S23 |
| Valid UUID format | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` | Required by the UUID search bar and modal search validators |
| Invalid UUID examples | `abc`, `not-a-uuid`, `storage-template-test-001` | Non-UUID format strings — rejected by the validator |

---

## Scenario 1 — *page loads and the three table panels render*

### Given

1. The administrator is authenticated in the webapp.

### When

1. They navigate to `/isard-admin/admin/domains/render/Storage`.

### Then

1. The page title "Storage files" is visible.
2. The **Ready** table (`#storage`) is visible and has loaded (spinner gone,
   at least the `<tbody>` is present).
3. The seeded storage `storage-template-test-001` appears as a row in the
   Ready table with status `ready`.
4. The **Maintenance** table (`#storagesMaintenance`) panel is visible with
   its "Storage files in maintenance" heading.
5. The **Other status** panel is visible with its status dropdown (`#status`)
   enabled and populated (at least one option beyond "Select status").
6. The **Duplicated UUIDs** panel is visible with its dropdown
   (`#uuid_status`) enabled.
7. No API calls to `/api/v4/admin/items/storage/by-status/ready` return a
   5xx status.

---

## Scenario 1b — *Seed A row renders the expected value in every column*

> This scenario is the data contract between the API and the table. If the row
> is not filled correctly, all tests that rely on the visual state of the table
> will fail for the wrong reason.

### Given

1. The page has loaded and the Ready table (`#storage`) shows the row with id
   `storage-template-test-001` (Seed A).

### When

1. The administrator locates the row by its id (the `id` attribute of the `<tr>`).

### Then

Each column is verified against the expected seed value:

| Column | DataTable field | Expected value |
| --- | --- | --- |
| **Status** | `data: 'status'` | text `ready` |
| **Path** | `data: 'directory_path'` | text `/isard/templates` |
| **Id** | `data: 'id'` | text `storage-template-test-001` |
| **Format** | `data: 'type'` | text `qcow2` |
| **Size** | `data: 'qemu-img-info.virtual-size'` | text `-` (seed has no `qemu-img-info`) |
| **Used** | `data: 'qemu-img-info.actual-size'` | text `-` (same reason) |
| **Parent** | `data: 'parent'` | text `-` (seed has `parent: null`) |
| **User** | `data: 'user_name'` | non-empty text (resolved name for `local-default-admin-admin`) |
| **Category** | `data: 'category'` | non-empty text (category of the owner user) |
| **Perms** | `data: 'perms'` | contains `r` (seed has `perms: ["r"]`) |
| **Last** | `data: 'last'` | readable text (e.g. "a few seconds ago", "N/A") — not empty, not `undefined` |
| **Task** | `data: 'task'` | `.btn-task-info` button is **absent** (seed has no `task` field) |

Additionally, the admin action buttons on the row:

| Button | Selector | Present? | Reason |
| --- | --- | --- | --- |
| Find | `.btn-find` | ✅ Yes | always shown for admin |
| Delete scheduler | `.btn-delete-scheduler` | ✅ Yes | shown when `status = ready` |
| Retry task | `.btn-retry-task` | ❌ No | only shown when the row has a `task` field |
| Delete orphan | `.btn-delete-orphan` | ❌ No | only shown when `status = orphan` |

---

## Scenario 1c — *Category filter is added automatically on page load*

### Given

1. The admin navigates to the Storage page.

### When

1. The page finishes loading.

### Then

1. The `#filter-boxes` container already contains one filter box for **Category**
   (`#filter-category`) — it is added automatically by `initial_filters()` without
   the admin having to select it from the dropdown.
2. The Category Select2 (`#category`) is populated with available categories
   (fetched from `GET /api/v4/admin/item/userschema`).
3. The admin's own category (`default`) is pre-selected in the Select2.
4. The **"Category"** option is no longer present in the `#filter-select` dropdown
   (it has been removed to prevent duplicate addition).

---

## Scenario 1d — *Adding a path filter shows clickable options from the table data*

### Given

1. The Ready table has loaded with at least one row (Seed A, path `/isard/templates`).

### When

1. The admin opens the `#filter-select` dropdown and selects **"Path"**.

### Then

1. A new filter box for Path appears in `#filter-boxes` with:
   - A label **"Path"**.
   - An operator selector (`#operator-path`) with options **"is"** and **"is not"**.
   - A Select2 multi-select input (`#path`) populated with the distinct
     `directory_path` values currently loaded in the Ready table
     (e.g. `/isard/templates`).
2. The **"Path"** option is removed from `#filter-select` (preventing a second
   Path filter from being added).
3. Clicking inside the Select2 opens a dropdown showing the available path options;
   clicking `/isard/templates` selects it (it appears as a tag in the input).

---

## Scenario 1e — *Search with a path filter applied narrows the Ready table*

### Given

1. A Path filter has been added (as per S1d) with `/isard/templates` selected and
   operator set to **"is"**.

### When

1. The admin clicks the **Search** button (`#btn-search`).

### Then

1. The Ready table is filtered client-side: only rows whose **Path** column matches
   `/isard/templates` exactly are shown.
2. Seed A (`storage-template-test-001`, path `/isard/templates`) remains visible.
3. Rows with a different path are hidden. The environment is **not** seed-only — it
   is a populated dev DB (e.g. dozens of `/isard/groups` disks alongside the few
   `/isard/templates` ones), so the test asserts narrowing for real: every visible
   row must be a `/isard/templates` disk (count-independent, tolerant of the
   fluctuating dev-data totals).
4. No network request is made for path/user/parent filters — the search runs against
   the already-loaded DataTable data.

---

## Scenario 1f — *Operator "is not" excludes the selected path value*

### Given

1. A Path filter has been added with `/isard/templates` selected and operator set
   to **"is not"**.

### When

1. The admin clicks **Search**.

### Then

1. The Ready table hides rows whose Path column matches `/isard/templates` and shows
   only rows with a different path.
2. Seed A is **not** visible (its path is `/isard/templates`, which is excluded).
3. In the populated dev DB the non-matching rows (e.g. `/isard/groups`) remain, so
   the test asserts that no visible row is a `/isard/templates` disk (and that rows
   remain). The DataTables empty-state would only show if every row matched.

---

## Scenario 1g — *Clear button removes all filter boxes and restores the dropdown*

### Given

1. At least one additional filter (e.g. Path) has been added to `#filter-boxes`
   alongside the default Category filter.

### When

1. The admin clicks the **Clear** button (`#btn-clear`).

### Then

1. All filter boxes are removed from `#filter-boxes` (including Category and Path).
2. The `#filter-select` dropdown is repopulated with all four options:
   Category, User, Parent, Path — restored in alphabetical order.
3. The Ready table clears any previously applied column search and shows all rows.

---

## Scenario 1h — *Individual filter delete (×) removes one filter and restores its option*

### Given

1. Both a Path filter and a User filter have been added to `#filter-boxes`.

### When

1. The admin clicks the **×** button (`btn-delete-filter`) on the Path filter only.

### Then

1. The Path filter box (`#filter-path`) is removed from `#filter-boxes`.
2. The User filter box remains untouched.
3. The **"Path"** option is restored to the `#filter-select` dropdown.
4. Any column search applied by the Path filter is cleared and the table redraws.

---

## Scenario 1i — *Reload button repopulates non-category filter options*

### Given

1. A User filter has been added. Its Select2 is populated with the user names
   currently in the Ready table.

### When

1. The admin clicks the **Reload** button (`#btn-reload`).

### Then

1. The Ready table redraws (showing all rows, ignoring any previous filter draw).
2. The User filter Select2 is repopulated with the updated list of `user_name`
   values from the reloaded table data.
3. The Category filter is not repopulated (it comes from the API, not the table data).

> **Known limitation**: `#btn-reload` calls `reloadOtherFiltersContent(domains_table)`
> where `domains_table` is not defined on the Storage page. If this causes a JS
> error instead of the expected behaviour, that is a bug the test should surface,
> not a reason to skip the assertion.

---

## Scenario 2 — *UUID search bar blocks an invalid UUID*

### Given

1. The admin is on the Storage page.
2. The UUID search input (`#storage-uuid-search`) and its button
   (`#storage-uuid-search-btn`) are visible in the page header.

### When

1. They type an invalid value (e.g. `not-a-valid-uuid`) into the input.
2. They click the **search** button (or press Enter).

### Then

1. A PNotify error notification appears with title **"Invalid UUID"** and a
   message about the expected format.
2. The `#modalSearchStorage` modal does **not** open.
3. No call is made to `/api/v4/admin/item/storage/search-info/…`.

---

## Scenario 3 — *UUID search bar opens the modal for a known storage*

### Given

1. Seed B (`e2e00000-0000-0000-0000-000000000001`) is present in the Ready table.

### When

1. They type Seed B's UUID (`e2e00000-0000-0000-0000-000000000001`) into
   the UUID search input.
2. They click the search button.

### Then

1. `GET /api/v4/admin/item/storage/search-info/<id>` is called with
   status `< 400`.
2. The `#modalSearchStorage` modal opens.
3. The **storage info** section (`#storage-info`) is visible and shows
   the storage ID, status, path, and size fields.
4. The **storage actions** section (`#storage-actions`) is visible with
   action buttons.
5. If the storage status is `ready`, all action buttons are enabled.
6. If the storage status is **not** `ready`, action buttons other than
   Find and Delete are disabled.

---

## Scenario 4 — *UUID search modal shows "not found" for an unknown storage*

### Given

1. The admin is on the Storage page.

### When

1. They enter a well-formed UUID that does not exist in the DB (e.g.
   `00000000-0000-0000-0000-000000000000`) into the UUID search input.
2. They click the search button.

### Then

1. `GET /api/v4/admin/item/storage/search-info/00000000-0000-0000-0000-000000000000`
   returns `404`.
2. A PNotify error notification appears with a "not found" message.
3. The `#storage-info` and `#storage-actions` sections inside the modal
   remain hidden (or the modal stays closed if it was never shown).

---

## Scenario 5 — *row info icon opens the search modal pre-populated*

### Given

1. Seed B (`e2e00000-0000-0000-0000-000000000001`) is present in the Ready table.

> **Why Seed B?** `openStorageSearchModal(storageId)` calls `isValidStorageUUID()` before
> searching. Seed A's id (`storage-template-test-001`) fails the UUID check, so the modal
> opens but the auto-search is blocked. Seed B's UUID-format id passes the check.

### When

1. The admin clicks the **info** icon (`#btn-info`) on Seed B's row.

### Then

1. The `#modalSearchStorage` modal opens.
2. The search field (`#storage-id`) is pre-populated with Seed B's UUID.
3. `GET /api/v4/admin/item/storage/search-info/<seed-b-id>`
   is called automatically (the modal performs the search on open).
4. The storage info section shows the expected fields (ID, status `ready`,
   path containing `/isard/templates`).
5. The storage actions buttons are visible and enabled (status is `ready`).

---

## Scenario 6 — *row detail expands the backing chain and UUID subtables*

### Given

1. The seeded storage `storage-template-test-001` appears in the Ready table.

### When

1. The admin clicks the **expand** button (`#btn-details`) on the seeded
   storage row.

### Then

1. The row expands inline showing a child area.
2. `GET /api/v4/item/storage/storage-template-test-001/parents` is called;
   the child DataTable (`#cl<id>`) renders with at least the seeded storage
   itself as entry #1 (bold).
3. `GET /api/v4/item/storage/storage-template-test-001/storages_with_uuid`
   is called; if the result is empty the UUID-duplicate container for this
   storage is hidden.
4. A **"Storage actions"** button (`.btn-storage-actions`) appears inside
   the expanded area (admin only). Clicking it opens `#modalSearchStorage`
   pre-populated with the storage ID (same behaviour as S5).
5. Clicking the expand button a second time **collapses** the row.

---

## Scenario 7 — *Find action enqueues a task and shows success notification*

### Given

1. The seeded storage `storage-template-test-001` is in the Ready table.

### When

1. The admin clicks the **find** button (`.btn-find`) on the seeded storage row.

### Then

1. `GET /api/v4/item/storage/storage-template-test-001/find` is called with
   status `< 400`.
2. A PNotify success notification appears with title **"Find task started"**
   and text indicating status will update when the scan completes.
3. No navigation occurs; the admin remains on the Storage page.

---

## Scenario 8 — *Other status dropdown populates and loads a table*

### Given

1. The admin is on the Storage page.
2. `GET /api/v4/admin/item/storage/status` has returned a list that includes
   at least one status beyond `ready` and `maintenance` (e.g. `deleted`,
   `orphan`).

### When

1. The admin opens the **Other storages status** dropdown (`#status`) and
   selects a status.

### Then

1. `POST /api/v4/admin/items/storage/by-status/<selected_status>` is called.
2. The `#storagesOtherTable` DataTable is (re)created and its rows reflect
   the selected status.
3. If the status has no items, the table shows the DataTables empty-state
   text (no JS error, no spinner stuck).

---

## Scenario 9 — *Global action on Ready table with a filter applied asks for confirmation*

### Given

1. The Ready table has at least one row (the seeded storage).
2. The admin applies a column filter in the table footer (e.g. filters by
   path containing `/isard/templates`) so that some rows match.

### When

1. The admin selects **"Find & update disks"** from the **Global actions**
   dropdown (`.mactionsStorage[selectedTableId="storage"]`).

### Then

1. A PNotify confirmation dialog appears with title **"Confirmation Needed"**
   and a message stating the action will be performed on N storages.
2. If the admin clicks **Ok**:
   a. `PUT /api/v4/items/storage/find` is called with a JSON body containing
      the list of matching storage IDs.
   b. The API returns status `< 400`.
   c. A success PNotify appears.
   d. The dropdown resets to "Select action".
3. If the admin clicks **Cancel**, no API call is made and the dropdown
   resets.

---

## Scenario 10 — *Global action on Ready table with no filter requires text confirmation*

### Given

1. The Ready table has no active column filter (the search fields in the
   footer are empty).

### When

1. The admin selects **"Sparsify disks"** from the Global actions dropdown.

### Then

1. A PNotify confirmation dialog appears with title **"Warning!"** asking the
   admin to type **`I'm aware`** to confirm the bulk action on all storages.
2. If the admin types `I'm aware` and clicks **Ok**:
   a. `PUT /api/v4/items/storage/sparsify/ready` is called.
   b. The API returns status `< 400` (or an error surfaced in PNotify).
   c. The dropdown resets.
3. If the admin clicks **Cancel**, no API call is made.
4. Typing a wrong phrase and pressing Ok does **not** trigger the API call.

---

## Scenario 11 — *Create storage modal opens and validates required fields*

### Given

1. The admin is on the Storage page.

### When

1. They click the **"Create storage"** link/button (`.btn-add-storage`) in
   the page header.

### Then

1. The `#modalCreateStorage` modal opens with title **"Add new unattached
   storage disk"**.
2. The user search field (`#user` Select2) is present and requires at least
   2 characters before showing results.
3. If the admin clicks **Send** without filling in required fields, Parsley
   validation blocks the submission and no API call is made.
4. Filling in a valid user, size and format, then clicking **Send**, calls
   `POST /api/v4/item/storage/priority/<priority>` and shows a success
   notification.
5. The modal closes automatically on success.

> **E2E test status note**: Both paths are covered. Steps 1–3 (modal opens,
> Parsley blocks the empty form) run as S11; the "Send" success path (steps 4–5)
> runs as S11b — it creates a real unattached disk via
> `POST /api/v4/item/storage/priority/<priority>` (no `parent`), captures the new
> id from the response and deletes it in `afterEach`.

---

## Scenario 12 — *Duplicated UUIDs section loads when a status is selected*

### Given

1. The admin is on the Storage page.
2. `GET /api/v4/items/storage/storages_with_uuid/status` returns at least
   the "All" option.

### When

1. The admin opens the **Found file status** dropdown (`#uuid_status`) and
   selects **"All"**.

### Then

1. `GET /api/v4/items/storage/storages_with_uuid` is called.
2. The `#storagesUUID` DataTable renders (even if it has no rows — the
   empty state is shown rather than a JS error).
3. Each row with status `duplicated` has both a **Delete** button
   (`.btn-uuid-delete`) and a **Set as storage path** button
   (`.btn-uuid-set-path`).
4. Rows with other statuses only show the **Delete** button.

---

## Scenario 13 — *Maintenance table renders and shows progress column*

### Given

1. The admin is on the Storage page.

### When

1. The page loads (maintenance table is always initialised on load).

### Then

1. `POST /api/v4/admin/items/storage/by-status/maintenance` is called.
2. The `#storagesMaintenance` DataTable renders without JS errors.
3. The **Progress** column is visible in the maintenance table (it is hidden
   in the ready table).
4. If no storage is in maintenance, the table shows the DataTables empty-state.

---

## Scenario 15 — *Delete scheduler confirms and calls the scheduler endpoint*

### Given

1. The seeded storage `storage-template-test-001` is in the Ready table.

### When

1. The admin clicks the **delete scheduler** button (`.btn-delete-scheduler`)
   on the row.
2. A PNotify confirmation dialog appears.
3. The admin clicks **Ok**.

### Then

1. `DELETE /scheduler/storage-template-test-001.stg_action` is called.
2. A PNotify success notification with title **"Deleted"** appears.
3. If the scheduler did not exist the API may return an error; the error
   PNotify should appear and the page should not crash.

---

## Scenario 16 — *Move action: modal opens with pool options and Send fires the API*

### Given

1. Seed B (`e2e00000-0000-0000-0000-000000000001`) is visible in the Ready table.
2. The admin opens `#modalSearchStorage` for Seed B (via the row info button or
   UUID search bar) and the storage info section loads.

### When

1. The admin clicks the **Move** button (`.btn-modal-move`) inside the actions panel.

### Then

1. `#modalSearchStorage` closes.
2. `GET /api/v4/item/storage/<id>/has-derivatives` is called.
   - If `derivatives > 1`: a PNotify error "This storage has derivatives" is shown and
     `#modalMoveStorage` does **not** open. *(Seed B has no children so this branch
     is not exercised here — see S24.)*
3. `GET /api/v4/admin/item/storage/info/<id>` is called.
4. `PUT /api/v4/storage-pool/by-path` is called with the storage's `directory_path`.
5. `GET /api/v4/storage-pools` is called to populate the destination pool selector.
6. `#modalMoveStorage` opens.
7. The modal shows radio buttons to choose between "same pool" (by path) and
   "different pool" (by storage pool).
8. The priority dropdown is populated with at least one option.
9. Clicking **Cancel** closes the modal without making any move call.

> **Send path**: with the default selection (mv, within the same pool), Send fires
> `PUT /api/v4/item/storage/<id>/move/by-path` (the rsync radio uses
> `…/rsync/to-path`). Selecting a valid destination path is required first. The e2e
> test (S16) stubs this op and verifies the call fires, a success PNotify shows and
> the modal closes; S16b verifies Cancel fires no move call.

---

## Scenario 17 — *Windows Registry action: modal opens and validates the file*

### Given

1. Seed B is visible in the Ready table and its storage info is loaded in
   `#modalSearchStorage`.

### When

1. The admin clicks the **Windows Registry** button (`.btn-modal-virt_win_reg`).

### Then

1. `#modalSearchStorage` closes.
2. `GET /api/v4/item/storage/<id>/has-derivatives` is called; since Seed B has no
   children (`derivatives ≤ 1`) the modal opens.
3. `#modalVirtWinReg` opens with title **"Apply Windows Registry Patch"**.
4. The file input (`#registry_file`) accepts `.reg` files only.
5. If the admin clicks **Send** without selecting a file, Parsley blocks the
   submission and no API call is made.
6. If the admin uploads a file with the wrong MIME type (not `text/x-ms-regedit`),
   a PNotify error **"File must be a regedit file"** appears and no API call is made.
7. If the admin uploads a file larger than 1 MB, a PNotify error about the size limit
   appears and no API call is made.

> **Send with a valid file**: uploading a valid `.reg` file and clicking Send calls
> `PUT /api/v4/item/storage/<id>/virt-win-reg/priority/<priority>`. In the e2e
> environment this may return an error from the engine; verify the call fires and
> the modal closes or an error PNotify appears.

---

## Scenario 18 — *Increase action: modal opens with current size and validates new size*

### Given

1. Seed B is visible in the Ready table and its storage info is loaded in
   `#modalSearchStorage`.

### When

1. The admin clicks the **Increase** button (`.btn-modal-increase`).

### Then

1. `#modalSearchStorage` closes.
2. `GET /api/v4/admin/item/storage/info/<id>` is called and returns the storage data
   including `virtual_size`.
3. `GET /api/v4/item/storage/<id>/has-derivatives` is called; since Seed B has no
   children the modal opens.
4. `GET /api/v4/admin/item/user/appliedquota/<user_id>` is called to determine the
   quota ceiling for the new-size field.
5. `#modalIncreaseStorage` opens.
6. The **"Current size"** label shows the storage's current size in human-readable
   units (e.g. "0 B" for an empty seed, never "NaN").
7. The **"New size"** spinner (`#new-size`) is pre-filled with `⌊current GB⌋ + 1`
   and its `min` attribute equals that value (so values ≤ current size are rejected).
8. Clicking **Send** with `new-size ≤ current-size` is blocked by Parsley
   (min constraint). No API call is made.
9. Entering a valid larger value and clicking **Send** calls
   `PUT /api/v4/item/storage/<id>/priority/<priority>/increase/<increment>`.

---

## Scenario 19 — *Add Disk (create derived) action: modal opens in derive mode*

### Given

1. Seed B is in path `/isard/templates` (kind = `template` in the pool paths).
2. Seed B's storage info is loaded in `#modalSearchStorage`.

### When

1. The admin clicks the **Add Disk** button (`.btn-modal-create`, admin-only).

### Then

1. `#modalSearchStorage` closes.
2. `GET /api/v4/admin/item/storage/info/<id>` and
   `PUT /api/v4/storage-pool/by-path` are called to determine the disk kind.
3. Because the path maps to `kind = "template"`, `#modalCreateStorage` opens
   in **"Create derived storage disk"** mode:
   - The modal title reads **"Create disk"**.
   - The **"Parent storage ID"** field (`#storage_id`) is populated with Seed B's id.
   - The **"Owner"** field is hidden.
   - The `storage_pool` select is disabled (the pool is inherited from the parent).
4. Clicking **Send** calls
   `POST /api/v4/item/storage/priority/<priority>` with the parent id in the body.

> **Error case** (not applicable to Seed B but documented): if the storage's path maps
> to a kind other than `"template"` (e.g. it's a desktop disk), the button shows a
> PNotify error "Disks can only be derived from template disks" and the modal does not
> open.

> **Send path**: Send fires `POST /api/v4/item/storage/priority/<priority>` with the
> parent id in the body. The e2e test (S19) stubs this op and verifies the POST fires,
> a success PNotify shows and the modal closes; S19b verifies Cancel fires no create.

---

## Scenario 20 — *Sparsify action: modal opens with priority selector*

### Given

1. Seed B's storage info is loaded in `#modalSearchStorage`.

### When

1. The admin clicks the **Sparsify** button (`.btn-modal-sparsify`, admin-only).

### Then

1. `#modalSearchStorage` closes.
2. `GET /api/v4/item/storage/<id>/has-derivatives` is called (the result does not
   block the modal for Sparsify — it opens regardless).
3. `#modalSparsify` opens.
4. The priority dropdown is populated with Low / Default / High (admin role).
5. Clicking **Send** calls
   `PUT /api/v4/item/storage/<id>/sparsify/priority/<priority>`.
6. A success PNotify appears and the modal closes.
7. Clicking **Cancel** closes the modal without making any API call.

---

## Scenario 21 — *Disconnect action: modal opens and Send fires the API*

### Given

1. Seed B's storage info is loaded in `#modalSearchStorage`.

### When

1. The admin clicks the **Disconnect** button (`.btn-modal-disconnect`, admin-only).

### Then

1. `#modalSearchStorage` closes.
2. `#modalDisconnect` opens immediately (no `has-derivatives` pre-check).
3. The priority dropdown is populated.
4. Clicking **Send** calls
   `PUT /api/v4/item/storage/<id>/disconnect/priority/<priority>`.
5. Clicking **Cancel** closes the modal without firing the API.

---

## Scenario 22 — *Find action from modal: direct API call, no secondary modal*

### Given

1. Seed B's storage info is loaded in `#modalSearchStorage`.

### When

1. The admin clicks the **Find** button (`.btn-modal-find`, admin-only) inside the
   actions panel.

### Then

1. `#modalSearchStorage` closes immediately (the JS hides it before the API call).
2. `GET /api/v4/item/storage/<id>/find` is called with status `< 400`.
3. A PNotify success notification with title **"Find task started"** appears.
4. No secondary modal opens.

---

## Scenario 23 — *Delete action from modal: confirmation and DELETE call*

### Given

1. Seed B's storage info is loaded in `#modalSearchStorage`.

### When

1. The admin clicks the **Delete** button (`.btn-modal-delete`, admin-only).

### Then

1. `#modalSearchStorage` closes.
2. A PNotify confirmation dialog appears with title **"Confirmation Needed"** and
   a message asking to confirm deletion of the storage ID.
3. If the admin clicks **Ok**:
   a. `DELETE /api/v4/item/storage/<id>` is called.
   b. On success (status `< 400`): a PNotify success **"Deleted"** appears; the Ready,
      Maintenance and Other-status tables reload.
   c. On error: a PNotify error appears with the API description.
4. If the admin clicks **Cancel**:
   - No DELETE call is made.
   - The page remains unchanged.

> **Test note**: this test should use a storage created and tracked in `beforeAll`
> (not Seed B itself) so the seed remains intact for other tests. After delete,
> verify via `GET /api/v4/admin/item/storage/search-info/<id>` that the storage
> is gone (404).

---

## Scenario 24 — *Move / Increase blocked when storage has derivatives*

### Given

1. A storage with `derivatives > 1` exists. The webapp guard checks
   `data.derivatives > 1`, so the parent needs **2** derived children. The test
   builds this at runtime (unattached parent + 2 children via the apiv4 SDK) and
   cleans it up in `afterEach` (children before the parent).

### When

1. The admin opens `#modalSearchStorage` for the parent storage and clicks
   **Move**, **Windows Registry** or **Increase**.

### Then

1. `GET /api/v4/item/storage/<id>/has-derivatives` returns `derivatives > 1`.
2. A PNotify error appears:
   - **Move / Windows Registry**: "This storage has derivatives"
   - **Increase**: "Size of disks with derivatives cannot be modified"
3. The corresponding action modal (`#modalMoveStorage`, `#modalVirtWinReg`,
   `#modalIncreaseStorage`) does **not** open.

> **E2E test status**: Covered (S24). The test builds the fixture via the apiv4 SDK
> (own request context, so it bypasses the beforeEach create-stub and creates REAL
> disks): an unattached parent polled until `ready`, then 2 derived children so
> `has-derivatives` returns 2. It then opens `#modalSearchStorage` for the parent
> and asserts Move, Windows Registry and Increase each surface the block PNotify and
> keep their action modal closed. The parent + children are deleted in `afterEach`
> (children first). If the env cannot build the fixture, the test `skip`s instead of
> failing.

---

## Cleanup (afterEach)

1. Most tests create no persistent state (read-only actions, or actions that only
   enqueue tasks against a shared seed — and those disk ops are stubbed so they
   never mutate the DB record). The exceptions are S11b (creates a real unattached
   disk) and S23 (deletes the disposable Seed C).
2. Tests that open modals close them via `Escape` or the `×` button if the
   test fails mid-flow, so subsequent tests start with a clean modal state.
3. Any storage rows added during a test (S11b's unattached disk, tracked via its
   POST response id) are deleted via API in `afterEach`.

---

## Expected results — global summary

| Scenario | Covered in test? | Key checks |
| --- | --- | --- |
| S1 — Page load | ✅ | Three panels visible, Ready table shows seed rows, no 5xx |
| S1b — Row data integrity | ✅ | Every column of Seed A row contains the correct value; action buttons present/absent per status |
| S1c — Category filter auto-added on load | ✅ | Filter box present without user interaction; Select2 populated; current category pre-selected; option removed from dropdown |
| S1d — Add path filter; Select2 shows options | ✅ | Filter box created; operator selector present; Select2 populated with paths from table data; clicking input shows options |
| S1e — Search with "is" operator filters table | ✅ | Client-side column search applied; matching rows visible; no network call |
| S1f — Search with "is not" operator excludes rows | ✅ | Matching rows hidden; empty-state shown if no rows remain |
| S1g — Clear button removes all filters | ✅ | All filter boxes gone; all four options restored to dropdown; table redraws |
| S1h — Individual × removes one filter only | ✅ | Target filter box removed; other filter intact; option restored to dropdown |
| S1i — Reload repopulates non-category filters | ⚠️ | Table redraws; User/Parent/Path Select2 repopulated — may surface `domains_table` bug |
| S2 — UUID search: invalid format | ✅ | PNotify "Invalid UUID"; modal does NOT open; no API call |
| S3 — UUID search: known storage | ✅ | API called; modal opens; info + actions sections visible |
| S4 — UUID search: unknown ID (404) | ✅ | 404 → PNotify error; info/actions sections hidden |
| S5 — Row info icon → modal pre-populated | ✅ | Modal opens; field pre-filled; API auto-searched; info visible |
| S6 — Row detail expand | ✅ | Child table rendered; UUID-dup container hidden if empty; collapse works |
| S7 — Find row action | ✅ | API called `< 400`; PNotify "Find task started" |
| S8 — Other status dropdown | ✅ | API called for selected status; table renders; empty state OK |
| S9 — Global action with filter (Ok path) | ✅ | Confirmation with row count; API called with IDs; dropdown resets |
| S10 — Global action no filter (text confirmation) | ✅ | Warning dialog; `I'm aware` gating; wrong text blocks API |
| S11 — Create storage modal | ✅ | Modal opens; Parsley blocks empty form (S11); Send creates a real unattached disk and cleans it up (S11b) |
| S12 — Duplicated UUIDs section | ✅ | Status API; table renders; correct buttons per row status |
| S13 — Maintenance table renders | ✅ | API called; Progress column visible; empty state OK |
| S15 — Delete scheduler confirms | ✅ | Confirmation dialog; DELETE call; success or error PNotify |
| S16 — Move modal | ✅ | has-derivatives + info + pool APIs called; modal opens; Send fires move API (S16); Cancel safe (S16b) |
| S17 — Windows Registry modal | ✅ | Modal opens; wrong MIME rejected; oversized file rejected; Parsley blocks no-file |
| S18 — Increase modal | ✅ | Current size shown (no NaN); new-size min enforced; Send fires increase API |
| S19 — Add Disk (derive) modal | ✅ | Modal opens in derive mode; parent id populated; owner hidden; Send fires create API (S19); Cancel safe (S19b) |
| S20 — Sparsify modal | ✅ | Modal opens; priority populated; Send fires sparsify API; Cancel safe |
| S21 — Disconnect modal | ✅ | Modal opens without pre-check; Send fires disconnect API; Cancel safe |
| S22 — Find from modal | ✅ | Search modal closes; find API called; PNotify "Find task started" |
| S23 — Delete from modal | ✅ | Confirmation dialog; DELETE call; tables reload on success |
| S24 — Move/WinReg/Increase blocked (derivatives) | ✅ | Builds parent + 2 derived children via SDK; each action shows the block PNotify and its modal stays closed |

## APIs touched by the flows (reference)

- `POST   /api/v4/admin/items/storage/by-status/{status}` — load a table by status.
- `GET    /api/v4/admin/item/storage/status` — status options list for the "Other status" dropdown.
- `GET    /api/v4/admin/item/storage/search-info/{id}` — storage info for the search modal.
- `GET    /api/v4/admin/item/storage/info/{id}` — full storage info used by action modal pre-population.
- `GET    /api/v4/item/storage/{id}/parents` — backing chain for the row detail subtable.
- `GET    /api/v4/item/storage/{id}/storages_with_uuid` — UUID-duplicate files for the row detail subtable.
- `GET    /api/v4/items/storage/storages_with_uuid/status` — status options for the UUID-duplicates section.
- `GET    /api/v4/items/storage/storages_with_uuid[/{status}]` — UUID-duplicates table data.
- `GET    /api/v4/item/storage/{id}/find` — enqueue a find task for a single storage (row button and modal button).
- `GET    /api/v4/item/storage/{id}/has-derivatives` — derivative count; blocks Move / WinReg / Increase if > 1.
- `PUT    /api/v4/items/storage/{action}` — bulk action on a filtered set (body: `{ids: [...]}` ).
- `PUT    /api/v4/items/storage/{action}/{status}` — bulk action on all storages of a status.
- `POST   /api/v4/item/storage/priority/{priority}` — create a new unattached storage.
- `POST   /api/v4/item/storage/priority/{priority}` (with `parent`) — create a derived storage.
- `PUT    /api/v4/item/storage/{id}/priority/{priority}/increase/{increment}` — increase disk size.
- `PUT    /api/v4/item/storage/{id}/sparsify/priority/{priority}` — sparsify disk.
- `PUT    /api/v4/item/storage/{id}/disconnect/priority/{priority}` — disconnect from backing chain.
- `PUT    /api/v4/item/storage/{id}/move/by-path` — move (mv) within the same pool to a new path (Move default).
- `PUT    /api/v4/item/storage/{id}/rsync/to-path` — move via rsync within the same pool to a new path.
- `PUT    /api/v4/item/storage/{id}/rsync/to-storage-pool` — move via rsync to a different pool.
- `PUT    /api/v4/item/storage/{id}/virt-win-reg/priority/{priority}` — apply Windows registry patch.
- `PUT    /api/v4/storage-pool/by-path` — resolve pool from a directory path (used by Move and Add Disk).
- `GET    /api/v4/storage-pools` — list all pools for the Move destination selector.
- `GET    /api/v4/admin/item/user/appliedquota/{user_id}` — user quota ceiling for the Increase modal.
- `DELETE /api/v4/item/storage/{id}` — delete a storage (from modal Delete button or orphan button).
- `DELETE /scheduler/{id}.stg_action` — delete the scheduler job for a storage.
- `GET    /api/v4/task/{id}` — task info (opened from the task-info button).
- `PUT    /api/v4/admin/task/{id}/retry` — retry a failed task.
- `DELETE /api/v4/item/storage/{id}/path` — delete one of the UUID-duplicate physical files.
- `PUT    /api/v4/item/storage/{id}/path` — set the active path for a storage (UUID-dup fix).

## Relevant database state

- `storage` table: seed has `storage-template-test-001` in status `ready`.
- `storage_pool` table: `storage_pool.json` seed defines the pool.
- SocketIO `storage` event: real-time row moves between tables as status changes.
  (Not covered by these tests — SocketIO is mocked/skipped in the e2e env.)

## Required seeds

`testing/db/data/storage.json` provides three `ready` seeds: Seed A
(`storage-template-test-001`, non-UUID id), Seed B
(`e2e00000-0000-0000-0000-000000000001`, used by all modal action tests) and
Seed C (`e2e00000-0000-0000-0000-000000000002`, the disposable row S23 deletes).
Seed B and Seed C share the same shape — UUID-format id, `directory_path`
`/isard/templates`, owner `local-default-admin-admin`:

```json
{
    "id": "e2e00000-0000-0000-0000-000000000001",
    "type": "qcow2",
    "directory_path": "/isard/templates",
    "parent": null,
    "perms": ["r", "w"],
    "status": "ready",
    "status_logs": [],
    "storages_with_uuid": [],
    "user_id": "local-default-admin-admin",
    "task": null
}
```

## Cases not covered (future)

- SocketIO `storage` event moving a row from Ready → Maintenance → Other status in real time.
- Sparsify / Move / Increase / Disconnect full round-trips (require hypervisor).
- Convert action: the `.btn-convert` handler exists in `storage.js` but no HTML template renders
  a `.btn-convert` trigger — `detailButtons()` only generates `.btn-storage-actions`. Convert is
  dead code and untestable via the UI.
- Delete orphan storage (requires a seeded orphan storage).
- Manager role view (read-only, no action buttons visible).
- `searchStorageId` URL query parameter pre-filters the Ready table on load.
- `btn-task-info` and `btn-retry-task`: single-step flows (one click → one API call → PNotify) with
  no multi-component interaction. Not worth the seed overhead (Seed C + tasks table entry). The
  presence/absence of these buttons is already verified by S1b.
