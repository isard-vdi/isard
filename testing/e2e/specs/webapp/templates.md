# Template management in webapp

Human-readable functional specification of the **enable/disable**,
**duplicate**, **delete**, **edit**, **XML**, **change owner**,
**forced/favourite hypervisor**, **permissions (alloweds)**, **info
modal**, **detail panel**, and **filtering** flows for templates in the
legacy admin panel. Serves as the contract for the E2E test
`tests/webapp/templates.spec.js`.

## Scope

- **Component**: administration panel.
- **Screen**: **Templates** section at
  `/isard-admin/admin/domains/render/Templates`. Accessible to
  administrators and managers.
- **Actions covered**:
  - View and filter the templates list; verify row data for a known seed
    template.
  - Show and hide disabled templates.
  - Enable and disable individual templates.
  - Duplicate (create a copy of) a template — happy path and cancel.
  - Delete a template without derivatives — happy path and cancel.
  - Delete a template with cross-category derivatives (blocked).
  - Edit a template's hardware settings — happy path, cancel, and
    viewers selection persists after save.
  - Open the XML editor — modal opens and sections render (happy path).
  - Change the owner of a template — happy path and cancel.
  - Assign and remove a forced hypervisor — happy path and cancel.
  - Assign and remove a favourite hypervisor — happy path and cancel.
  - Search a template by UUID — valid, invalid format, and empty input.
  - Open the info-circle domain info modal and validate the displayed
    data for the seed template.
  - Expand the row detail panel and validate hardware, storage, and
    alloweds data for the seed template.
  - Edit template permissions via the Shares (`btn-alloweds`) button —
    happy path and cancel.
- **Out of scope**: creating templates from scratch (desktops-to-template
  conversion), booking/reservation management, share link / jumper URL
  (the `btn-jumperurl` button is absent from the admin template detail
  panel), server-mode assignment.

## Common role and prerequisites

| Element | Expected value |
| --- | --- |
| Role | Administrator of the `default` category |
| Session | Logged in to the webapp |
| Infrastructure | At least one registered hypervisor |
| Templates list | The `#domains` DataTable has loaded and is visible |

## Common data

| Field | Sample value | Notes |
| --- | --- | --- |
| Duplicate name | `e2e-tpl-<worker>-<timestamp>` | 4–50 chars; letters, digits, space, `.`, `-`, `_`, and accented characters |
| Duplicate description | `e2e template duplicated at <ISO timestamp>` | Free text |
| Seed template | `Template test frontend` | Fixed seed; used for all data-validation scenarios |
| Seed disabled template | A template with `enabled = false` | Used in S3; must exist in the initial seed |

The duplicate name is stored in test metadata so that `afterEach` can
recover and clean it up even if assertions fail.

---

## Scenario 1 — *admin views the templates table with all expected columns*

### Given

1. The administrator is authenticated in the webapp.
2. They navigate to the **Templates** page.

### When

1. The page loads and the `#domains` DataTable finishes its initial
   request to `POST /api/v4/admin/items/domains` with body
   `{"kind": "template"}`.

### Then

1. The table is visible and contains at least one row.
2. The visible column headers are: **Name**, **Description**, **User**,
   **Category**, **Group**, **Favourite Hyper**, **Forced Hyper**,
   **Enabled**, **Derivatives**, **Shares**, **Last Access**.
3. The **Enabled** column shows a checkbox for each row reflecting the
   template's current `enabled` state.
4. The **Shares** column shows the `btn-alloweds` button for each row.
5. Each row has an expand button (`.details-control`, fa-plus icon) and
   an info-circle button (`.info-control`, `data-domain-info` attribute).
6. The `#domain-uuid-search` input and the show/hide-disabled toggle
   button are visible in the toolbar.

---

## Scenario 2 — *admin toggles the show/hide disabled templates button*

### Given

1. The admin is on the Templates page with the table loaded.
2. At least one disabled template exists in the system.
3. By default the DataTable starts with `view="false"`, which shows **all**
   templates including disabled ones. The button label is **"Hide Disabled"**
   — this describes the action ("click to hide disabled rows"), not the
   current visibility state.

### When

1. They click the `.btn-disabled` toolbar button (currently showing
   "Hide Disabled").

### Then

1. The button label switches to **"View Disabled"**.
2. The DataTable redraws with `view="true"` — disabled rows (`enabled = false`)
   **disappear** from the table (only enabled templates shown).
3. Clicking the button again returns to **"Hide Disabled"** state and the
   disabled rows reappear in the table.

---

## Scenario 3 — *admin enables a disabled template*

### Given

1. A disabled template is visible in the table. Because the default state is
   `view="false"` (all templates shown), no toggle interaction is needed.
2. Its **Enabled** checkbox is **unchecked**.

### When

1. They tick the **Enabled** checkbox on the template's row.
2. A PNotify confirmation dialog appears: *"Are you sure you want to
   enable this template?"*.
3. They confirm.

### Then

1. `PUT /api/v4/item/template/{id}/set-enabled` with body
   `{"enabled": true}` responds with status `< 400`.
2. A PNotify success notification *"Template enabled"* appears.
3. The DataTable reloads; the row now shows a **checked** Enabled
   checkbox.
4. If queried via `POST /api/v4/admin/items/domains`, the template has
   `enabled = true`.

---

## Scenario 4 — *admin cancels the disable confirmation*

### Given

1. An enabled template exists and its **Enabled** checkbox is checked.

### When

1. They uncheck the **Enabled** checkbox.
2. A PNotify confirmation dialog appears: *"Are you sure you want to
   disable this template? All the temporal desktops (if any) derivated
   from this template will be deleted."*
3. They press **Cancel**.

### Then

1. **No** call is made to `PUT /api/v4/item/template/{id}/set-enabled`.
2. The checkbox reverts to **checked** (restored from `template_enabled`).
3. The table state is unchanged.

---

## Scenario 5 — *admin disables a template*

### Given

1. An enabled template exists and its **Enabled** checkbox is checked.

### When

1. They uncheck the **Enabled** checkbox.
2. The PNotify confirmation dialog appears.
3. They confirm.

### Then

1. `PUT /api/v4/item/template/{id}/set-enabled` with body
   `{"enabled": false}` responds with status `< 400`.
2. A PNotify success notification *"Template disabled"* appears.
3. The DataTable reloads; the row shows an **unchecked** Enabled checkbox
   (or disappears if show-disabled is off).
4. If queried via API, the template has `enabled = false`.

---

## Scenario 6 — *admin duplicates a template*

### Given

1. `Template test frontend` exists in the table and its detail row is
   expanded (`.details-control`).

### When — happy path

1. They press **Duplicate** (`btn-duplicate-template`).
2. The `#modalDuplicateTemplate` dialog opens, pre-filled with name
   `"Template <seed-name>"` and the seed description
   (via `GET /api/v4/item/template/{id}/get-info`).
3. They clear the name, enter `e2e-tpl-<worker>-<timestamp>`, update
   the description.
4. They press **Send**.

### Then — happy path

1. `POST /api/v4/item/template/{seed_id}/duplicate` with the new name,
   description, and `enabled: true` responds with status `< 400`.
2. A PNotify success notification *"Template duplicated successfully"*
   appears.
3. The dialog closes and the DataTable reloads.
4. A new row with the entered name appears in the table.
5. Querying `POST /api/v4/admin/items/domains` returns the new template
   with matching name and description.

### Cancel path

1. The dialog is open with valid data entered.
2. They press **Close** (or the × button).
3. **No** call is made to `POST /api/v4/item/template/{id}/duplicate`.
4. The dialog closes and no new row appears in the table.

---

## Scenario 7 — *admin tries to duplicate a template with an invalid name*

### Given

1. The `#modalDuplicateTemplate` dialog is open for a seed template.

### When

1. They enter an invalid value in the **Name** field. Cases to cover:
   - Too short (fewer than 4 characters), e.g. `ab`.
   - Contains characters outside the allowed set
     (`^[\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$`), e.g.
     `tpl@1`, `my/template`.
   - Empty.
2. They press **Send**.

### Then

1. Client-side validation (Parsley) blocks the submission.
2. An inline error message appears on the name field.
3. **No** call is made to `POST /api/v4/item/template/{id}/duplicate`.
4. The dialog stays open with the rest of the entered data intact.

---

## Scenario 8 — *admin deletes a duplicated template; original is not affected*


### Given

1. `Template test frontend` (the original seed) exists in the table.
2. A duplicate of it — `e2e-tpl-<worker>-<timestamp>` (created in S6 or
   via API fixture) — also exists, with **no** child desktops or
   sub-templates.

### When — happy path

1. They expand the **duplicate** template row (`.details-control`).
2. They press **Delete** (`btn-delete-template`).
3. The `#modalDeleteTemplate` dialog opens; the system fetches the
   derivative tree via
   `GET /api/v4/admin/items/desktops/tree_list/{id}` — tree is empty.
4. The **Stop and Delete** button is enabled.
5. They press **Stop and Delete**.

### Then — happy path

1. `DELETE /api/v4/admin/item/templates/delete/{id}` (id of the
   **duplicate**) responds with status `< 400`.
2. A PNotify success notification *"Item(s) deleted successfully"*
   appears.
3. The dialog closes and the DataTable reloads.
4. The duplicate row disappears from the table.
5. Querying via API no longer returns the duplicate.
6. **`Template test frontend` (the original) is still present** in the
   table and in the API response — deleting the duplicate did not affect
   the original template or its disk.

### Cancel path

1. The dialog is open with **Stop and Delete** enabled.
2. They press **Close** (or the × button).
3. **No** call is made to
   `DELETE /api/v4/admin/item/templates/delete/{id}`.
4. The dialog closes and the row remains in the table.

---

## Scenario 9 — *manager tries to delete a template with cross-category derivatives*

> The backend only masks cross-category derivatives for the **manager** role
> (items in a different category get `category === '-'` and
> `unselectable = true`). This scenario therefore runs as `manager_e2e_01`
> (category: `default`).
>
> Seed: `template-s9-seed` (category: `default`) has one derived desktop
> (`desktop-s9-cross-cat-01`) in the `another` category. The test only
> presses **Close**; cross-category deletion is outside E2E scope.

### Given

1. `manager_e2e_01` (role: manager, category: `default`) is authenticated.
2. `template-s9-seed` is visible in the Templates table (same category as
   the manager).
3. `desktop-s9-cross-cat-01` exists with `parents: ["template-s9-seed"]`
   in the `another` category.

### When

1. They expand the `template-s9-seed` row and press **Delete**.
2. The `#modalDeleteTemplate` dialog opens.
3. The system fetches the tree via
   `GET /api/v4/admin/items/desktops/tree_list/{id}`; the backend masks
   the cross-category desktop with `category = '-'` / `unselectable = true`;
   `hasCrossCategoryItems` returns `true`.

### Then (current behaviour)

1. The **manager-warning** banner (`#manager-warning`) is shown inside the
   dialog.
2. The **cross-category-footer** message (`#cross-category-footer`) is
   visible.
3. The **Stop and Delete** button (`#send`) is **hidden** entirely
   (`populate_tree_template_delete` calls `$('#send').hide()` and also hides
   `#delete-warning`). There is no clickable delete control, so the manager
   **cannot** fire the DELETE request from the UI.
4. Pressing **Close** dismisses the dialog without any change, and **no**
   `DELETE /api/v4/admin/item/templates/delete/{id}` is made.

> The frontend block is in effect (the submit button is removed from the
> dialog), and the API remains the authoritative safety net: a direct call
> would still be rejected with HTTP **403** `{"description":"This template
> has derivatives not owned by your category"}`.

---

## Scenario 10 — *admin edits the hardware settings of a template*

### Scenario 10a — *happy path*

#### Given

1. `Template test frontend`'s detail row is expanded.

#### When

1. They press **Edit** (`btn-edit`).
2. The `#modalEditDesktop` dialog opens pre-populated with the
   template's current hardware configuration.
3. They change **Name** and **Description** to new values.
4. They press **Send**.

#### Then

1. `PUT /api/v4/item/template/{id}/edit` responds with status `< 400`.
2. A PNotify success notification *"Domain updated successfully"*
   appears.
3. The dialog closes and the DataTable reloads.
4. The row displays the updated name and description.
5. Querying via API, the template reflects the new values.

---

### Scenario 10b — *admin cancels the edit (no API call is made)*

#### Given

1. The `#modalEditDesktop` dialog is open with changes entered.

#### When

1. They press **Close** (or the × button) without pressing **Send**.

#### Then

1. **No** call is made to `PUT /api/v4/item/template/{id}/edit`.
2. The dialog closes.
3. The table row still shows the original name and description.

---

### Scenario 10c — *viewers selection persists after save*

#### Given

1. `Template test frontend`'s detail row is expanded.
2. The edit modal is opened; the current viewers configuration is noted
   (`browser_vnc` and `file_spice` checked per seed).

#### When

1. They uncheck one viewer (`file_spice`) via the iCheck checkbox.
2. They press **Send** — the API responds with status `< 400`.
3. They reopen the edit modal for the same template.

#### Then

1. The `file_spice` checkbox is **unchecked** — the change was persisted.
2. The `browser_vnc` checkbox remains checked (unmodified viewer unaffected).
3. `afterEach` `restoreSeed()` restores both viewers via the API.

---

## Scenario 11 — *admin opens the XML editor*

> The seed template (`template-test-001`) has a minimal but valid libvirt
> `<domain>` XML in `domains.json`, which allows `split_xml_sections` to
> parse and return sections without a real hypervisor.
>
> The **save** path (`POST /api/v4/admin/item/domains/xml_sections/{id}`)
> is not tested here because merging and persisting edited XML may require
> hypervisor-side validation. See the TODO comment in the test.

### Given

1. `Template test frontend`'s detail row is expanded.
2. The **XML** button (`btn-xml`) is visible (admin role only).

### When

1. They press **XML** (`btn-xml`).

### Then

1. `GET /api/v4/admin/item/domains/xml_sections/{id}` responds with
   status `< 400`.
2. The `#modalEditXmlSections` modal opens.
3. At least one section textarea (`.xml-section-textarea`) is present
   in the DOM — sections loaded correctly. Nav links exist but may be
   hidden by CSS depending on viewport.
4. No `.alert-danger` is visible inside the modal.
5. Pressing **Close** dismisses the modal with no side effects.

---

## Scenario 12 — *admin changes the owner of a template*

### Given

1. The seed template (`Template Test Frontend`) exists and its detail row
   is expanded.
2. At least two users with role `admin` or `manager` exist in the system
   (role `user` cannot own templates — the backend rejects it with
   `bad_request`).

### When — happy path

1. They press **Change owner** (`btn-owner`).
2. The `#modalChangeOwnerDomain` dialog opens.
3. They type at least 2 characters in the Select2 user-search field;
   the list populates via
   `POST /api/v4/admin/items/users/search`.
4. They select a different user and press **Send**.

### Then — happy path

1. `PUT /api/v4/item/template/{id}/change-owner/{new_user_id}` responds
   with status `< 400`.
2. A PNotify success notification *"Owner changed succesfully"* appears.
3. The dialog closes and the DataTable reloads.
4. The **User** column on the row reflects the new owner.

### Cancel path

1. The dialog is open with a user selected.
2. They press **Close**.
3. **No** call is made to `PUT /api/v4/item/template/{id}/change-owner/…`.
4. The **User** column is unchanged.

---

## Scenario 13 — *admin assigns a forced hypervisor to a template*

> Available to administrator role only.

### Given

1. A seed template exists with `forced_hyp = false`. Its detail row is
   expanded.

### When — assign

1. They press **Forced hyp** (`btn-forcedhyp`).
2. The `#modalForcedhyp` dialog opens; `#forcedhyp-check` is unchecked
   and `#forced_hyp` dropdown is hidden.
3. They tick `#forcedhyp-check`; the dropdown populates via
   `POST /api/v4/admin/items/table/hypervisors`.
4. They select a hypervisor and press **Send**.

### Then — assign

1. `PUT /api/v4/item/template/{id}/edit` with
   `{"forced_hyp": ["<hyp_id>"]}` responds with status `< 400`.
2. A PNotify success notification *"Forced hypervisor updated
   successfully"* appears.
3. The dialog closes. The `#send` success handler does **not** reload the
   DataTable, so the row reflects the change after the next table reload
   (or when a `template_data` changefeed event reaches `dtUpdateInsert`).
4. After reloading, the **Forced Hyper** column shows the selected
   hypervisor id.
5. Re-opening the modal shows `#forcedhyp-check` checked and the
   hypervisor pre-selected.

### Remove path

1. They reopen the dialog; `#forcedhyp-check` is now checked.
2. They uncheck it; the dropdown hides.
3. They press **Send**.
4. `PUT /api/v4/item/template/{id}/edit` with `{"forced_hyp": false}`
   responds with status `< 400`.
5. The **Forced Hyper** column reverts to `"-"`.

### Cancel path

1. The dialog is open with changes made.
2. They press **Close**.
3. **No** call is made to `PUT /api/v4/item/template/{id}/edit`.
4. The **Forced Hyper** column is unchanged.

---

## Scenario 14 — *admin assigns a favourite hypervisor to a template*

> Available to administrator role only.

### Given

1. A seed template exists with `favourite_hyp = false`. Its detail row
   is expanded.

### When — assign

1. They press **Favourite hyp** (`btn-favouritehyp`).
2. The `#modalFavouriteHyp` dialog opens; `#favouritehyp-check` is
   unchecked and `#favourite_hyp` dropdown is hidden.
3. They tick `#favouritehyp-check`; the dropdown populates via
   `POST /api/v4/admin/items/table/hypervisors`.
4. They select a hypervisor and press **Send**.

### Then — assign

1. `PUT /api/v4/item/template/{id}/edit` with
   `{"favourite_hyp": ["<hyp_id>"]}` responds with status `< 400`.
2. A PNotify success notification *"Favourite hypervisor updated
   successfully"* appears.
3. The dialog closes. The `#send` success handler does **not** reload the
   DataTable, so the row reflects the change after the next table reload
   (or when a `template_data` changefeed event reaches `dtUpdateInsert`).
4. After reloading, the **Favourite Hyper** column shows the selected
   hypervisor id.
5. Re-opening the modal shows `#favouritehyp-check` checked and the
   hypervisor pre-selected.

### Remove path

1. They reopen the dialog; `#favouritehyp-check` is now checked.
2. They uncheck it; the dropdown hides.
3. They press **Send**.
4. `PUT /api/v4/item/template/{id}/edit` with `{"favourite_hyp": false}`
   responds with status `< 400`.
5. The **Favourite Hyper** column reverts to `"-"`.

### Cancel path

1. The dialog is open with changes made.
2. They press **Close**.
3. **No** call is made to `PUT /api/v4/item/template/{id}/edit`.
4. The **Favourite Hyper** column is unchanged.

---

## Scenario 15 — *admin searches a template by UUID*

### Given

1. A duplicate template (created via API) exists with a proper UUID. The
   seed id `template-test-001` is not a UUID and would be rejected by the
   frontend, but the duplicate receives a backend-generated UUID. Because
   `restoreSeed` clears `isos`/`floppies` before each test, the duplicate
   inherits no dangling ISO reference and `get-info` returns 200 cleanly.
2. The `#domain-uuid-search` input and `#domain-uuid-search-btn` are
   visible in the toolbar.

### When — valid UUID

1. They paste the template's UUID into `#domain-uuid-search`.
2. They press `#domain-uuid-search-btn` (or the Enter key).

### Then — valid UUID

1. `GET /api/v4/item/desktop/{uuid}/get-info` is called.
2. The domain info modal (`#domain-info-modal`) opens showing the
   template's details.

### When — invalid UUID format

1. They enter `not-a-uuid` in `#domain-uuid-search` and press the
   button.

### Then — invalid UUID format

1. A PNotify error *"Invalid UUID"* appears.
2. **No** `showDomainInfo` call is made.

### When — empty input

1. They press the button with an empty `#domain-uuid-search`.

### Then — empty input

1. A PNotify error *"Please enter a template ID to search for."*
   appears.

---

## Scenario 16 — *admin validates row data for "Template test frontend"*

> This scenario verifies that the DataTable row for the specific seed
> template contains the expected values for all text columns, to confirm
> the table rendering is correct and the seed is in the expected state.

### Given

1. `Template test frontend` is present in the table and visible.

### When

1. The admin locates the row for `Template test frontend` in the
   `#domains` DataTable.

### Then

The row cells must match the known seed configuration exactly:

| Column | Expected value |
| --- | --- |
| Name | `Template test frontend` |
| Description | *(seed value)* |
| User | *(seed owner username)* |
| Category | *(seed category name)* |
| Group | *(seed group name)* |
| Enabled | Checkbox is **checked** |
| Derivatives | *(seed count)* |

---

## Scenario 17 — *admin opens the info modal for "Template test frontend"*

> Tests the info-circle button (`.info-control`, `data-domain-info`
> attribute) which calls `showDomainInfo(id)` and opens the
> `#domain-info-modal`. The same modal is also reachable via UUID
> search (S15).

### Given

1. `Template test frontend` row is visible in the table.

### When

1. They press the info-circle button (`.info-control`) on the
   `Template test frontend` row.

### Then

1. `GET /api/v4/item/desktop/{id}/get-info` responds with status `< 400`.
2. The `#domain-info-modal` opens and shows at minimum:

   | Field | Expected value |
   | --- | --- |
   | Title (modal header) | `Template test frontend` |
   | ID | *(seed id, copyable)* |
   | Name | `Template test frontend` |
   | Kind | `template` |

3. Pressing **Close** dismisses the modal with no side effects.

---

## Scenario 18 — *admin expands the detail panel for "Template test frontend"*

> Tests the expand button (`.details-control`, fa-plus icon) that
> reveals the inline admin detail panel with hardware specs, alloweds,
> and action buttons. Validates the panel renders with content that
> matches the seed configuration.

### Given

1. `Template test frontend` row is visible in the table.

### When

1. They click the expand button (`.details-control`) on the
   `Template test frontend` row.

### Then

1. The row expands inline showing the `admin-template-detail-domain`
   panel.
2. The **Status detailed info** section (`#status-detail-{id}`) is
   visible.
3. The hardware section (from `domain_hardware.html`) renders with
   values matching the seed's configured hardware (vCPUs, RAM, boot
   order, etc.).
4. The **Alloweds** section renders showing the seed's access
   permissions (users, groups, roles).
5. The action buttons present are: **Forced hyp**, **Favourite hyp**,
   **Duplicate**, **Edit**, **XML**, **Change owner**, **Delete**.
6. There is **no** `btn-jumperurl` (Viewer share link) button in the
   panel.
7. Clicking the expand button again collapses the row.

---

## Scenario 19 — *admin edits template permissions via the Shares button*

### Given

1. `Template test frontend` is visible in the table.

### When — happy path

1. They click the `btn-alloweds` button in the **Shares** column of the
   `Template test frontend` row.
2. The alloweds modal opens showing the current permission assignments
   (users, groups, roles, categories).
3. They add or remove a permission entry and confirm.

### Then — happy path

1. The alloweds API call is made (via `modalAllowedsFormShow`) and
   responds with status `< 400`.
2. The modal closes successfully.
3. The permissions are updated.

### Cancel path

1. The alloweds modal is open.
2. They press **Close** without making any change.
3. **No** API call to modify alloweds is made.
4. The template's permissions are unchanged.

---

## Cleanup (afterEach)

1. The duplicate template name created by this test is recovered from
   the metadata.
2. If a template with that name exists (looked up via
   `POST /api/v4/admin/items/domains` with `{kind: "template"}`), it is
   deleted via `DELETE /api/v4/admin/item/templates/delete/{id}`.
3. If a forced or favourite hypervisor was set on a seed template during
   a test, the original value (`false`) is restored via the edit API
   before cleanup finishes.
4. If the seed template name/description was changed by S10a, restore
   original values via the edit API.
5. Cleanup errors are silenced to avoid masking an earlier test failure.

---

## Expected results — global summary

| Scenario | Covered in test? | Key checks |
| --- | --- | --- |
| S1 — Table loads | ✅ | Columns present, expand & info buttons per row, toolbar visible |
| S2 — Show/hide disabled | ✅ | Button label toggles, disabled rows appear/disappear on redraw |
| S3 — Enable template | ✅ | Confirmation → API ok → checkbox checked → persisted |
| S4 — Disable cancel | ✅ | Cancel → no API call → checkbox reverts |
| S5 — Disable template | ✅ | Confirmation → API ok → checkbox unchecked → persisted |
| S6 — Duplicate (happy + cancel) | ✅ | Dialog pre-filled, API ok, new row; cancel → no POST |
| S7 — Duplicate invalid name | ✅ | Parsley blocks Send; no POST; error shown |
| S8 — Delete duplicate (happy + cancel) | ✅ | Tree empty, API ok, duplicate row gone; **original template still present**; cancel → no DELETE |
| S9 — Delete blocked (cross-category) | ✅ (manager role) | Warning + cross-category footer shown; Stop-and-Delete (#send) button hidden → no DELETE possible from the UI |
| S10a — Edit happy path | ✅ | Dialog pre-filled, API ok, row updated, persisted |
| S10b — Edit cancel | ✅ | Cancel → no PUT call → row unchanged |
| S10c — Edit viewers | ✅ | Uncheck viewer → save → reopen → change persisted |
| S11 — XML editor | happy path | Modal opens; sections render; no error; close works |
| S12 — Change owner (happy + cancel) | ✅ | Select2 search, API ok, column updated; cancel → no PUT |
| S13 — Forced hypervisor | ✅ (all paths) | Cancel path: no PUT; assign: API ok, column updated; remove: API ok, column reverts |
| S14 — Favourite hypervisor | ✅ (all paths) | Cancel path: no PUT; assign: API ok, column updated; remove: API ok, column reverts |
| S15 — UUID search | ✅ (all 3 paths) | Valid UUID → duplicate id used (valid UUID, no dangling ISO) → modal opens; invalid format → error; empty → error |
| S16 — Row data validation | ✅ | Seed row matches expected name, description, user, category, group |
| S17 — Info modal | ✅ | `get-info` returns 200; seed has no dangling ISO (restoreSeed clears isos/floppies); modal opens with correct data |
| S18 — Detail panel | ✅ | Panel expands with hardware, alloweds, action buttons; no jumperurl button |
| S19 — Permissions (alloweds) | ✅ | Modal opens; happy path: group added → API ok → success notification; cancel → no change |

## APIs touched by the flows (reference)

- `POST   /api/v4/admin/items/domains` — load the table.
  Body `{"kind": "template"}`; response: array of template objects.
- `PUT    /api/v4/item/template/{id}/set-enabled` — enable/disable.
  Body `{"enabled": true|false}`.
- `POST   /api/v4/item/template/{id}/duplicate` — duplicate.
  Body: name, description, enabled, allowed, user_id.
- `GET    /api/v4/item/template/{id}/get-info` — pre-fill duplicate
  modal and the info modal. Response: name, description, kind, status,
  hyp_started, storage_id, owner, interfaces.
- `GET    /api/v4/item/desktop/{id}/get-info` — called by
  `showDomainInfo(id)` for the info modal (uses the desktop endpoint
  for both templates and desktops).
- `DELETE /api/v4/admin/item/templates/delete/{id}` — delete template.
- `GET    /api/v4/admin/items/desktops/tree_list/{id}` — fetch
  derivative tree before delete.
- `PUT    /api/v4/item/template/{id}/edit` — edit hardware, name,
  description, forced_hyp, favourite_hyp.
- `PUT    /api/v4/item/template/{id}/change-owner/{user_id}` — change
  owner.
- `POST   /api/v4/admin/items/users/search` — user-search for
  change-owner. Body `{term}`.
- `POST   /api/v4/admin/items/table/hypervisors` — hypervisor list for
  forced/favourite modals. Body `{pluck: ["id","hostname"]}`.

## Relevant database state

- `domains` table: `enabled`, `forced_hyp`, `favourite_hyp`, `name`,
  `description` are the main fields mutated by these tests.
- Cross-category detection uses the `category` field of child domains
  returned by `tree_list`; a value of `'-'` or `unselectable = true`
  triggers the delete block.
- `Template test frontend` must exist in the seed and must be in
  `Stopped` state with a known, stable configuration.

## Cases not covered (future)

- Delete a template that has **same-category** derivatives (tree is
  non-empty but no cross-category block): requires a seed with nested
  desktops under the template.
- Share link (jumper URL): `btn-jumperurl` is absent from the admin
  templates detail panel (`templates_detail.html`); the feature only
  exists in the user-facing desktops view.
- Real-time Socket.io updates (`template_data`, `template_delete`) while
  the table is open.
