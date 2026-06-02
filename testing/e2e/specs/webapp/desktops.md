# Desktop management in webapp

Human-readable functional specification of the **table view**, **lifecycle**
(start / stop / retry / cancel), **CRUD** (edit, delete, template creation),
**bulk** (create, edit, mass actions), and **advanced** (owner change, share
link, forced/favourite hypervisor, server mode, info modal, storage) flows for
desktops in the legacy admin panel.
Serves as the contract for the E2E test `tests/webapp/desktops.spec.js`.

## Scope

- **Component**: administration panel.
- **Screen**: **Desktops** section at `/isard-admin/admin/domains/render/Desktops`.
- **Actions covered**:
  - View the full desktop list and verify seeded desktops are present.
  - Start a stopped desktop and observe the status transition.
  - Stop a running desktop (and force-stop one that is shutting down).
  - Retry a desktop stuck in Failed state.
  - Cancel a storage operation on a desktop in Maintenance state.
  - Edit a desktop's name, description, and hardware from the row-detail panel.
  - Delete a desktop via the row-detail panel (with PNotify confirmation).
  - Create a template from a desktop (with `enabled` toggle and `alloweds`).
  - Bulk-create desktops from a template.
  - Bulk-edit hardware on a set of desktops.
  - Apply a bulk action (delete) to a hand-picked selection of desktops.
  - Apply a bulk action to all filtered desktops (requires the `"I'm aware"` prompt).
  - Change the owner of a desktop.
  - Enable and disable the direct-viewer share link (jump URL / Viewer).
  - Set and clear the **forced** hypervisor (desktop only starts on that hyp).
  - Set and clear the **favourite** hypervisor (preferred, with failover).
  - Enable and disable server mode (with autostart option).
  - Open the Info modal and verify domain/owner/network details.
  - Open the storage modal, view attached disks, and increase disk size.
- **Out of scope**: booking flows, viewer connection itself (opening VNC/RDP
  session), VM console interaction, GPU profile management (covered in `gpus.md`).
- **Filters covered**: server-side indexed filter (`status` → S24), server-side
  name filter (`name` → S25), clear all filters (S26), reload without API call (S27).

## Common role and prerequisites

| Element | Expected value |
| --- | --- |
| Role | Administrator of the `default` category |
| Session | Logged in to the webapp (Flask admin session via JWT bridge) |
| Admin panel | Reachable at `/isard-admin/admin/domains/render/Desktops` |
| Desktop table | `#domains` DataTable has loaded (no spinner, at least one row) |

## Common data — seeded desktops

The test relies on desktops that exist in the seed DB. Their IDs and names
are defined as the `SEEDED` constant at the top of `tests/webapp/desktops.spec.js`
(some IDs overlap with `testing/e2e/fixtures/desktops.js`, but `s16` is only
in the spec file).

| Key | Name | Status | Notes |
| --- | --- | --- | --- |
| `test` | Desktop with storage | Stopped | Persistent, no GPU |
| `started` | Test started desktop | Started | Persistent, IP visible |
| `failed` | Failed desktop | Failed | Persistent, no GPU |
| `maintenance` | Test maintenance desktop | Maintenance | `current_action: increase` |
| `gpu` | Test desktop with GPU | Stopped | Needs booking, `NVIDIA-A16-2Q` |
| `s16` | Desktop S16 storage | Stopped | Dedicated to S16 only — isolated to avoid race conditions with S2's `PUT /start` under `fullyParallel` |

## Common data — dynamically created desktops

For scenarios that create new desktops the test generates a unique name:

| Field | Sample value | Notes |
| --- | --- | --- |
| Name | `e2e-desktop-<worker>-<timestamp>` | Per-worker, per-run unique |
| Description | `e2e desktop created at <ISO timestamp>` | Free text |
| Template | First available template in the dialog | Picked from the system list |

The name is stored in `testInfo.annotations` (type `'desktop-name'`) so that
`afterEach` can recover and delete the desktop even when assertions fail.

---

## Scenario 1 — *admin loads the desktops table and sees seeded desktops*

### Given

1. The administrator is authenticated in the webapp.
2. They navigate to `/isard-admin/admin/domains/render/Desktops`.

### When

1. The page finishes loading (`#domains_processing` disappears or
   `#domains tbody tr` count is at least 1).

### Then

1. The `#domains` DataTable is present and has at least one row.
2. The seeded desktop **"Desktop with storage"** is visible in the table.
3. The **Status** column of that row shows `Stopped`.
4. The row's action column renders a **Start** button (`#btn-play`).
5. `POST /api/v4/admin/items/domains` (body `{ kind: "desktop" }`) responds
   with status `< 400`.

---

## Scenario 2 — *admin starts a stopped desktop*

### Given

1. The seeded desktop `test` ("Desktop with storage") is in `Stopped` state.
2. It is visible in the `#domains` table.

### When

1. The admin clicks the **Start** button (`#btn-play`) on that row.
2. Because this desktop has no bookable reservables the start fires directly —
   no confirmation dialog appears.

### Then

1. `PUT /api/v4/item/desktop/{id}/start` is called and responds with
   status `< 400`.
2. The row's **Status** column transitions from `Stopped` to `Starting` (and
   eventually `Started`) via the `desktop_data` WebSocket event — the DataTable
   row updates in place without a page reload.
3. Once `Started`, the **Action** column switches to a **Stop** button
   (`#btn-stop`) and a **Show** button (`#btn-display`) appears in the
   **Action** column.

### Note on GPU-booked desktops

For the seeded `gpu` desktop (`needs_booking: true`, no active booking):

1. Clicking **Start** triggers a PNotify warning ("non-booked desktop").
2. On **Confirm**, `PUT /api/v4/item/desktop/{id}/start` fires.
3. On **Cancel**, no API call is made; the row status is unchanged.

---

## Scenario 3 — *admin stops a running desktop*

### Given

1. The seeded desktop `started` ("Test started desktop") is in `Started` state
   and visible in the table.

### When

1. The admin clicks the **Stop** button (`#btn-stop`) on that row.

### Then

1. `PUT /api/v4/item/desktop/{id}/stop` is called and responds with
   status `< 400`.
2. The row transitions through `Shutting-down` → `Stopped` via WebSocket events.
3. Once `Stopped`, the **Stop** button is replaced by a **Start** button and the
   **Show** button disappears.

### Force-stop sub-case

If the desktop is already in `Shutting-down`:

1. The button label shows **Force stop** (with a spinner icon).
2. Clicking it calls `PUT /api/v4/item/desktop/{id}/stop` again.
3. The desktop transitions to `Stopping` → `Stopped`.

> **Dev-env note:** In an isolated environment without a real hypervisor the
> domain is put into `Shutting-down` directly via RethinkDB (no actual VM is
> running). In this case the engine has no active VM to force-stop and returns
> `428` instead of `200`. The test accepts both `200` and `428` to cover both
> environments.

---

## Scenario 4 — *admin retries a failed desktop*

### Given

1. The seeded desktop `failed` ("Failed desktop") is in `Failed` state.

### When

1. The admin clicks the **Retry** button (`#btn-update`) in the table row.

### Then

1. `PUT /api/v4/item/desktop/{id}/retry` is called and responds with
   status `< 400`.
2. The row's **Status** column changes from `Failed` to a transitional state
   (typically `Stopped` or `Starting`).
3. The **Retry** button disappears; the appropriate action button for the new
   status is rendered.

---

## Scenario 5 — *admin cancels a storage operation on a maintenance desktop*

### Given

1. The seeded desktop `maintenance` ("Test maintenance desktop") is in
   `Maintenance` state, with `current_action: "increase"`.

### When

1. The admin clicks the **Cancel task** button (`#btn-cancel`) on that row.
2. A PNotify confirmation dialog appears asking "Are you sure you want to
   cancel current storage operation: increase?".
3. The admin confirms.

### Then

1. `GET /api/v4/admin/item/domain/storage/{id}` is called to retrieve the
   attached storage list, responding with status `< 400`.
2. For each storage entry, `PUT /api/v4/item/storage/{storage_id}/abort-operations`
   is called and responds with status `< 400`.
3. A PNotify success notification "Cancelling current storage operation..."
   appears.
4. The desktop's status eventually leaves `Maintenance` (confirmed via WebSocket
   or table reload).

### Cancel sub-case

If the admin presses **Cancel** in the PNotify dialog, no API calls are made
and the row remains in `Maintenance`.

---

## Scenario 6 — *admin edits a desktop's name and description*

### Given

1. The seeded desktop `test` is in `Stopped` state and its row detail is
   **collapsed**.

### When

1. The admin clicks the **expand** button (`.details-control` `+` button) to
   open the row detail panel.
2. The detail panel renders action buttons including **Edit** (`.btn-edit`,
   pencil icon).
3. The admin clicks **Edit**; `#modalEditDesktop` opens, pre-filled with the
   desktop's current name and description.
4. The admin changes the **Description** to updated text (the Name is left
   unchanged to avoid fixture side-effects on other tests).
5. The admin clicks **Send**.

### Then

1. `PUT /api/v4/item/desktop/{id}/edit` is called with the updated fields
   and responds with status `< 400`.
2. The modal closes automatically and a "Domain updated successfully" PNotify
   success notification appears.
3. The `#domains` DataTable reloads (`.ajax.reload()`) and the row remains
   visible.

---

## Scenario 7 — *admin deletes a desktop*

### Given

1. A desktop created by this test exists (e.g., bulk-created in S9) and is
   in `Stopped` state.

### When

1. The admin expands its row detail panel.
2. They click the **Delete** button (`.btn-delete`, red cross).
3. A PNotify confirmation "Are you sure you want to delete virtual machine:
   \<name\>?" appears.
4. The admin confirms.

### Then

1. `DELETE /api/v4/item/desktop/{id}` is called and responds with
   status `< 400`.
2. A PNotify success notification "Desktop deleted" / "Desktop \<name\> has
   been deleted" appears.
3. The row disappears from the `#domains` table (via the `desktop_delete`
   WebSocket event).
4. The desktop is no longer returned by the list API.

### Cancel sub-case

If the admin presses **Cancel** in the confirmation dialog, no DELETE call is
made and the row remains.

---

## Scenario 8 — *admin creates a template from a desktop*

> **Skipped — not idempotent in this environment.** `POST /api/v4/item/template`
> enqueues a storage task on `SEEDED.test`'s storage row. Without a storage
> worker the task stays queued, and every subsequent run raises
> 428 `storage_pending_task`. Cleanup would require cancelling the task via
> `DELETE /task/{id}`, but the only API to discover that ID
> (`GET /api/v4/admin/tasks`) returns 500 in this environment (separate bug).
> To enable this test: fix `GET /api/v4/admin/tasks` **or** expose the `task`
> field in `AdminDomainStorageItem` **or** run a real storage worker.

### Given

1. The seeded desktop `test` ("Desktop with storage") is in `Stopped` state.
2. The template quota is below 100%.

### When

1. The admin expands the row detail panel.
2. They click the **Template** button (`.btn-template`).
3. `#modalTemplateDesktop` opens, pre-filled with:
   - **Name**: `Template Desktop with storage` (or a custom unique name).
   - **Description**: copied from the desktop's description.
   - **Visibility** (`#enabled` checkbox): unchecked by default — the template
     is created disabled. The admin must explicitly check it to make it
     immediately visible to users.
   - **Allowed** (`#alloweds-add`): scope selector (roles, categories, groups,
     users) that controls who can create desktops from this template.
4. The admin enables the visibility checkbox and leaves the alloweds at their
   default.
5. They click **Send**.

### Then

1. `POST /api/v4/item/template` is called with `{ name, desktop_id, allowed,
   description, enabled: true }` and responds with status `< 400`.
2. The modal closes and a "New template — Template created successfully" PNotify
   success notification appears.
3. If the Templates admin page is loaded, the new template appears in its
   table with the visibility indicator matching the chosen `enabled` value.

### Quota-exceeded sub-case

If the template quota is ≥ 100%:

1. Clicking `.btn-template` shows a PNotify error "Quota for creating templates
   full." and the modal does **not** open.

---

## Scenario 9 — *admin bulk-creates desktops from a template*

> **Skipped if no template is available** in the system (the test reads
> `sharedTemplateId` from `beforeAll`; if the template fetch returns null the
> test is skipped with `test.skip(!sharedTemplateId, …)`).

### Given

1. At least one template exists in the system.
2. The admin is on the Desktops admin page.

### When

1. The admin clicks **Bulk Add Desktops** (`.btn-add-desktop`) in the toolbar.
2. `#modalAddDesktop` opens.
3. The admin fills in **Name** with the unique test name and **Description**.
4. They select the first available template from the `#modal_add_desktops`
   DataTable inside the dialog.
5. They set the **allowed** scope (default is pre-filled).
6. They click **Send**.

### Then

1. `POST /api/v4/items/desktops/bulk-create` is called with
   `{ name, template_id, description, allowed }` and responds with
   status `< 400`.
2. A "New desktops — Desktops created successfully" PNotify success notification
   appears.
3. The modal closes automatically.
4. The new desktop appears in the `#domains` table (via WebSocket or reload).

### No-template sub-case

If the admin clicks **Send** without selecting a template:

1. The dialog shows an inline error "No template selected"
   (`#datatables-error-status`).
2. **No** call is made to `POST /api/v4/items/desktops/bulk-create`.
3. The modal stays open.

---

## Scenario 10 — *admin bulk-edits hardware on multiple desktops*

### Given

1. Two or more desktops exist and are visible in the `#domains` table.
2. None of them is currently running (to avoid hardware-locked state).

### When

1. The admin checks the checkboxes of two desktops (`.form-check-input` in
   each row) so that `domains_table.rows('.active').data().length > 0`.
2. They click **Bulk Edit Desktops** (`.btn-bulk-edit-desktops`).
3. `#modalBulkEdit` opens, listing the selected desktop names and the count
   "N desktop(s) will be updated".
4. The admin changes the **vCPUs** field to a new valid value.
5. They click **Send**.

### Then

1. `PUT /api/v4/items/desktops/bulk-edit` is called with
   `{ ids: [...], hardware: { vcpus: N } }` and responds with status `< 400`.
2. A "Updated — N desktop(s) updated successfully" PNotify success notification
   appears.
3. The modal closes.
4. Querying each desktop via the API confirms the new vCPU value.

---

## Scenario 11 — *admin applies a bulk action to selected desktops*

### Given

1. Two or more stopped desktops are visible in `#domains`.
2. The admin has checked their row checkboxes (`.form-check-input`).

### When

1. The admin selects **Delete** from the `#mactions` global-actions dropdown.
2. A PNotify warning lists the selected desktop names and asks for confirmation.
3. The admin confirms.

### Then

1. `POST /api/v4/admin/items/multiple_actions` is called with
   `{ ids: [...], action: 'delete' }` and responds with status `< 400`.
2. A "Action queued: delete" PNotify success notification appears.
3. The `#mactions` dropdown resets to "Select action".
4. The selected rows eventually disappear from the table as WebSocket
   `desktop_delete` events arrive.

### Cancel sub-case

If the admin presses **Cancel** in the PNotify dialog, no API call is made and
the rows remain.

---

## Scenario 12 — *admin applies a bulk action to all desktops (requires "I'm aware")*

### Given

1. No row checkboxes are checked (so the "all applied rows" branch is used).
2. At least one desktop is visible in the filtered table.

### When

1. The admin selects **Force Failed** from the `#mactions` dropdown.
2. A PNotify prompt appears asking the admin to type `"I'm aware"` to confirm.
3. The admin types the wrong phrase first (e.g., `"yes"`).
4. The original prompt PNotify **stays open** (the `click` handler does not call
   `notice.remove()` on a wrong phrase); a separate "Cancelled" info PNotify
   appears and `#mactions` resets to "none". **No** API call is made.
5. The admin clears the prompt input (still open), types `"I'm aware"` correctly,
   and presses **Ok**.

### Then

1. `POST /api/v4/admin/items/multiple_actions` is called with
   `{ ids: [...], action: 'force_failed' }` and responds with status `< 400`.
2. A "Action queued: force_failed" PNotify success notification appears.
3. The `#mactions` dropdown resets to "Select action".

---

## Scenario 13 — *admin changes the owner of a desktop*

### Given

1. A seeded or test desktop is in `Stopped` state.
2. A second user exists in the system (different from the current owner).

### When

1. The admin expands the row detail panel and clicks **Change Owner**
   (`.btn-owner`).
2. `#modalChangeOwnerDomain` opens.
3. The admin types at least 2 letters in the `#new_owner` Select2 search and
   picks the target user from the autocomplete dropdown.
4. They click **Send**.

### Then

1. `PUT /api/v4/item/desktop/{id}/change-owner/{new_owner_id}` is called and
   responds with status `< 400`.
2. A "Owner changed successfully" PNotify success notification appears.
3. The modal closes.
4. The `#domains` table reloads (`ajax.reload()`) and the row shows the new
   owner's name in the **User** column.

### Running-desktop sub-case

If the desktop is in `Started` state when the admin clicks **Send**:

1. A warning PNotify "Desktop is running, changing owner will shut it down.
   Continue?" appears.
2. On **Confirm**, the API call fires and the desktop is stopped.
3. On **Cancel**, no API call is made.

---

## Scenario 14 — *admin enables and disables the share link (jump URL)*

### Given

1. The seeded desktop `test` is in `Stopped` state and has **no** active
   share link (jumper URL).

### When — enable

1. The admin expands the row detail panel and clicks **Jump URL**
   (`.btn-jumperurl`).
2. `#modalJumperurl` opens with the `#jumperurl` field hidden (no link yet).
3. The admin ticks the `#jumperurl-check` checkbox.
4. `PUT /api/v4/item/desktop/{id}/update-share-link` is called with
   `{ enabled: true }` and responds with a `link` in the body.
5. The `#jumperurl` input shows the full URL (`/vw/<link>`).

### Then — enable

1. The API call responds with status `< 400`.
2. The `#jumperurl` field is visible and contains a non-empty URL.
3. The **Copy** button (`.btn-copy-jumperurl`) is also visible.

### When — disable

1. With the share link active, the admin unticks `#jumperurl-check`.
2. A PNotify confirmation "Are you sure you want to delete direct viewer access
   url?" appears.
3. The admin confirms.
4. `PUT /api/v4/item/desktop/{id}/update-share-link` is called with
   `{ enabled: false }`.

### Then — disable

1. The API call responds with status `< 400`.
2. The `#jumperurl` input is cleared and hidden.
3. The **Copy** button is also hidden.

### Cancel sub-case

If the admin presses **Cancel** in the confirmation dialog on disable:

1. No API call is made; `#jumperurl-check` stays checked and the URL remains
   visible.

---

## Scenario 15 — *admin sets a forced hypervisor for a desktop*

> **Skipped in dev** — the test auto-skips if no hypervisors are registered in
> the DB (`#forced_hyp` dropdown is empty). Hypervisors are not seed data: they
> register themselves when the isard-hypervisor service connects to the engine.
> In the isolated testing environment no hypervisor service runs, so the
> dropdown is always empty. Same applies to S19 (favourite hypervisor).

> **Semantics (docs):** When forced hypervisor is active the desktop
> **will only start on that specific hypervisor and on no other**. This is
> different from favourite hypervisor (S19), which allows failover to any
> available alternative.

### Given

1. The seeded desktop `test` has **no** forced hypervisor set
   (`forced_hyp: false / []`).
2. At least one hypervisor is registered in the system.

### When — set

1. The admin expands the row detail panel and clicks **Forced Hyp**
   (`.btn-forcedhyp`).
2. `#modalForcedhyp` opens; the `#forcedhyp-check` checkbox is unchecked and
   `#forced_hyp` is hidden.
3. The admin checks `#forcedhyp-check`; the hypervisor dropdown appears,
   populated from `POST /api/v4/admin/items/table/hypervisors`.
4. The admin picks the first hypervisor and clicks **Send**.

### Then — set

1. `PUT /api/v4/item/desktop/{id}/edit` is called with
   `{ forced_hyp: [<hyp_id>] }` and responds with status `< 400`.
2. A "Updated — Forced hypervisor updated successfully" PNotify success
   notification appears.
3. The modal closes.
4. The **Forced Hyper** column in the table row shows the chosen hypervisor ID
   (verified after page reload).

### When — clear

1. The admin opens the modal again; `#forcedhyp-check` is now checked.
2. They uncheck it; `#forced_hyp` hides and the dropdown empties.
3. They click **Send**.

### Then — clear

1. `PUT /api/v4/item/desktop/{id}/edit` is called with `{ forced_hyp: false }`
   and responds with status `< 400`.
2. The **Forced Hyper** column reverts to `-` (verified after page reload).

---

## Scenario 16 — *admin views storage and increases disk size*

### Given

1. The seeded desktop `s16` ("Desktop S16 storage") is in `Stopped` state.
   This desktop is dedicated to S16 only to avoid race conditions with S2's
   `PUT /start` under `fullyParallel`.
2. It has at least one storage entry with `status: "ready"`.

### When — open modal

1. The admin clicks the **Storage** button (`#btn-storage`, HDD icon) visible
   in the table row (only shown for `Stopped` desktops).
2. `#modalDesktopStorage` opens with a loading spinner.
3. `GET /api/v4/admin/item/domain/storage/{id}` is called; it responds with
   a non-empty list of storage objects.

### Then — modal renders

1. The modal title shows the desktop name.
2. Each storage entry is displayed with its ID, status label, virtual/actual
   size, and action buttons.
3. For `ready` storage on a `Stopped` desktop, the **Increase** button is
   enabled; the **Cancel** button is only present when the storage has a
   pending task.

### When — increase disk

1. The admin clicks the **Increase** button (`.btn-increase`) for the first
   storage entry.
2. The click fires three background requests:
   - `GET /api/v4/admin/item/storage/info/{storage_id}` — to fetch the current
     virtual disk size and owner.
   - `GET /api/v4/item/storage/{storage_id}/has-derivatives` — to guard against
     resizing a disk that has child templates.
   - `GET /api/v4/admin/item/user/appliedquota/{user_id}` — to enforce the
     user's disk-size quota.
3. `#modalDesktopStorage` closes; `#modalIncreaseStorage` opens (Bootstrap 3
   cannot stack modals, so the parent hides first).
4. The admin sets the **New size** field to a value greater than the current
   size and clicks **Increase** (`#send`).

### Then — increase disk

1. `PUT /api/v4/item/storage/{storage_id}/priority/{priority}/increase/{increment}`
   is called and responds with status `< 400`, where `increment = new_size − current_size`.
2. A "Task created successfully" PNotify success notification appears.
3. All modals close automatically (`$('.modal').modal('hide')`).

### Validation / cancel sub-cases

- If the admin clicks **Cancel** in `#modalIncreaseStorage`, no API call is
  made and the modal closes.
- If the admin submits the form with **New size** ≤ the current size, Parsley
  client-side validation blocks the submission and **no** API call is made.

---

## Scenario 17 — *admin enables server mode with autostart*

> **Semantics (docs):** Server mode keeps the desktop running continuously.
> The **autostart** option restarts it automatically if it is ever shut down.
> Editing a server desktop requires deactivating autostart first because the
> desktop must be offline before any modification.

### Given

1. The seeded desktop `test` is in `Stopped` state and server mode is **off**
   (`server: false`).

### When — enable server mode

1. The admin expands the row detail panel and clicks **Server** (`.btn-server`).
2. `#modalServer` opens; the `#server` iCheck checkbox is unchecked and the
   `#autostart` checkbox is greyed out.
3. The admin checks `#server`; the `#autostart` checkbox becomes active.
4. The admin also checks `#autostart`.
5. They click **Send**.

### Then — enable

1. `PUT /api/v4/item/desktop/{id}/edit` is called with
   `{ server: true, server_autostart: true }` and responds with status `< 400`.
2. A "Updated — Server updated successfully" PNotify success notification
   appears.
3. The modal closes.
4. The **Server** column in the `#domains` table shows `AUTO` for that row
   (verified after page reload).

### When — disable server mode

1. The admin navigates back to the Desktops page (page reload after column
   verification); expands the row detail panel and clicks **Server** again.
2. `#server` is checked; they uncheck it; `#autostart` is greyed out again.
3. They click **Send**.

### Then — disable

1. `PUT /api/v4/item/desktop/{id}/edit` is called with
   `{ server: false, server_autostart: false }` and responds with status `< 400`.
2. The **Server** column reverts to `-` (verified after page reload).

### Note on column update

The `#modalServer` success callback does not call `domains_table.ajax.reload()`;
the column updates via the `desktop_data` WebSocket event when the engine
acknowledges the change. The test verifies the column after an explicit page
reload, which fetches fresh data from the API regardless of WebSocket timing.

### Autostart-only sub-case

If the admin checks `#server` but leaves `#autostart` unchecked:

1. `{ server: true, server_autostart: false }` is sent.
2. The **Server** column shows `SERVER` (not `AUTO`).

---

## Scenario 18 — *admin opens the Info modal for a desktop*

> **Semantics (docs):** The Info modal (available since v14.119.0) shows a
> quick-view of domain details, owner info, network interfaces, and Bastion
> access, plus action buttons (Start, Stop, Delete).

### Given

1. The seeded desktop `test` ("Desktop with storage") is visible in the
   `#domains` table.

### When

1. The admin clicks the **Info** button (`.btn btn-xs btn-info` with
   `data-domain-info` attribute, column "Info") on that row.
2. The domain info modal opens.

### Then

1. The modal is visible and displays:
   - **Domain details section**: ID matching the seeded `test` desktop ID,
     name "Desktop with storage", kind `desktop`, status `Stopped`.
   - **Owner section**: at minimum the username and role fields are non-empty.
   - **Network interfaces section**: at least one network entry (or a clear
     "no interfaces" message if the desktop has none configured).
2. The modal contains action buttons — at least **Start** and **Delete** are
   present for a `Stopped` desktop.
3. Clicking **Start** from inside the modal calls
   `PUT /api/v4/item/desktop/{id}/start` (same as the table row button) and
   responds with status `< 400`.

### Search-by-UUID sub-case

The UUID search box in the toolbar (`#domain-uuid-search`) is an alternative
entry point to the same modal:

1. The admin enters the desktop ID in `#domain-uuid-search` and presses Enter
   (or clicks the search button).
2. The same info modal opens.
3. If the value is not a valid UUID format, a PNotify error "Invalid UUID
   format" appears and **no** modal opens.
4. If the field is empty, a PNotify error "Please enter a desktop ID" appears.

---

## Scenario 19 — *admin sets a favourite hypervisor for a desktop*

> **Semantics (docs):** When a favourite hypervisor is set the desktop
> **will start on that hypervisor if it is available; if not, it falls back
> to any other available hypervisor**. This is the key difference from forced
> hypervisor (S15), which never falls back.

### Given

1. The seeded desktop `test` has **no** favourite hypervisor set
   (`favourite_hyp: false / []`).
2. At least one hypervisor is registered in the system.

### When — set

1. The admin expands the row detail panel and clicks **Favourite Hyp**
   (`.btn-favouritehyp`).
2. `#modalFavouriteHyp` opens; the `#favouritehyp-check` checkbox is unchecked
   and `#favourite_hyp` is hidden.
3. The admin checks `#favouritehyp-check`; the dropdown appears, populated
   from `POST /api/v4/admin/items/table/hypervisors`.
4. The admin picks the first hypervisor and clicks **Send**.

### Then — set

1. `PUT /api/v4/item/desktop/{id}/edit` is called with
   `{ favourite_hyp: [<hyp_id>] }` and responds with status `< 400`.
2. A "Updated — Favourite hypervisor updated successfully" PNotify success
   notification appears.
3. The modal closes.
4. The **Fav Hyper** column in the table row shows the chosen hypervisor ID.

### When — clear

1. The admin opens the modal again; `#favouritehyp-check` is now checked.
2. They uncheck it and click **Send**.

### Then — clear

1. `PUT /api/v4/item/desktop/{id}/edit` is called with
   `{ favourite_hyp: false }` and responds with status `< 400`.
2. The **Fav Hyper** column reverts to `-`.

---

## Scenario 20 — *admin opens the desktop logs modal and both tabs load without error*

> This is a smoke test. It does **not** assert specific log entries (content
> depends on prior activity in the environment). It verifies that the modal
> opens, both API calls succeed, and the UI does not enter an error state.
> The bug that motivated this scenario: the three POST requests inside
> `desktop_logs_modal.js` were sent as form-encoded data without an explicit
> `contentType`, causing the backend dependency `parse_json_or_form` to raise a
> 400 "Request body must be JSON or form data" on every open.

### Given

1. The seeded desktop `test` ("Desktop with storage") is visible in the
   `#domains` table.

### When

1. The admin expands the row detail panel.
2. They click the **Logs** button (`.btn-desktop-logs`).
3. The `#desktop-logs-modal` opens.

### Then

1. The modal is visible with the title "Desktop Logs: Desktop with storage".
2. **Tab 1 — Desktop Logs:**
   The `POST /api/v4/admin/items/logs_desktops` fired by the DataTables
   initialization responds with status `< 400`. The table `#table-desktop-logs`
   renders without an error state (no `dataTables_empty` error class, no
   red/alert styling from a failed ajax).
3. **Tab 2 — Direct Viewer Logs:**
   A second `POST /api/v4/admin/items/logs_desktops` fired by
   `loadDirectViewerLogs` also responds with status `< 400`. Switching to the
   "Direct Viewer Logs" tab renders the `#table-directviewer-logs` table
   without errors (zero rows is acceptable).
4. The **Download CSV** button is present and enabled.
5. Clicking **Close** dismisses the modal cleanly.

---

## Scenario 21 — *User, Category, Role and Group columns are populated after load, edit and create*

> **Why this test exists:** `AdminDomainListItem` declares `user_name`, `role`,
> `category_name`, and `group_name` all as `Optional`. Three different code
> paths write to the `#domains` table — the initial `ajax` load, the
> `ajax.reload()` triggered after an edit, and the `desktop_data` WebSocket
> event triggered after a create. Any of these can silently omit those fields
> and leave the cells blank. This test pins that contract so a refactor that
> drops any of the four fields is caught immediately.

### Given

1. The seeded desktop `test` ("Desktop with storage") is visible in the
   `#domains` table.
2. Its owner is user `admin_e2e_09` (`id: c7e77d70-e443-53d2-9933-d9b83e4a19a1`),
   whose seed-DB fields are:
   | Field | Seed value |
   | --- | --- |
   | `name` (→ `user_name` column) | `E2E Admin 09` |
   | `role` | `admin` |
   | `category` → `name` (→ `category_name` column) | `Default` |
   | `group` → `name` (→ `group_name` column) | `Default` |

---

### Part A — columns are populated on initial table load

#### When

1. The admin navigates to `/isard-admin/admin/domains/render/Desktops`.
2. The `#domains` DataTable finishes loading.

#### Then

1. The row for "Desktop with storage" exists in the table.
2. The **User** cell (`data-field: user_name`) contains exactly `"E2E Admin 09"`.
3. The **Role** cell (`data-field: role`) contains exactly `"admin"`.
4. The **Category** cell (`data-field: category_name`) contains exactly `"Default"`.
5. The **Group** cell (`data-field: group_name`) contains exactly `"Default"`.
6. `POST /api/v4/admin/items/domains` responds with status `< 400` and the
   matching entry in the response body has all four fields non-null.

---

### Part B — columns survive an edit (`ajax.reload()`)

#### When

1. The admin expands the row detail of "Desktop with storage" and clicks
   **Edit** (`.btn-edit`).
2. They change the **Description** field to a new value (name is left
   unchanged to avoid fixture side-effects) and click **Send**.
3. `PUT /api/v4/item/desktop/{id}/edit` responds with status `< 400`.
4. The modal closes and `domains_table.ajax.reload()` fires, reloading the
   table from `POST /api/v4/admin/items/domains`.

#### Then

1. The row for "Desktop with storage" is still present.
2. The **User**, **Role**, **Category**, and **Group** cells still show exactly
   the same seeded values (`"E2E Admin 09"`, `"admin"`, `"Default"`, `"Default"`).

---

### Part C — columns are populated for a newly created desktop

> **Skipped if no template is available** (`sharedTemplateId` is null). When a
> template exists the part runs: a desktop is created via the API and the new
> row's metadata cells are verified.

#### When

1. The admin bulk-creates a desktop using the same flow as Scenario 9,
   targeting only their own user.
2. The new row appears in the table (via the `desktop_data` WebSocket event
   or a subsequent reload).

#### Then

1. The new row is visible in the table.
2. The **User** cell shows the creating admin's display name (non-empty).
3. The **Role** cell shows `admin` (non-empty).
4. The **Category** cell shows the category name (non-empty).
5. The **Group** cell shows the group name (non-empty).

---

## Cleanup (afterEach)

1. Desktops created dynamically by Scenarios 7, 9, 10, 11, 13 and 21-C are
   tracked via `testInfo.annotations` (type `'desktop-name'`).
2. After each test, any matching desktop is found by name via
   `POST /api/v4/admin/items/domains` and deleted via
   `DELETE /api/v4/item/desktop/{id}`.
3. The seeded desktops (`test`, `started`, `failed`, `maintenance`) must be
   restored to their original state if the test mutated them (e.g., a started
   desktop should be stopped before the next run).
4. Cleanup errors are silenced so they do not mask the actual test failure.

---

## Expected results — global summary

| Scenario | Covered in test? | Key checks |
| --- | --- | --- |
| S1 — Table loads | ✅ | `#domains` renders; seeded row visible; status correct |
| S2 — Start desktop | ⚠️ partial | `PUT /start` ok; btn-play hidden after click — WebSocket transition to Started/btn-stop not verifiable without a running hypervisor |
| S2 (GPU sub-case) — Start GPU desktop | ✅ | `GET /admin/item/domain/{id}/viewer_data` ok; non-booked PNotify appears; Cancel aborts; Confirm fires `PUT /start` |
| S3 — Stop desktop | ⚠️ partial | `PUT /stop` ok; btn-stop hidden after click — WebSocket transition to Stopped/btn-play not verifiable without a running hypervisor |
| S3 (force-stop sub-case) — Force stop | ⚠️ partial | Shutting-down state renders Force stop button; `PUT /stop` fires; returns 428 in dev (no hypervisor/active VM) instead of 200 |
| S4 — Retry failed desktop | ⚠️ partial | `PUT /retry` ok; UI state after retry (button change, status transition) not verifiable without a running hypervisor |
| S5 — Cancel maintenance op | ✅ | `GET /domain/storage` ok; `abort-operations` called; PNotify "Cancelling" visible |
| S6 — Edit desktop | ✅ | `PUT /edit` ok; modal closes; "Domain updated successfully" PNotify visible; table refreshed |
| S7 — Delete desktop | ✅ | `DELETE` ok; row disappears — skips if no template in DB |
| S8 — Create template | ⏭ skipped | not idempotent without storage worker: subsequent runs hit 428 `storage_pending_task`; `GET /admin/tasks` returns 500 |
| S9 — Bulk create desktops | ✅ | `POST bulk-create` ok; modal closes; row appears — skips if no template in DB |
| S10 — Bulk edit hardware | ✅ | `PUT bulk-edit` ok; modal closes — skips if no template in DB |
| S11 — Bulk action (selected) | ✅ | `POST multiple_actions` ok; rows disappear — skips if no template in DB |
| S12 — Bulk action (all, "I'm aware") | ✅ | Wrong phrase → Cancelled PNotify; prompt stays open; correct phrase → API fires |
| S13 — Change owner | ✅ | `PUT change-owner` ok; User column updates — skips if no template in DB |
| S14 — Share link enable/disable | ✅ | `PUT update-share-link` ok; URL non-empty and visible; Copy button shown/hidden |
| S15 — Forced hypervisor set/clear | ✅ | SET: `PUT /edit { forced_hyp }` ok; Forced Hyper column shows chosen hyp ID after reload; CLEAR: column reverts to `-`; auto-skipped if no hypervisors |
| S16 — Storage view & increase | ✅ | `GET domain/storage` ok; Cancel aborts without API call; `PUT /increase` ok; "Task created successfully" PNotify visible; modal closes |
| S17 — Server mode + autostart | ✅ | Enable: `PUT /edit { server, server_autostart }` ok; Server column shows `AUTO` after reload; Disable: column reverts to `-` after reload |
| S18 — Info modal + UUID search | ✅ | Modal shows ID; owner table non-empty; interfaces table renders; Start fires `PUT /start`; UUID search works |
| S19 — Favourite hypervisor set/clear | ✅ | SET: `PUT /edit { favourite_hyp }` ok; Fav Hyper column shows chosen hyp ID after reload; CLEAR: column reverts to `-`; auto-skipped if no hypervisors |
| S20 — Desktop logs modal smoke | ✅ | Modal title correct; CSV button present; both `POST /logs_desktops` calls return `< 400`; no error state in either tab |
| S21 — User/Category/Role/Group columns populated | ✅ | A: cells show exact seeded values on load; B: exact values survive `ajax.reload()` after edit; C: metadata cells populated for new row (skips if no template) |
| S22 — XML sections editor smoke | ✅ | Modal opens; both GETs respond `< 400`; sections render without error; Save: `POST /xml_sections` responds `< 400`; modal closes |
| S23 — Row detail description and hardware | ✅ | Both AJAX calls respond `< 400`; `#description` shows `"Base desktop"`; `#vcpu` shows `"1 CPU(s)"`; `#ram` shows `"0.50GB"` |
| S24 — Status filter (server-side) | ✅ | `POST /domains` fires with `status: "Stopped"` in body; seeded Stopped row visible after filtered reload |
| S25 — Name filter (server-side) | ✅ | `POST /domains` fires with `name` in body ✓; matching row visible, non-matching row hidden |
| S26 — Clear filters | ✅ | Filter boxes removed from DOM; options restored to `#filter-select`; column search cleared (hidden rows reappear) |
| S27 — Reload button | ✅ | No `POST /domains` fired; filter box still present; status options repopulated after reload |

## APIs touched by the flows (reference)

- `POST   /api/v4/admin/items/domains` — list desktops. Body `{ kind: "desktop", categories: [...] }`.
- `POST   /api/v4/admin/items/table/domains` — pluck fields for a domain.
- `PUT    /api/v4/item/desktop/{id}/start` — start a desktop.
- `PUT    /api/v4/item/desktop/{id}/stop` — stop / force-stop a desktop.
- `PUT    /api/v4/item/desktop/{id}/retry` — retry a failed desktop.
- `PUT    /api/v4/item/desktop/{id}/edit` — edit name, description, hardware, forced_hyp, favourite_hyp, server.
- `DELETE /api/v4/item/desktop/{id}` — delete a desktop.
- `GET    /api/v4/admin/item/domain/{id}/viewer_data` — viewer data (reservables + booking check before start; admin path).
- `GET    /api/v4/item/desktop/{id}/get-info` — desktop info for template dialog pre-fill.
- `POST   /api/v4/item/template` — create a template from a desktop.
- `POST   /api/v4/items/desktops/bulk-create` — create desktops in bulk from template.
- `PUT    /api/v4/items/desktops/bulk-edit` — edit hardware on multiple desktops.
- `POST   /api/v4/admin/items/multiple_actions` — apply an action to a list of desktop IDs.
- `PUT    /api/v4/item/desktop/{id}/change-owner/{new_owner_id}` — change desktop owner.
- `GET    /api/v4/item/desktop/{id}/get-share-link` — get current share link.
- `PUT    /api/v4/item/desktop/{id}/update-share-link` — enable or disable share link.
- `GET    /api/v4/admin/item/domain/storage/{id}` — list storage attached to a desktop.
- `PUT    /api/v4/item/storage/{storage_id}/abort-operations` — cancel storage operation.
- `PUT    /api/v4/item/storage/{storage_id}/priority/low/increase/{increment}` — increase disk.
- `POST   /api/v4/admin/items/table/hypervisors` — list hypervisors (for forced/favourite hyp dropdowns).
- `POST   /api/v4/items/alloweds/term/users` — user search for owner change (Select2 AJAX).

## APIs touched by the flows — additions for S17–S22

- `PUT    /api/v4/item/desktop/{id}/edit` with `{ server, server_autostart }` — server mode (S17).
- `GET    /api/v4/admin/item/domain/{id}/details` — domain detail fetch for the info modal (S18).
- `PUT    /api/v4/item/desktop/{id}/edit` with `{ favourite_hyp }` — favourite hypervisor (S19).
- `POST   /api/v4/admin/items/logs_desktops` — desktop logs query, DataTables server-side format (S20). Called twice on modal open: once by the DataTables init (Tab 1) and once by `loadDirectViewerLogs` (Tab 2).
- `GET    /api/v4/admin/item/domains/xml_sections/{id}` — fetch XML sections for the editor (S22).
- `GET    /api/v4/admin/item/domains/xml_capabilities` — fetch hypervisor capabilities for section dropdowns (S22).
- `POST   /api/v4/admin/item/domains/xml_sections/{id}` — save XML sections (S22).
- `GET    /api/v4/admin/item/domain/{id}/details` — status detail and description for the row detail panel (S23).
- `GET    /api/v4/admin/item/domain/hardware/{id}` — hardware summary (vCPUs, RAM, network, video, boot) for the row detail panel (S23).

---

## Scenario 22 — *admin opens the XML sections editor and saves without changes*

> This is a smoke test. It does **not** assert specific XML content (section
> values depend on the desktop's KVM/QEMU config and require libvirt expertise
> to validate). It verifies that the modal opens, both load requests succeed,
> the container renders without an error alert, and the save call succeeds.

### Given

1. The seeded desktop `test` ("Desktop with storage") is visible in the
   `#domains` table and in `Stopped` state.

### When

1. The admin expands the row detail panel and clicks **XML** (`.btn-xml`).
2. `#modalEditXmlSections` opens and fires two parallel requests:
   - `GET /api/v4/admin/item/domains/xml_sections/{id}`
   - `GET /api/v4/admin/item/domains/xml_capabilities`
3. Both respond and the sections are rendered inside `#xmlSectionsContainer`.
4. The admin clicks **Save** (`#xmlSectionsSave`) without modifying anything.

### Then

1. Both `GET` requests respond with status `< 400`.
2. `#xmlSectionsContainer` renders content — no `.alert-danger` error block and
   not empty (spinner replaced by actual section markup).
3. `POST /api/v4/admin/item/domains/xml_sections/{id}` is called and responds
   with status `< 400`.
4. The modal closes automatically.

---

---

## Scenario 23 — *row detail panel shows correct description and hardware*

### Given

1. The seeded desktop `test` ("Desktop with storage") is visible in the
   `#domains` table.
2. Its seed-DB values are:
   | Field | Value |
   | --- | --- |
   | `description` | `Base desktop` |
   | `create_dict.hardware.vcpus` | `1` |
   | `create_dict.hardware.memory` | `524288` bytes → `0.50 GB` |

### When

1. The admin clicks the **expand** button (`td.details-control`) on the row.
2. The detail panel (`[id="actions-{id}"]`) becomes visible.
3. Two AJAX calls fire automatically:
   - `GET /api/v4/admin/item/domain/{id}/details` → populates
     `#description-{id}` and `#status-detail-{id}`.
   - `GET /api/v4/admin/item/domain/hardware/{id}` → populates
     `#hardware-{id} #vcpu`, `#ram`, `#net`, `#video`, `#boot`, `#disk_bus`.

### Then

1. Both `GET` requests respond with status `< 400`.
2. `#description-{id}` shows exactly `"Base desktop"`.
3. `#hardware-{id} #vcpu` shows exactly `"1 CPU(s)"`.
4. `#hardware-{id} #ram` shows exactly `"0.50GB"`.

---

---

## Scenario 24 — *admin applies a server-side indexed filter (status)*

> The filter toolbar has two types of filters. **Server-side (indexed)** filters
> (`status`, `group`, `user`, `hyp_started`, `server`) are sent as parameters
> in the `POST /api/v4/admin/items/domains` body, triggering `ajax.reload()`.
> **Client-side** filters (`name`, `memory`, `vcpus`, `forced_hyp`,
> `favourite_hyp`) apply a DataTables column regex search on already-loaded data
> — no API round-trip. This scenario tests the indexed path.

### Given

1. The admin is on the Desktops page with the full desktop list loaded.

### When

1. The admin selects **Status** from the `#filter-select` dropdown.
2. The status filter box appears in `#filter-boxes`; its select is pre-populated
   from `GET /api/v4/admin/items/domains/status/desktop`.
3. The admin selects `Stopped` from the filter's Select2 widget.
4. The admin clicks **Search** (`#btn-search`).

### Then

1. `POST /api/v4/admin/items/domains` is called with `{ status: "Stopped", … }`
   in the request body and responds with status `< 400`.
2. The `#domains` table shows only `Stopped` desktops.
3. The seeded desktop `test` ("Desktop with storage", status `Stopped`) is
   visible in the filtered table.

---

## Scenario 25 — *admin applies a server-side name filter*

> **Note:** the name filter was converted to a server-side indexed filter
> (commit `6f5dc2af1`) to support datasets beyond 70 k desktops. The Select2
> widget uses a remote type-ahead (`GET /admin/items/domains/name/desktop/search`).
> The test sets the value programmatically via jQuery for reliability.

### Given

1. The admin is on the Desktops page with the full desktop list loaded.

### When

1. The admin selects **Name** from the `#filter-select` dropdown.
2. The name filter box appears in `#filter-boxes` with a Select2 AJAX widget.
3. The admin selects `"Desktop with storage"` (set programmatically via jQuery
   to avoid the `populateSelect` bug).
4. The admin clicks **Search** (`#btn-search`).

### Then

1. `POST /api/v4/admin/items/domains` is fired with `{ name: ["Desktop with storage"] }`
   in the body and responds with status `< 400`.
2. Only the matching row ("Desktop with storage") remains visible; non-matching
   rows (e.g. "Failed desktop") are hidden.

---

## Scenario 26 — *admin clears all active filter boxes*

### Given

1. The admin is on the Desktops page with at least two filter boxes active
   (`status` and `name`).
2. Both filter options have been removed from `#filter-select` after being added.

### When

1. The admin clicks **Clear** (`#btn-clear`).

### Then

1. All active filter boxes (`#filter-status`, `#filter-name`, …) are removed
   from `#filter-boxes`.
2. Their corresponding options (`status`, `name`) are re-added to
   `#filter-select` and are selectable again.
   (`removeFilter` re-appends the option and re-sorts the dropdown alphabetically.)
3. The DataTables column search is cleared (`this.search('').draw()`) so any
   locally hidden rows reappear from the current dataset.

### Note on indexed filters

Clearing an indexed filter (e.g., `status`) removes its DOM box and clears the
column search, but does **not** trigger a new `ajax.reload()`. The table retains
the last API-filtered subset until the admin clicks **Search** again (with no
filters) or **Reload** (`#btn-reload`).

---

## Scenario 27 — *admin reloads the table without triggering an API call*

### Given

1. The admin is on the Desktops page with at least one filter box active
   (e.g. `status`).

### When

1. The admin clicks **Reload** (`#btn-reload`).

### Then

1. **No** new `POST /api/v4/admin/items/domains` is fired — `reloadOtherFiltersContent`
   calls `table.draw(false)` (client-side redraw only, no `ajax.reload()`).
2. The active filter box is still present in `#filter-boxes` after reload.
3. `populateSelect` reruns and re-populates the filter's options.

---

## Cases not covered (future)

- **Viewer connection**: clicking **Show** (`#btn-display`) and asserting the
  VNC/RDP session opens — requires a real running VM.
- **XML sections content validation** — asserting specific section values
  (CPU topology, disk buses, etc.) requires libvirt expertise; the smoke
  test in S22 already covers the HTTP contract.
- **Desktop logs content** — specific row assertions in `#table-desktop-logs`
  (timestamps, durations, initiators) depend on prior activity in the
  environment; the smoke test in S20 already covers the HTTP contract.
- **Filter combinations** (two or more indexed filters active simultaneously,
  e.g. `status + user`) — logic is better covered by lower-level unit tests.
- **"Remove forced/favourite hypervisor" bulk actions** — mirrors the per-row
  clear flows of S15/S19; omitted to avoid duplication.
