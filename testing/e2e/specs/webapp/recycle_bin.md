# Recycle bin management in webapp

Human-readable functional specification of the **recycle bin** admin
screen: bulk and individual **delete / restore**, the **automatic
delete after** (cutoff time) selector, the **main entries datatable**
(search, filters, columns, details), and the **other status**
datatable. It also specifies the **recycle bin config** page (Part 2).
Serves as the contract for **two separate** E2E test files:
`tests/webapp/recycle_bin.spec.js` (the Domains page — Part 1) and
`tests/webapp/recycle_bin_config.spec.js` (the Config page — Part 2).

> This file is a **spec only**. The matching `recycle_bin.spec.js`
> (Part 1) and `recycle_bin_config.spec.js` (Part 2) are future work;
> implement them from this document with the
> `isard-e2e-tests-from-markdown` skill. **Keep the two test files
> separate.** Scenarios that hit a documented bug or that can't be set
> up cleanly are marked `test.skip` + `// TODO` so the eventual suites
> stay green.

## Scope

- **Component**: legacy administration panel (`isard-admin`), Jinja
  page `recyclebin_domains.html` driven by
  `static/admin/js/recyclebin_domains.js`.
- **Screen**: **Recycle bin → Domains**, reached at
  `/isard-admin/admin/domains/render/Recyclebin/Domains`.
  Two stacked panels:
  - **Domains pending to be deleted** — the *main* datatable
    `#recyclebin_domains`, listing `recycled` entries (the only status
    that exposes checkboxes and per-row action buttons).
  - **Domains in other status** — the *secondary* datatable
    `#recyclebin_domains_other`, loaded on demand from the `#status`
    dropdown.
- **Roles**: `admin` and `manager` (the page template is gated by
  `{% if current_user.role in ['admin', 'manager'] %}`,
  [recyclebin_domains.html:6](../../../../webapp/webapp/webapp/templates/admin/pages/recyclebin_domains.html#L6); the Flask
  route is `@isAdminManager`,
  [AdminViews.py:269-287](../../../../webapp/webapp/webapp/views/AdminViews.py#L269-L287)).
  Managers see only their **own category**'s entries; admins see all.
- **Actions covered**: bulk delete, bulk restore, "no selection"
  guard, automatic-delete cutoff, individual delete, individual
  restore, search, column rendering, item-type filter, row details,
  admin-only ID column reveal, other-status table, and the
  restore-dependency limitation.
- **Part 2 — config page**: the **recycle bin config** page
  (`recyclebin_config.html` / `recycle_bin_config.js`, **admin only**)
  is specified separately in **Part 2** at the end of this file and is
  implemented in its **own** test file `recycle_bin_config.spec.js`.
  Bugs #3/#4/#5 live on that page.
- **Out of scope (both parts)**: the deep side effects of each config
  toggle / action (what the scheduler/engine actually does afterwards)
  — the specs assert the API + UI contract, not the downstream
  processing.

## Non‑negotiable conventions

1. **Always use the SDK; never hardcode admin routes.** All setup,
   verification and cleanup go through the generated apiv4 client
   (`src/gen/apiv4/sdk.gen`), exactly like `gpus.spec.js` does (e.g.
   `getReservableItems`, `adminTableList`). The webapp's own XHRs are
   only *observed* via `page.waitForResponse`, never reproduced by
   hand-built URLs.
2. **Locate rows by `tr[id]` — caveat to verify at implementation.**
   The main table sets `"rowId": "id"`
   ([recyclebin_domains.js:256](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L256)),
   so each row *should* be reachable as
   `#recyclebin_domains tbody tr[id="<entry_id>"]`, the entry id taken
   from the SDK (`getRecycleBinAdminEntries`) — the same pattern
   `gpus.spec.js` uses (`#table-gpus tbody tr[id="${gpuId}"]`). The
   table uses `deferRender`, so expand the page length first
   (`$('#recyclebin_domains').DataTable().page.len(-1).draw(false)`, as
   gpus' `gotoHypervisors` does) or off‑page rows won't be in the DOM.
   The main table has **no item‑name column**, so there is no
   text‑based fallback.
   - ⚠️ **Verify at implementation.** Experience on other admin specs
     is that **if a column is not visible, Playwright cannot see/use
     it**, and the only way to expose the **Id** column is the
     **Ctrl+Alt+I** shortcut, which is **admin‑only**
     ([isard.js:932-945](../../../../webapp/webapp/webapp/static/isard.js#L932-L945)).
     If `tr[id]` turns out to be insufficient for this table, the test
     must reveal the Id column first (admin) before locating rows — and
     **managers cannot**. So manager UI row‑location may be infeasible;
     decide when writing the tests whether the affected `M*` UI steps
     drop to SDK‑level assertions or `test.skip` + TODO.
3. **Each test owns its data.** Create throwaway items via the SDK with
   a unique name (`e2e-rb-<workerIndex>-<timestamp>`), delete them to
   produce a recycle-bin entry, and clean up in `afterEach`
   (permanently purge any entry the test created via
   `bulkDeleteRecycleBin`). Never assert against pre-existing seed
   entries.
4. **Don't fix bugs here.** Where a documented bug blocks a flow, the
   scenario is `test.skip` with a `// TODO` — the spec/test must not
   work around or patch backend/JS bugs.

## Fixtures (from `fixtures/apiv4`)

| Fixture | Role | Use |
| --- | --- | --- |
| `authenticatedPage` / `apiv4Admin` | admin (`admin_e2e_NN`, category `default`) | admin scenarios |
| `managerE2EPage` / `apiv4Manager` | manager (`manager_e2e_01`, category `default`) | manager scenarios |

> `managerE2EPage` logs in but does **not** bridge the legacy admin
> Flask session the way `authenticatedContext` does
> (`bridgeAdminSession`,
> [client.js:289-299](../../../../testing/e2e/fixtures/apiv4/client.js)). The manager
> scenarios below assume an equivalent bridged manager page is
> available; if it is not yet wired up, that wiring is a prerequisite
> for the `M*` tests (flag at implementation, `test.skip` + TODO
> otherwise).

## The "recycled entry" precondition

An item only lands in the recycle bin as status **`recycled`** (the
status the main table shows, with checkboxes + action buttons) when the
owner's effective cutoff time is **not "Immediately"**. The decision
reads the owner's category `recycle_bin_cutoff_time`, falling back to
the system value
([recycle_bin.py:996-1025](../../../../component/_common/src/isardvdi_common/helpers/recycle_bin.py#L996-L1025)).
The seeded `default` category ships `recycle_bin_cutoff_time: null`
([categories.json](../../../../testing/db/data/categories.json)), i.e. it falls back to the
system cutoff, which in the dev/CI DB is non‑immediate. So:

- Deleting an **admin/manager‑owned** item created in `default` →
  `recycled` entry (the happy path for setup). ✅
- If a test needs to be certain, it may read/raise the cutoff via the
  SDK first (see A5/M3) — **but** see the parallel‑safety warning there.

Status lifecycle (enum
[recycle_bin.py:23-28](../../../../component/_common/src/isardvdi_common/schemas/recycle_bin.py)):
`recycled` → (restore) `restored`; `recycled` → (delete) `queued` →
`deleting` → `deleted`. Under engine load a delete may sit in `queued`
/ `deleting` for a while, and a restore may transiently show `queued`
— **assertions must tolerate the intermediate statuses** and poll the
SDK rather than expect an instant terminal state.

## Common data

| Field | Sample value | Notes |
| --- | --- | --- |
| Throwaway desktop/template name | `e2e-rb-<workerIndex>-<timestamp>` | unique per worker; tracked in `testInfo.annotations` for `afterEach` cleanup |
| Cutoff value chosen in A5/M3 | a **non‑zero** option (e.g. `1` hour) | never "Immediately" mid‑suite (see A5) |

---

## Admin scenarios

### A1 — *page loads and the main table renders recycled entries*

#### Given

1. The administrator is authenticated in the webapp.
2. At least one `recycled` entry exists — the test creates one via SDK:
   `createDesktop`, then deletes it so it enters the recycle bin; the
   entry id is tracked in `testInfo.annotations` for cleanup.

#### When

1. Navigate to `/isard-admin/admin/domains/render/Recyclebin/Domains`.
2. Wait for the `#recyclebin_domains` DataTable wrapper to render and
   for at least one `tbody tr` to appear.

#### Then

1. The row `#recyclebin_domains tbody tr[id="<entry_id>"]` is present
   in the table.
2. The page console has **no** `data.filter is not a function` error
   (**Bug #2** gate).
3. `GET /api/v4/items/recycle-bin/admin-entries` → `2XX`; the response
   body is a JSON **array** of entries (SDK `getRecycleBinAdminEntries`).

> **Notes**: this is the load-sanity gate for the whole file. If
> **Bug #2** reproduces on the target branch (page errors / table
> doesn't render), every scenario here is blocked — mark the whole
> `describe` as `test.skip` + TODO referencing Bug #2.

---

### A2 — *global "Delete permanently" on selected rows*

#### Given

1. The administrator is authenticated.
2. **N = 2** recycled entries exist, created by the test via SDK (two
   throwaway desktops deleted); their entry ids are collected.

#### When

1. For each entry, click `tr[id="<id>"] .select-checkbox input` to
   select the row (sets `.active` via `toggleRow`,
   [isard.js:401-410](../../../../webapp/webapp/webapp/static/isard.js#L401-L410)).
2. Select **"Delete permanently"** in `#mactions`.
3. A confirmation PNotify *"Are you sure you want to delete \<N\>
   recycle bin entries?"* appears
   ([recyclebin_domains.js:597](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L597)).
4. Assert the rendered count equals `N`.
5. Click **Ok** (`.ui-pnotify-action-button` with text `ok`).

#### Then

1. A success PNotify *"Action queued: delete …"* appears.
2. The selected rows disappear from `#recyclebin_domains` (the table
   reloads; non-`recycled` rows have no checkboxes/buttons).
3. `PUT /api/v4/items/recycle-bin/delete` with body
   `{ "recycle_bin_ids": [<ids>] }` → `2XX` (SDK `bulkDeleteRecycleBin`).
4. SDK poll: each entry's status becomes `queued`/`deleting`/`deleted`
   (`getRecycleBinAdminEntries?status=deleted`); intermediate states
   are tolerated.
5. Selecting the matching status in `#status` loads
   `#recyclebin_domains_other` with the entries present (see **A14**).

---

### A3 — *global "Restore disk and domain" on selected rows*

#### Given

1. The administrator is authenticated.
2. **N = 2** recycled entries from throwaway **desktops** exist (so
   each entry carries a `desktops` list of restorable ids); their entry
   ids and `desktops[].id` are collected via SDK.

#### When

1. Select the N rows as in **A2**.
2. Choose **"Restore disk and domain"** in `#mactions`.
3. Assert the confirmation PNotify count == N.
4. Click **Ok**.

#### Then

1. `PUT /api/v4/items/recycle-bin/restore` with body
   `{ "recycle_bin_ids": [...] }` → `2XX` (SDK `bulkRestoreRecycleBin`).
2. A success PNotify appears; the selected rows leave the main table.
3. In `#status`, the entries appear under **`restored`** (tolerate
   intermediate `queued` status).
4. SDK cross-check: poll that the `desktops[].id` values recorded
   before restore exist again in the live domains table — via
   `adminTableList({ table: 'domains', body: { id } })` or `getDesktop`.
   Tolerate `queued`; use a timeout-based poll rather than a single read.

---

### A4 — *global action with nothing selected → guard PNotify*

#### Given

1. The administrator is authenticated and on the Recyclebin/Domains page.
2. No rows are selected (none `.active`).

#### When

1. Select **"Delete permanently"** (or **"Restore …"**) in `#mactions`.

#### Then

1. A warning PNotify **"Please select items to delete"** appears
   ([recyclebin_domains.js:652-666](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L652-L666));
   `#mactions` resets to `none`.
2. **No** `PUT /api/v4/items/recycle-bin/{delete,restore}` request is
   fired (assert via a request listener, as `gpus.spec.js` does for the
   no-profile case).

---

### A5 — *automatic delete after (system cutoff) selector*

> **⚠ Parallel-safety (must-read)**: the system cutoff is **global**
> and influences whether every other test's deletions recycle or go
> straight to `deleted`. **Never** set it to "Immediately" while the
> suite runs; always pick a non-zero value; always restore it; and run
> this scenario **serially** (`test.describe.serial` or a worker guard)
> so it can't race the `recycled`-entry preconditions of A1–A14.

#### Given

1. The administrator is authenticated.
2. The current system cutoff value is read and saved via SDK
   `getSystemCutoffTime`
   (`GET /api/v4/item/recycle-bin/system/cutoff-time`).

#### When

1. On the Recyclebin/Domains page, assert `#maxtime` has the expected
   options (Immediately, 1 h, 6 h, … 1 year).
2. Choose a **non-zero** value (e.g. `1` hour).
3. A confirmation PNotify appears
   ([recyclebin_domains.js:788-832](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L788-L832));
   click **Ok**.
4. Reload the page.

#### Then

1. `PUT /api/v4/item/recycle-bin/system/cutoff-time` with body
   `{ "recycle_bin_cuttoff_time": <int> }` (note the apiv3 double-t
   spelling, `RecycleBinUpdateCutoffTimeRequest`) → `2XX` (SDK
   `updateSystemCutoffTime`).
2. After reload, `#maxtime` shows the chosen value
   (`selectAutomaticDelete()` sets it from the GET).
3. **Cleanup**: restore the original system cutoff via
   `updateSystemCutoffTime` in `afterEach`.

> **Role split (confirmed in code)**: **admin** writes the *global
> system* cutoff (`category_id = None`); a **manager** writes their own
> category's cutoff
> ([recycle_bin.py:426-461](../../../../component/apiv4/src/api/routes/recycle_bin.py#L426-L461)).
> The manager variant is **M3**.
> **Bug note**: safe from **Bug #1** because the admin reads the
> *system* cutoff, not a per-category one.

---

### A6 — *individual delete (red‑cross button)*

#### Given

1. The administrator is authenticated.
2. One recycled entry from a throwaway desktop exists; its id is known.

#### When

1. On `tr[id="<id>"]`, click the per-row **delete** button
   `button#btn-delete`.
2. A confirmation PNotify *"Do you really want to permanently delete the
   bin `<id>`?"* appears
   ([recyclebin_domains.js:430-457](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L430-L457)).
3. Click **Ok**.

#### Then

1. `DELETE /api/v4/item/recycle-bin/<id>` → `202 Accepted` (SDK
   `deleteRecycleBinEntry`).
2. The row leaves the main table.
3. SDK poll shows the entry under `queued`/`deleting`/`deleted`.
4. Selecting `deleted` in the `#status` dropdown shows the entry (see
   **A14**).

---

### A7 — *individual restore (undo button)*

#### Given

1. The administrator is authenticated.
2. One recycled entry from a throwaway **desktop** exists; its id and
   `desktops[].id` are known from `getRecycleBin(entry_id)`.

#### When

1. On `tr[id="<id>"]`, click `button#btn-restore`.
2. The confirmation PNotify lists counts (*"\<n\> desktops … \<n\>
   disks"*,
   [recyclebin_domains.js:459-505](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L459-L505)).
3. Click **Ok**.

#### Then

1. `PUT /api/v4/item/recycle-bin/<id>/restore` → `200` (SDK
   `restoreRecycleBin`).
2. A *"Restored …"* success PNotify appears; the row leaves the main
   table.
3. The entry shows under `restored` status in `#status` (tolerate
   `queued`).
4. SDK cross-check (poll): the entry's `desktops[].id` exist again in
   `domains` (as **A3**).

---

### A8 — *main datatable search*

#### Given

1. The administrator is authenticated.
2. At least one recycled entry exists whose agent/owner/item_type cell
   value is known from the SDK entry (`getRecycleBinAdminEntries`).

#### When

1. In the `#recyclebin_domains` table footer, type a distinctive value
   (e.g. the owner name) into a per-column **Filter** input
   ([recyclebin_domains.js:372-406](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L372-L406)).

#### Then

1. The table narrows to rows matching the term; the target `tr[id]`
   remains visible while non-matching rows are filtered out.
2. Clearing the input restores the full row set.

> **Note**: the footer renders per-column **Filter** inputs for every
> column except checkbox, actions, and item-type.

---

### A9 — *all columns render the expected info*

#### Given

1. The administrator is authenticated.
2. One recycled entry exists with SDK fields known
   (`getRecycleBinAdminEntries` → the entry object).

#### When

1. Navigate to the Recyclebin/Domains page and locate
   `tr[id="<entry_id>"]`.
2. Read the cells of that row.

#### Then

Each column is non-empty and correctly formatted:

1. **Deleted** = `moment.unix(accessed).fromNow()` (a relative time
   string).
2. **Status** = `recycled`.
3. **Agent name** = `agent_name`; **Agent type** = `agent_type`.
4. **Owner name** = `owner_name` (or italic *(deleted)* placeholder
   when null,
   [recyclebin_domains.js:298-300](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L298-L300)).
5. **Item type** = `item_type` (e.g. `desktop`).
6. **Deleted desktops / templates / deployments / storages** counts
   equal the SDK entry's `desktops`/`templates`/`deployments`/`storages`
   counts.
7. **Last modification** = `moment.unix(last.time).fromNow()`.

---

### A10 — *item‑type column filter dropdown*

#### Given

1. The administrator is authenticated.
2. At least one `desktop`-type recycled entry exists (and ideally one
   of another type).

#### When

1. In the **Item type** footer cell — a `<select>` with options
   Desktop/Template/Deployment/User/Group/Category
   ([recyclebin_domains.js:386-402](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L386-L402))
   — select **Desktop**.

#### Then

1. Only `item_type = desktop` rows remain; the created desktop entry
   stays visible while non-desktop entries are hidden.
2. Resetting to the blank option restores all rows.

---

### A11 — *open details — basic (desktop entry)*

#### Given

1. The administrator is authenticated.
2. One recycled entry from a throwaway **desktop** exists (so it has
   ≥1 desktop and ≥1 storage; SDK-/UI-created desktops auto-attach
   storage); its id is known.

#### When

1. Click `tr[id="<id>"] td.details-control button#btn-details` to
   expand the row.
2. The detail panel (`recyclebin_domains_detail.html`) renders 7
   sub-tables: Desktops, Templates, Storages, Deployments, Users,
   Groups, Categories.

#### Then

1. `GET /api/v4/item/recycle-bin/<id>` → `2XX` (SDK `getRecycleBin`);
   the body has the per-section arrays.
2. The **Desktops** sub-table shows the desktop row (its `id`/`name`).
3. The **Storages** sub-table shows ≥1 disk.
4. Each panel's `.quantity` header reads `(<n> items)`
   ([recyclebin_domains.js:537-548](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L537-L548)).
5. Main-table `Deleted desktops`/`… storages` column values == detail
   sub-table row counts == SDK `getRecycleBin().desktops.length` /
   `.storages.length`. Templates/deployments are `0` for a
   single-desktop entry.

---

### A12 — *open details — full (all 7 sections > 0 via category deletion)* — `test.skip`

> **E2E test status**: `test.skip` + `// TODO`. **Blocked by Bug #1**
> — a category created via `adminCreateCategory` does not ship
> `recycle_bin_cutoff_time`; deleting it makes the recycle flow call
> `get_user_recycle_bin_cutoff_time` which raises `ReqlNonExistenceError`
> → the deletion 500s and no entry is produced. Also fixture-heavy:
> needs `adminCreateCategory` → `adminCreateGroup` → `adminCreateUser`
> → `createTemplate` → `createDesktop` → `createDeployment`, all
> scoped to the new category, before `adminDeleteCategory`.
>
> **Unskip once Bug #1 is fixed** — the test must not pre-initialise
> the missing field or otherwise work around the bug (convention #4).

#### Given

1. A category with groups, users, templates, desktops, and deployments
   all scoped to it exists (created via SDK).

#### When

1. Delete the category via SDK `adminDeleteCategory`.
2. Wait for the recycle-bin entry to appear in
   `getRecycleBinAdminEntries`.
3. Navigate to the Recyclebin/Domains page and open the entry's details
   panel.

#### Then

1. The detail panel's Desktops, Templates, Deployments, Storages,
   Users, Groups, and Categories sub-tables all show `> 0` rows.
2. The main-table count columns match the detail sub-table row counts.

---

### A13 — *Ctrl+Alt+I reveals the hidden ID column (admin only)*

#### Given

1. The administrator is authenticated and the Recyclebin/Domains page
   has loaded with ≥1 row.
2. The **Id** column is defined `"visible": false`
   ([recyclebin_domains.js:361-365](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L361-L365)).

#### When

1. Press **Ctrl+Alt+I** on the page.

#### Then

1. `adminShowIdCol` toggles the last column's visibility for
   `data-role == 'admin'`
   ([isard.js:932-945](../../../../webapp/webapp/webapp/static/isard.js#L932-L945)).
2. The **Id** column is now visible and shows the entry id.
3. Pressing **Ctrl+Alt+I** again hides it.

---

### A14 — *"Domains in other status" dropdown + table*

#### Given

1. The administrator is authenticated.
2. At least one non-`recycled` entry exists — produced by **A2**
   (→ `deleted`/`queued`) or **A3** (→ `restored`); the page has been
   reloaded.

#### When

1. Observe the `#status` dropdown, populated from
   `GET /api/v4/items/recycle-bin/status` (`by_status`), **excluding**
   `recycled` and `deleting`
   ([recyclebin_domains.js:668-681](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L668-L681)).
   Options read like `deleted (N items)`.
2. Select the status that was produced in the precondition.

#### Then

1. `GET /api/v4/items/recycle-bin/admin-entries?status=<status>` →
   `2XX` (SDK `getRecycleBinAdminEntries({ query: { status } })`).
2. `#recyclebin_domains_other` loads and contains the entry at
   `tr[id="<id>"]`.
3. Rows in this table have **no** action buttons or checkboxes — only
   the details expander.

---

### A15 — *other‑status table search & item‑type filter*

#### Given

1. The administrator is authenticated.
2. `#recyclebin_domains_other` is loaded with ≥1 entry (after **A14**).

#### When

1. Type a distinctive value into a footer filter input of
   `#recyclebin_domains_other`.
2. Separately, select a value in the item-type `<select>` footer filter.

#### Then

1. The text filter narrows rows to matches; clearing it restores the
   full set.
2. The item-type filter shows only rows of the selected type; resetting
   to blank restores all rows.
3. Both filters work identically to **A8** and **A10** but operate on
   `#recyclebin_domains_other`.

---

### R1 — *restore limitation: orphaned parent template blocks restore*

> **Note**: viable but depends on an asynchronous template purge
> completing before the restore attempt. If that timing proves flaky at
> implementation, fall back to `test.skip` + `// TODO` explaining the
> timing dependency. Do **not** loosen the 412 assertion.

#### Given

1. The administrator is authenticated (admin-owned resources in
   `default` — **Bug #1** does not apply).
2. `createTemplate` → template `T`.
3. `createDesktop` from `T` → desktop `D`.
4. Delete `D` → recycled entry `E_D` (`item_type = desktop`; its
   `parents` reference `T`).
5. Delete `T` → recycled entry `E_T` (`item_type = template`).
6. **Permanently** delete `E_T` via SDK (`deleteRecycleBinEntry(E_T)`
   or bulk) and **poll until `T` is actually gone** from `domains`
   (`adminTableList({table:'domains', body:{id:T}})` returns nothing)
   — the purge is asynchronous (`queued` → `deleted`).

#### When

1. On `tr[id="E_D"]`, click `button#btn-restore`.
2. Confirm **Ok** in the confirmation PNotify.

#### Then

1. `PUT /api/v4/item/recycle-bin/E_D/restore` → **non-2XX**, expected
   **412** with description code `parent_template_not_found`
   ([recycle_bin.py check_can_restore / validate_parents](../../../../component/_common/src/isardvdi_common/helpers/recycle_bin.py)).
2. An **ERROR** PNotify *"ERROR restoring desktop …"* appears with the
   API description.
3. `E_D` stays in the main table; SDK confirms the desktop was **not**
   recreated.

---

## Manager scenarios

> The recycle bin admin page is reachable by managers; the API scopes
> their view to their own category
> (`get_recycle_bin_admin_entries`,
> [recycle_bin.py:519-527](../../../../component/apiv4/src/api/routes/recycle_bin.py#L519-L527)).
> `manager_e2e_01` is in the seeded `default` category (has the cutoff
> field), so **Bug #1 does not bite the manager flows below**.
>
> **Row location (verify — see convention #2):** every `M*` UI
> scenario must locate the manager's entry by `tr[id]`. If that proves
> insufficient and the hidden **Id** column is needed, managers
> **cannot** reveal it (Ctrl+Alt+I is admin‑only), so those UI steps
> may have to fall back to SDK‑level assertions or `test.skip` + TODO.
> Settle this once, at implementation time.

### M1 — *manager access + category scoping*

#### Given

1. The manager (`manager_e2e_01`, category `default`) is authenticated
   with a bridged admin session (see **Fixtures**).
2. A recycled entry exists created and deleted by the manager (throwaway
   desktop).
3. A separate entry created by the **admin** in a *different* category
   also exists (to verify it does not appear for the manager).

#### When

1. Navigate to `/isard-admin/admin/domains/render/Recyclebin/Domains`
   as manager.

#### Then

1. The page renders for the manager.
2. `GET /api/v4/items/recycle-bin/admin-entries` as manager → `2XX`;
   every returned entry belongs to the manager's category.
3. The admin entry from a different category does **not** appear in the
   manager's list (SDK cross-check).

---

### M2 — *manager bulk + individual delete / restore (own category)*

#### Given

1. The manager is authenticated.
2. One or two recycled entries from throwaway **desktops** owned by the
   manager exist.

#### When

1. Perform the same flows as **A2**, **A3**, **A6**, and **A7** on the
   manager page, against the manager's own entries.

#### Then

1. All assertions from **A2/A3/A6/A7** hold: correct PNotify counts,
   `2XX` on bulk/individual delete/restore endpoints, rows leave the
   table, and the SDK restore cross-check confirms the desktops came
   back.

---

### M3 — *manager automatic delete after (category‑scoped)*

> **E2E test status**: normal test. **Bug #7 is FIXED** —
> `GET /api/v4/item/recycle-bin/system/cutoff-time` now returns an int
> for the manager role (previously it returned a `{category,system}`
> dict that failed `RecycleBinSystemCutoffTimeResponse` validation →
> 500). The category cutoff persists and the UI reload check passes.

> **⚠ Parallel-safety**: this mutates the **shared `default` category**
> cutoff; save and restore the original and run serially with **A5**,
> since it can flip `default`-owned deletions between `recycled` and
> `deleted`.

#### Given

1. The manager is authenticated.
2. The current category cutoff is read and saved via SDK.

#### When

1. On `#maxtime`, choose a non-zero value (options trimmed to ≤ the
   system maximum,
   [recyclebin_domains.js:834-852](../../../../webapp/webapp/webapp/static/admin/js/recyclebin_domains.js#L834-L852)).
2. Confirm the PNotify (category-variant text).
3. Reload the page.

#### Then

1. `PUT /api/v4/item/recycle-bin/system/cutoff-time` → `2XX` (writes
   the manager's **category** cutoff).
2. After reload, `#maxtime` reflects the saved value.
3. **Cleanup**: restore the original category cutoff via SDK in
   `afterEach`.

> **Bug note**: safe from **Bug #1** because `default` has the
> `recycle_bin_cutoff_time` field.

---

### M4 — *manager does NOT get the Ctrl+Alt+I ID column*

#### Given

1. The manager is authenticated and the Recyclebin/Domains page has
   loaded with ≥1 row.

#### When

1. Press **Ctrl+Alt+I** on the page.

#### Then

1. The **Id** column **stays hidden** — the keydown listener is only
   registered for `data-role == 'admin'`
   ([isard.js:932-945](../../../../webapp/webapp/webapp/static/isard.js#L932-L945)).
2. The Id column header/cell is not visible after the shortcut (negative
   assertion).

---

### M5 — *manager details‑table coverage — NOT automated (documented)*

> **Decision**: the full details flow (A11/A12 equivalents) is
> intentionally not covered for managers:
>
> - Managers **cannot delete categories** (`adminDeleteCategory` is on
>   `admin_router`,
>   [users.py:1483-1511](../../../../component/apiv4/src/api/routes/admin/users.py#L1483-L1511)),
>   so the rich `item_type = category` entry cannot be produced as a
>   manager.
> - A group-deletion entry has fewer populated sections.
> - **Row location is uncertain for managers** (convention #2): if
>   Playwright can't use the hidden **Id** column and managers can't
>   reveal it, the entry can't be pinned down in the manager UI.
>
> **To verify at implementation**: if `tr[id]` does work without the
> visible column, a manager basic-details test (an A11 equivalent on a
> manager `adminDeleteGroup` or own-desktop entry) becomes feasible and
> could be added; if not, manager details stay blocked. This is the
> same `tr[id]` question as convention #2 — settle it there.

---

## Cleanup (afterEach)

1. Recover throwaway item names/ids and any recycle‑bin entry ids from
   `testInfo.annotations`.
2. Permanently purge recycle‑bin entries the test created
   (`bulkDeleteRecycleBin`), and delete any leftover live items
   (`deleteDesktop` / `adminTemplateDelete` / `adminDeleteCategory` /
   `adminDeleteGroup`) via the SDK.
3. Restore any cutoff value mutated by A5/M3 to its original.
4. Silence cleanup errors so they don't mask the real failure.

## Expected results — coverage summary

| ID | Role | Covered? | Key checks |
| --- | --- | --- | --- |
| A1 | admin | ✅ | page loads, main table renders, no `data.filter` error (Bug #2 gate) |
| A2 | admin | ✅ | bulk delete: PNotify count==N, `PUT …/delete` 2XX, rows leave, status→deleted/queued |
| A3 | admin | ✅ | bulk restore: count==N, `PUT …/restore` 2XX, status→restored, **SDK desktops back** |
| A4 | admin | ✅ | no selection → "Please select items" PNotify, no PUT |
| A5 | admin | ✅ | cutoff options, `PUT system/cutoff-time` 2XX, value persists; serial + restore |
| A6 | admin | ✅ | individual delete `DELETE …/{id}` 202, row leaves |
| A7 | admin | ✅ | individual restore `PUT …/{id}/restore` 200, **SDK desktops back** |
| A8 | admin | ✅ | datatable footer search narrows rows |
| A9 | admin | ✅ | all columns render; count columns match SDK entry |
| A10 | admin | ✅ | item‑type `<select>` filter works |
| A11 | admin | ✅ | details modal: desktops+storages sub‑tables, counts correspond |
| A12 | admin | ⏭ `skip` | full all‑sections details via category deletion — **blocked by Bug #1** + heavy fixture |
| A13 | admin | ✅ | Ctrl+Alt+I reveals hidden Id column (admin only) |
| A14 | admin | ✅ | `#status` populated from `…/status`, other table loads filtered |
| A15 | admin | ✅ | other‑status table search/filter |
| R1 | admin | ⏭ `skip` | orphaned‑template restore — async template‑purge timing flaky; **skip + TODO** |
| M1 | manager | ✅ | manager access; entries scoped to own category |
| M2 | manager | ✅ | manager delete/restore mirror A2/A3/A6/A7 on own entries |
| M3 | manager | ✅ | **Bug #7 FIXED** — `GET …/system/cutoff-time` now returns an int for managers; `#maxtime` writes the category cutoff, PUT 2XX + PNotify, persists on reload |
| M4 | manager | ✅ | Ctrl+Alt+I does **not** reveal Id (negative) |
| M5 | manager | 🚫 / verify | details left to admin; manager UI row‑location depends on the hidden‑Id‑column question (convention #2) — settle at implementation |

## APIs touched by the flows (reference)

All via the generated SDK (`src/gen/apiv4/sdk.gen`) — **never** as
hardcoded URLs:

- `GET  /api/v4/items/recycle-bin/admin-entries[?status=]` — list
  entries (admin = all, manager = own category). SDK
  `getRecycleBinAdminEntries`. Returns a JSON **array** of
  `RecycleBinEntry`.
- `GET  /api/v4/item/recycle-bin/{id}` — entry detail with per-section
  arrays. SDK `getRecycleBin` → `RecycleBinResponse`.
- `DELETE /api/v4/item/recycle-bin/{id}` — individual permanent delete.
  SDK `deleteRecycleBinEntry` → **202** `DeleteResponse`.
- `PUT  /api/v4/item/recycle-bin/{id}/restore` — individual restore.
  SDK `restoreRecycleBin` → **200** `SimpleResponse(id=…)`.
- `PUT  /api/v4/items/recycle-bin/delete` — bulk delete; body
  `{recycle_bin_ids:[…]}`. SDK `bulkDeleteRecycleBin`.
- `PUT  /api/v4/items/recycle-bin/restore` — bulk restore; same body.
  SDK `bulkRestoreRecycleBin`.
- `GET  /api/v4/items/recycle-bin/status` — `{total, by_status}` used to
  populate the `#status` dropdown. SDK `getRecycleBinStatus`.
- `GET/PUT /api/v4/item/recycle-bin/system/cutoff-time` — the
  "Automatic delete after" value (PUT body
  `{recycle_bin_cuttoff_time:<int>}`). SDK `getSystemCutoffTime` /
  `updateSystemCutoffTime`.
- **Setup/cleanup helpers**: `createDesktop`, `createTemplate`,
  `createDeployment`, `adminCreateCategory`/`adminDeleteCategory`,
  `adminCreateGroup`/`adminDeleteGroup`, `adminCreateUser`,
  `adminTableList`/`getDesktop` (restore verification).

## Relevant database state

- `recycle_bin` table — one row per entry; `status` drives the UI
  (`recycled` ⇒ main table with actions; `restored`/`deleted`/`queued`
  ⇒ other‑status table). Each entry holds `desktops`/`templates`/
  `deployments`/`storages`/`users`/`groups`/`categories` (counts in the
  list endpoint, arrays in the detail endpoint).
- `domains` table — restore re‑creates the desktop/template rows;
  permanent delete removes them (and their storage). The R1 restore
  guard reads `domains.get(parent)` to decide whether a desktop's
  parent template still exists.
- `categories.recycle_bin_cutoff_time` — per‑category cutoff (system
  fallback when `null`). Missing on API‑created categories → **Bug #1**.

## Known issues (do not fix here — spec only)

| # | Summary | In scope for this page? | Effect on these tests |
| --- | --- | --- | --- |
| 1 | `recycle_bin_cutoff_time` missing on API‑created categories → `ReqlNonExistenceError` in `get_user_recycle_bin_cutoff_time` ([recycle_bin.py:1015-1020](../../../../component/_common/src/isardvdi_common/helpers/recycle_bin.py#L1015-L1020)) | **Yes (partial)** | Blocks **A12** (deleting a freshly‑created category 500s). All other scenarios use seeded categories that have the field, so they are safe. **A12 = skip + TODO.** |
| 2 | `Uncaught TypeError: data.filter is not a function` on navigating to the recycle bin webapp | **Yes (gate)** | Caused by the entries endpoint returning an object while the DataTable uses `sAjaxDataProp:""` (expects a bare array). On this branch the route returns a **bare array** ([recycle_bin.py:519-543](../../../../component/apiv4/src/api/routes/recycle_bin.py#L519-L543)) and the reported stack line numbers don't match the current JS → **appears fixed here**. **A1 verifies it; if it reproduces on the target branch, `test.skip` the whole describe + TODO.** |
| 3 | `PUT /api/v4/item/recycle-bin/config/delete-action/{action}` → 400. The "Actions after deleting storage" radios send `delete`/`move`, but the apiv4 enum only accepts `recycle`/`permanent`, so **both** radios 400 | **Yes — Part 2** | **C2** is `test.skip` + TODO; unskip when the radio values match the enum. |
| 4 | Scheduler "send unused items to recycle bin" → 500 (`KeyError: 'users'`) | Part 2 (context) | Scheduler‑side; **not reachable from the config UI** (no "run now" button). Documented in Part 2; blocks no scenario. |
| 5 | `POST /api/v4/items/recycle-bin/unused-items` ("add unused items") → 500 | Part 2 (context) | Same root cause as #4; the config page only does rule **CRUD**, never calls this. Tests must **not** call `recycleBinAddUnusedItems`. |
| 6 | Edit modal for unused-item-timeout rules doesn't pre-fill all required selects (op / cutoff_time) when reopened via `#btn-edit` — clicking `#send` is blocked by Parsley validation | **Yes — Part 2** | **C6** is `test.skip` + TODO; unskip when the modal pre-fills all selects correctly. |
| 7 | `GET /api/v4/item/recycle-bin/system/cutoff-time` returns **500** for the **manager** role — the manager's category cutoff is correctly persisted in the DB but the reload fails | **Yes (M3, Part 1)** | **M3** is `test.skip` + TODO. Also, `set_default_delete` / `set_old_entries_max_time` / `set_old_entries_action` do not invalidate their 60-second TTL caches → SDK cross-checks on those helpers read stale values. Workaround in C1: use `adminTableList` on `config` to bypass the cache. |

## Cases not covered (future)

- **A12** full‑details category entry (unskip after Bug #1).
- **M5** manager details coverage (pending the convention #2 `tr[id]`
  vs hidden‑Id‑column question; managers can't reveal the column).

> The recycle bin **config** page is **Part 2** below (separate test
> file `recycle_bin_config.spec.js`).

---
---

## Part 2 — Recycle bin config

Specification of the **recycle bin config** page. **Implement this in a
separate test file `tests/webapp/recycle_bin_config.spec.js`** — do not
mix it with the Domains spec (`recycle_bin.spec.js`).

## Scope (Part 2)

- **Component**: legacy admin panel, Jinja page `recyclebin_config.html`
  driven by `static/admin/js/recycle_bin_config.js`.
- **Screen**: **Recycle bin → Config**, reached at
  `/isard-admin/admin/domains/render/Recyclebin/Config`
  ([AdminViews.py:269-287](../../../../webapp/webapp/webapp/views/AdminViews.py#L269-L287)).
- **Role**: **admin only** (per product). The Flask route is
  `@isAdminManager`, so the page *renders* for managers too, but the
  config write endpoints are admin‑scoped and the page is treated as
  admin‑only here. ⚠️ **Verify at implementation**: confirm how the
  admin‑only restriction is enforced (sidebar link hidden for managers
  vs the config XHRs returning 403). Run these tests with the **admin**
  fixture (`authenticatedPage` / `apiv4Admin`).
- **Areas covered**: *Enable recycle bin by default*, *Actions after
  deleting storage* (Bug #3 fixed), *Old entries* (max‑time +
  delete‑entry), and *Unused items rules* (CRUD + alloweds).

## Conventions (Part 2 — in addition to Part 1's)

- **SDK for setup/verify/cleanup.** Every config endpoint has an SDK
  function (see the Part 2 API reference); use them to read originals,
  verify persistence and restore state. Observe the webapp's own XHRs
  with `page.waitForResponse`.
- **Save & restore global config.** *Default delete*, *delete action*
  and *old‑entries* are **system‑wide** singletons; a test that flips
  them must read the original first and restore it in `afterEach`, and
  these scenarios should run **serially** so they don't race each other.
- **⚠️ iCheck plugin (verify at implementation).** The checkboxes and
  radios here are decorated by the **iCheck** plugin — the JS calls
  `.iCheck('check'/'uncheck'/'update')` and binds the
  `ifChecked`/`ifUnchecked` events, not the native `change`. iCheck
  hides the real `<input>` and renders an overlay, so a Playwright
  click on the native input may **not** fire the handler. Interact via
  the rendered iCheck control (its wrapper/`ins.iCheck-helper`) or the
  associated `<label>`; confirm the approach when writing the test.

## Part 2 scenarios

### C1 — *Enable recycle bin by default (checkbox)*

#### Given

1. The administrator is authenticated on the Recycle bin Config page.
2. The current value is read and saved via SDK
   `getRecycleBinDefaultDeleteConfig`
   (`GET /api/v4/item/recycle-bin/get-default-delete-config`); restore
   in `afterEach`.

#### When

1. Toggle `#default-delete-checkbox` via the iCheck control.
   `checkDefaultDelete` binds `ifChecked`→`toggleDefaultDelete(true)` /
   `ifUnchecked`→`toggleDefaultDelete(false)`
   ([recycle_bin_config.js:283-320](../../../../webapp/webapp/webapp/static/admin/js/recycle_bin_config.js#L283-L320)).

#### Then

1. `PUT /api/v4/item/recycle-bin/config/default-delete` with body
   `{ "rb_default": <bool> }` → `2XX` (SDK `setDefaultDelete`).
2. Success PNotify *"Send to recycle bin by default enabled/disabled"*
   appears.
3. Reload → the checkbox reflects the saved state (driven by the GET).
   Cross-check via the SDK.

> **Context (out of scope)**: with the box checked/unchecked, the user
> frontend `/desktops` delete modal's "send to recycle bin" checkbox
> defaults accordingly (only when the desktop has no tag id and cutoff ≠
> 0). That crosses into the Vue user frontend — future cross-check, not
> part of `recycle_bin_config.spec.js`.

---

### C2 — *Actions after deleting storage (radios)*

> **E2E test status**: normal test. **Bug #3 is FIXED.**
> The two radios — `#delete-action-radio` (`value="delete"`) and
> `#move-action-radio` (`value="move"`,
> [recyclebin_config.html:45-56](../../../../webapp/webapp/webapp/templates/admin/pages/recyclebin_config.html#L45-L56))
> — fire `PUT /api/v4/item/recycle-bin/config/delete-action/{value}`
> (`toggleDeleteAction`,
> [recycle_bin_config.js:322-371](../../../../webapp/webapp/webapp/static/admin/js/recycle_bin_config.js#L322-L371)).
> `DeleteActionEnum` now accepts **`move`** / **`delete`**, so the PUT
> returns **204**.
>
> Assertions: checking `#move-action-radio` → `2XX` + success PNotify
> *"Delete action set to move"*; persistence is cross-checked against the
> raw `config` table (`adminTableList`), **not** a reload — `get_delete_action`
> is wrapped in a 60s `TTLCache` that `set_delete_action` does not
> invalidate, so a reload within 60s reads the stale value.

---

### C3 — *Old entries: max‑time select*

#### Given

1. The administrator is authenticated on the Recycle bin Config page.
2. Current config read via SDK `getOldEntriesConfig`
   (`GET /api/v4/item/recycle-bin/old-entries/config` →
   `{action, max_time}`); `max_time` saved for `afterEach` restore.

#### When

1. Change `#maxtime` — options "5 minutes"=`0` … "2 years",
   "Never"=`null`
   ([recyclebin_config.html:73-90](../../../../webapp/webapp/webapp/templates/admin/pages/recyclebin_config.html#L73-L90)).

> **Note**: this is a **different** `#maxtime` from the one on the
> Domains page (which drives the cutoff — **A5**). Here it drives
> old-entries max-time.

#### Then

1. `PUT /api/v4/item/recycle-bin/old-entries/max-time/{h}` → `2XX`
   (SDK `setOldEntriesMaxTime`).
2. Success PNotify *"Updated time"* appears.
3. Reload → `#maxtime` shows the chosen value (`checkOldEntriesAction`).

---

### C4 — *Old entries: "Delete entry" checkbox*

#### Given

1. The administrator is authenticated on the Recycle bin Config page.
2. Current `action` read via `getOldEntriesConfig`; saved for `afterEach`
   restore.

#### When

1. Toggle `#delete-radio` (a **checkbox**, `name="archive-delete-action"`,
   `value="delete"`,
   [recyclebin_config.html:92-107](../../../../webapp/webapp/webapp/templates/admin/pages/recyclebin_config.html#L92-L107))
   via iCheck.
   - `ifChecked` → `toggleOldEntriesAction('delete')`.
   - `ifUnchecked` → `toggleOldEntriesAction('none')`.

#### Then

1. `PUT /api/v4/item/recycle-bin/old-entries/action/{action}` → `2XX`
   (SDK `setOldEntriesAction`).
2. `PUT /scheduler/recycle_bin/old_entries/{action}` → `2XX` (webapp→
   scheduler proxy, not apiv4 — observed via `waitForResponse`).
3. Success PNotify *"Updated scheduler"* (*"Old entries will be deleted
   after N hours"* / *"Old entries action disabled"*).
4. Reload → the checkbox reflects the saved action.

---

### C5 — *Unused items rules: table loads + Create*

#### Given

1. The administrator is authenticated on the Recycle bin Config page.
2. `#unused-desktops-table` has loaded via
   `GET /api/v4/items/recycle-bin/unused-item-timeout-rules`
   (`sAjaxDataProp: "rules"`,
   [recycle_bin_config.js:373-417](../../../../webapp/webapp/webapp/static/admin/js/recycle_bin_config.js#L373-L417));
   assert it renders without error (SDK `getAllUnusedItemTimeoutRules`
   for the baseline).

#### When

1. Click `.btn-add-unused-desktop-rule` → modal `#modalUnusedTime`.
2. Fill **name** (required, ≤50 chars), **description** (optional,
   ≤255), **op** (required — one of
   `send_unused_desktops_to_recycle_bin`,
   `send_unused_deployments_to_recycle_bin`,
   `send_unused_deployment_desktops_to_recycle_bin`), **priority**
   (required, number), **cutoff_time** (required select).
3. Click `#send`.

#### Then

1. `POST /api/v4/items/recycle-bin/unused-item-timeout-rules` → `2XX`
   (SDK `createUnusedItemTimeoutRule`).
2. Success PNotify *"Added"*; the datatable reloads.
3. SDK `getAllUnusedItemTimeoutRules` contains the new rule; its `id`
   is tracked for cleanup.

> **Negative validation**: with **name** (or **priority**/**op**/
> **cutoff_time**) empty, Parsley blocks `#send` and **no POST** is
> fired — the modal stays open and no request goes out (mirror
> `gpus.spec.js` S9/S10).

---

### C6 — *Unused items rules: Edit + Delete*

> **E2E test status (Edit)**: normal test. **Bug #6 is FIXED** — the
> edit modal now pre-fills the required selects. The `#cutoff_time`
> `<select>` offers `1..6,12` and the apiv4 enum accepts exactly those,
> so a stored value always has a matching option. The rule is created
> with `cutoff_time=6` (present in both the enum and the select).

#### Given

1. The administrator is authenticated.
2. A rule exists, created via SDK `createUnusedItemTimeoutRule`
   (independent of **C5**).

#### When (Delete — automatable)

1. Locate the rule row and click `#btn-delete`.
2. Confirm the PNotify (*"Are you sure you want to delete rule …?"*) →
   **Ok**.

#### Then (Delete)

1. `DELETE /api/v4/item/recycle-bin/unused-item-timeout-rule/{id}` →
   `2XX` (SDK `deleteUnusedItemTimeoutRule`).
2. PNotify *"Deleted"* appears; the row is removed from the table.
3. `getAllUnusedItemTimeoutRules` no longer contains the rule.

#### When (Edit)

1. Locate the rule row and click `#btn-edit`.
2. The modal should open pre-filled from
   `GET /api/v4/item/recycle-bin/unused-item-timeout-rule/{id}` (SDK
   `getUnusedItemTimeoutRule`), including **op** and **cutoff_time**.
3. Change name and priority; click `#send`.

#### Then (Edit)

1. `PUT /api/v4/item/recycle-bin/unused-item-timeout-rule/{id}` →
   `2XX` (SDK `updateUnusedItemTimeoutRule`).
2. PNotify *"Updated"*; the change is verified via the GET.

---

### C7 — *Unused items rules: alloweds*

#### Given

1. The administrator is authenticated.
2. A rule exists, created via SDK.

#### When

1. Click row `#btn-alloweds` → `modalAllowedsFormShow("unused_item_timeout",
   data)` (shared alloweds widget, `snippets/alloweds.js`).
2. The modal loads current alloweds from
   `GET /api/v4/item/allowed/table/unused_item_timeout` (SDK
   `allowedTable`).
3. Add an allowed (group/category/role/user via term search
   `GET /api/v4/items/alloweds/term/...`).
4. Save.

#### Then

1. `POST /api/v4/item/allowed/update/unused_item_timeout` → `2XX` (SDK
   `adminAllowedUpdate`).
2. Re-opening the alloweds modal (or `allowedTable`) confirms the added
   entry is present.

---

## Cleanup (Part 2 — afterEach)

1. Delete every rule the test created (SDK `deleteUnusedItemTimeoutRule`).
2. Restore *default delete*, *delete action* (if a fix unskips C2),
   *old‑entries* `max_time`/`action` to the values read at the start
   (SDK setters).
3. Silence cleanup errors.

## Part 2 — coverage summary

| ID | Covered? | Key checks |
| --- | --- | --- |
| C1 | ✅ | default‑delete checkbox → `config/default-delete` 2XX + PNotify; persists (cross-check via `adminTableList` on config, bypassing Bug #7 cache) |
| C2 | ✅ | **Bug #3 FIXED** — `DeleteActionEnum` now accepts `move`/`delete`; radio → `config/delete-action/{move}` 204 + PNotify; persists (cross-check via `adminTableList` on config, not the reload — `set_delete_action` does not invalidate the 60s cache) |
| C3 | ✅ | old‑entries max‑time → `old-entries/max-time/{h}` 2XX + PNotify; persists |
| C4 | ✅ | delete‑entry checkbox → `old-entries/action/{a}` + scheduler proxy 2XX + PNotify; persists |
| C5 | ✅ | rules table loads; create rule POST 2XX + SDK verify; Parsley blocks empty form |
| C6 | ✅ | **Bug #6 FIXED** — `#cutoff_time` `<select>` now offers `1..6,12` and the enum accepts exactly those; rule created with `cutoff_time=6`, modal pre-fills, edit (PUT) + delete (DELETE) run end to end |
| C7 | ✅ | alloweds `allowed/update/{table}` 2XX; persists |

## Part 2 — APIs touched (reference, all via SDK)

- `GET  /api/v4/item/recycle-bin/get-default-delete-config` —
  `getRecycleBinDefaultDeleteConfig`.
- `PUT  /api/v4/item/recycle-bin/config/default-delete` `{rb_default}` —
  `setDefaultDelete`.
- `GET  /api/v4/item/recycle-bin/config/delete-action` — `getDeleteAction`.
- `PUT  /api/v4/item/recycle-bin/config/delete-action/{action}` —
  `setDeleteAction` (**Bug #3 fixed** — enum accepts `delete`/`move`).
- `GET  /api/v4/item/recycle-bin/old-entries/config` — `getOldEntriesConfig`.
- `PUT  /api/v4/item/recycle-bin/old-entries/max-time/{max_time}` —
  `setOldEntriesMaxTime`.
- `PUT  /api/v4/item/recycle-bin/old-entries/action/{action}` —
  `setOldEntriesAction`; plus the webapp→scheduler proxy
  `PUT /scheduler/recycle_bin/old_entries/{action}` (not apiv4).
- `GET  /api/v4/items/recycle-bin/unused-item-timeout-rules` —
  `getAllUnusedItemTimeoutRules`.
- `GET/POST/PUT/DELETE /api/v4/item(s)/recycle-bin/unused-item-timeout-rule(s)[/{id}]`
  — `getUnusedItemTimeoutRule` / `createUnusedItemTimeoutRule` /
  `updateUnusedItemTimeoutRule` / `deleteUnusedItemTimeoutRule`.
- `GET  /api/v4/item/allowed/table/{table}` — `allowedTable`;
  `POST /api/v4/item/allowed/update/{table}` — `adminAllowedUpdate`;
  term search `GET /api/v4/items/alloweds/term/{table}`.

## Part 2 — known bug notes

### Fixed (2026-06-11) — tests converted from `test.skip` to normal assertions

- **Bug #3** (was blocking **C2**) — `DeleteActionEnum` now accepts
  `move`/`delete`, matching the radio values. C2 is a normal test.
- **Bug #6** (was blocking **C6**) — the edit modal `#cutoff_time`
  `<select>` now offers `1..6,12` and the apiv4 enum accepts exactly
  those, so a stored value always has a matching option. C6 is normal.
- **Bug #7** (was blocking **M3**) — `GET …/system/cutoff-time` now
  returns an int for managers (no longer a `{category,system}` dict that
  failed schema validation → 500). M3 is normal.

### Still open

- **Bugs #4 / #5** (`send/add unused items` → 500, `KeyError: 'users'`)
  are **scheduler‑side / processing** bugs. The config page exposes only
  rule **CRUD** and **no "run now" trigger**, so these scenarios never
  hit them. Tests must **not** call `recycleBinAddUnusedItems`
  (`POST /api/v4/items/recycle-bin/unused-items`) — that endpoint is the
  bug, not a test step.
