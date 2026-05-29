# Media management in webapp

Human-readable functional specification of the **page load**, **upload from URL**,
**row actions**, and **status filtering** flows for the media administration panel.
Serves as the contract for the E2E test `tests/webapp/media.spec.js`.

## Scope

- **Component**: administration panel.
- **Screen**: **Media** — `/isard-admin/admin/isard-admin/media`
- **Actions covered**:
  - Page loads the `#media` DataTable with Downloaded media.
  - Status dropdown populates and filters `#mediaOtherTable` by status.
  - Expanding a media row shows a detail table of domains using it.
  - Upload from URL: form opens with all required fields; client-side
    validation blocks invalid URL (http), invalid name (empty, too short,
    too long), and unselected type.
  - Delete a Downloaded media: confirmation modal lists affected domains,
    DELETE API is called, row disappears.
  - Create desktop from media: modal opens with the media pre-selected
    (ISO and qcow2 variants).
  - Check media status: PNotify confirm triggers PUT check endpoint.
  - Show last task info: GET task endpoint, PNotify with task detail.
  - Alloweds: modal opens for a Downloaded ISO media.
  - Change owner: modal opens and Select2 search loads results.
  - Secondary table (`#mediaOtherTable`) row actions: expand, check, task,
    delete (for whichever status is currently selected).
- **Out of scope**: physical media rescan (requires storage host), socket
  real-time update events, actual file download progress, local file upload
  (UI is commented out), desktop creation hardware configuration detail,
  abort/retry actions (require media in Downloading/failed states),
  change-owner form submission (requires a second valid user).

## Common role and prerequisites

| Element | Expected value |
| --- | --- |
| Role | Administrator of the `default` category |
| Session | Logged in to the webapp |
| Tables | `#media` DataTable has loaded and is visible |

## Common data

| Field | Sample value | Notes |
| --- | --- | --- |
| URL | `https://example.com/test.iso` | Must start with `https://`; must contain a filename |
| Name | `e2e-media-<worker>-<timestamp>` | 4–60 chars; letters, digits, space, `.`, `-`, `_`, accents |
| Type | `iso` | `iso`, `floppy`, or `qcow2` |
| Description | `e2e test media` | Optional, max 255 chars |

---

## SECTION A — Page load and status filtering

### Scenario A1 — *Downloaded media table loads on page visit*

#### Given

1. The administrator navigates to `/isard-admin/admin/isard-admin/media`.

#### When

1. The page finishes loading.

#### Then

1. `GET /api/v4/admin/items/media/Downloaded` responds with status `< 400`.
2. The `#media` DataTable is visible and contains at least the header row.
3. The status dropdown (`#status`) is visible.

---

### Scenario A2 — *status dropdown populates with non-Downloaded statuses*

#### Given

1. The page has loaded and the `#media` DataTable is visible.

#### When

1. `GET /api/v4/admin/item/media/status` completes successfully.

#### Then

1. The `#status` dropdown is enabled (not `disabled`).
2. The dropdown contains at least the placeholder option plus one or more
   statuses returned by the API (e.g. `Downloading`, `Available`,
   `DownloadFailed`).
3. `Downloaded` is **not** present in the dropdown (it is filtered out by
   the JS: `notShownStatus = ['Downloaded']`).

---

### Scenario A3 — *selecting a status in the dropdown loads the secondary table*

#### Given

1. The `#status` dropdown has at least one non-placeholder option.

#### When

1. The admin selects a status from the `#status` dropdown.

#### Then

1. `GET /api/v4/admin/items/media/{status}` is called for the selected status
   and responds with status `< 400`.
2. The `#mediaOtherTable` DataTable becomes visible and renders the result
   (may be empty if no media has that status).

---

## SECTION B — Upload from URL

### Scenario B1 — *"Upload from URL" button opens the add modal*

#### Given

1. The admin is on the media page.

#### When

1. They press the **Upload from URL** button.

#### Then

1. The `#modalAddMedia` dialog opens.
2. The following fields are present and empty: `#url`, `#name`.
3. The `#kind` dropdown defaults to the placeholder ("Choose..").
4. The **Start download** button is visible in the modal footer.

---

### Scenario B2 — *Parsley blocks submission when URL uses http://*

#### Given

1. `#modalAddMedia` is open.
2. The name and type are filled with valid values.

#### When

1. They enter `http://example.com/test.iso` in the **URL** field (not https).
2. They press **Start download**.

#### Then

1. Parsley validation blocks the submission.
2. The `#url` field gets the `parsley-error` CSS class.
3. **No** call is made to `POST /api/v4/item/media`.
4. The dialog stays open.

---

### Scenario B3 — *Name auto-fills with URL filename when the field is focused while empty*

> **Note:** The media.js focus handler (`$('#modalAddMediaForm #name').focus(...)`)
> populates `#name` with the last path segment of the URL whenever `#name` is
> focused while empty and `#url` already has a value. As a side-effect, if
> Parsley's `validate()` focuses the first invalid field (which is `#name` when
> empty), it triggers this auto-fill. The form therefore cannot be submitted with
> an empty name when a URL is present — making B3 a test of the auto-fill
> feature rather than a blocked-empty-name scenario.

#### Given

1. `#modalAddMedia` is open.
2. The **URL** field is filled with `https://example.com/test.iso`.
3. The **Name** field is empty.

#### When

1. The admin clicks (focuses) the `#name` field.

#### Then

1. `#name` is auto-filled with `test.iso` (the last path segment of the URL).

---

### Scenario B4 — *Parsley blocks submission when Name is shorter than 4 characters*

#### Given

1. `#modalAddMedia` is open.
2. URL and type are valid.

> **Implementation note:** `#name` must be filled **before** `#url` in the test.
> If `#url` is filled first and then `#name` is focused while empty, the auto-fill
> handler (see B3) sets `#name` to the URL filename. Parsley's `validate()` then
> re-focuses `#name`, the auto-fill fires again with a value that passes length
> validation, and `isValid()` returns `true` — causing the POST to fire.
> Filling `#name` first (while `#url` is still empty) prevents the auto-fill.

#### When

1. They enter `abc` (3 characters) in the **Name** field.
2. They press **Start download**.

#### Then

1. Parsley blocks the submission with a length error.
2. The `#name` field gets the `parsley-error` CSS class.
3. **No** call is made to `POST /api/v4/item/media`.
4. The dialog stays open.

---

### Scenario B5 — *Parsley blocks submission when Name exceeds 60 characters*

#### Given

1. `#modalAddMedia` is open.
2. URL and type are filled with valid values.

> **Implementation note:** same as B4 — `#name` must be filled before `#url`
> to avoid the auto-fill side effect (see B3 and B4 notes).

#### When

1. They enter a name of 61 or more characters in the **Name** field.
2. They press **Start download**.

#### Then

1. Parsley blocks the submission with a length error.
2. The `#name` field gets the `parsley-error` CSS class.
3. **No** call is made to `POST /api/v4/item/media`.
4. The dialog stays open.

---

### Scenario B6 — *Parsley blocks submission when Type is not selected*

#### Given

1. `#modalAddMedia` is open.
2. URL and name are filled with valid values.
3. The **Type** (`#kind`) dropdown is still on the "Choose.." placeholder (value `""`).

#### When

1. They press **Start download**.

#### Then

1. Parsley blocks the submission (required field).
2. The `#kind` field gets the `parsley-error` CSS class.
3. **No** call is made to `POST /api/v4/item/media`.
4. The dialog stays open.

---

### Scenario B7 — *submitting a valid form fires POST and closes the modal*

> The URL is fetched at runtime from the IsardVDI repository catalogue via
> `GET /api/v4/admin/items/downloads/media`, looking up the entry named by
> `REPO_MEDIA_NAME` in the spec. The test only verifies that the API call is
> made and the modal closes — it does not wait for the download to complete.
>
> The test is skipped when the named entry is not found in the catalogue
> (e.g. CI without network access or before the media is published).
> To switch to a smaller media, update the `REPO_MEDIA_NAME` constant.

#### Given

1. `#modalAddMedia` is open.
2. A valid HTTPS URL to an ISO-like resource is available.

#### When

1. They fill in a valid **URL**, a valid **Name**, and select **ISO CD/DVD**.
2. They press **Start download**.

#### Then

1. `POST /api/v4/item/media` is called with status `< 400`.
2. The modal closes.
3. A "Created" success PNotify appears.

---

## SECTION C — Downloaded media row actions

> Scenarios C1–C7 require at least one media item with status `Downloaded`
> to exist in the system. The `empty-iso` DB fixture guarantees this
> condition on every test run. The skip guards are a defensive fallback only.
> C2 uses a separate `e2e-delete-target` fixture (excluded from
> `listDownloadedMedia`) so that C6's check never transitions it to `deleted`.
>
> **Execution order within section C**: C7 runs immediately before C6 because
> `PUT .../check` (C6) can transition the media from `Downloaded` to `deleted`
> when no physical file exists (test environment). All tests that need a
> Downloaded ISO — including C7 — must therefore complete before C6 runs.
> C2 is placed last for the same reason: it deletes its own fixture and must
> not run before any other C test that needs a Downloaded row.
>
> **qcow2 vs ISO button differences** (reflected in C3, C6, C7): for
> `Downloaded` qcow2 media the JS renders only `btn-createfromiso` and
> `btn-delete` — there is no `btn-check` or `btn-task`. ISO and Floppy
> media include all buttons. Scenarios C6–C7 use ISO media only.

### Scenario C1 — *expanding a row shows the domains detail table*

#### Given

1. At least one Downloaded media row exists in `#media`.

#### When

1. The admin clicks the **expand** (`+`) button on the first media row.

#### Then

1. `GET /api/v4/admin/items/media/domains/{media_id}` is called and responds
   with status `< 400`.
2. A child table (`#cl{media_id}`) appears below the row showing the
   domains that use this media (may be empty if no domain references it).
3. Clicking the expand button again hides the child table.

---

### Scenario C2 — *delete a Downloaded media shows the confirmation modal and removes the row*

#### Given

1. A Downloaded media item exists in `#media`.

#### When

1. The `#media_filter` search box is filled with the media name so the row is
   visible regardless of pagination.
2. They click the **delete** (×) icon on the media row.
3. `#modalDeleteMedia` opens (the `GET /api/v4/item/media/{media_id}/get-desktops`
   request fires to populate affected domains, if any).
4. They press **Delete media**.

#### Then

1. `DELETE /api/v4/item/media/{media_id}` responds with status `< 400`.
2. The modal closes.
3. After navigating back to the media page (fresh load), the media row is
   absent from `#media`. The row is not removed client-side immediately because
   removal relies on a WebSocket event; the fresh load confirms the deletion
   is reflected in the API response.

---

### Scenario C3 — *"Create desktop from media" opens the creation modal pre-filled*

> Only available for Downloaded ISO media (`kind` not starting with `qcow`).

#### Given

1. A Downloaded ISO (non-qcow) media row exists in `#media`.

#### When

1. They click the **Create desktop from media** (desktop icon) button on
   the row.

#### Then

1. `#modalAddFromMedia` opens.
2. The hidden `#media` input inside the modal contains the media's id.
3. The `#media_name` label shows the media's name.
4. The OS Hardware Template section (`#modal_add_install`) is visible and
   populated from `GET /api/v4/items/media/installs`.

---

### Scenario C4 — *Alloweds button opens the alloweds modal*

> Only available for Downloaded ISO (non-qcow) media.

#### Given

1. A Downloaded ISO media row exists in `#media`.

#### When

1. They click the **Alloweds** (users icon) button on the row.

#### Then

1. `POST /api/v4/item/allowed/table/media` is called with the media id and responds
   with status `< 400`.
2. `#modalAlloweds` becomes visible.

---

### Scenario C5 — *Change owner modal opens and Select2 search returns results*

> Only available for Downloaded ISO (non-qcow) media.

#### Given

1. A Downloaded ISO media row exists in `#media`.

#### When

1. They click the **Change owner** (exchange icon) button on the row.
2. `#modalChangeOwnerMedia` opens.
3. They type at least 2 characters into the **New owner** Select2 search box.

#### Then

1. `POST /api/v4/items/alloweds/term/users` is called with the typed term
   and responds with status `< 400`.
2. The Select2 dropdown shows at least one result.

---

### Scenario C6 — *Check media status opens confirmation and calls check endpoint*

> Only available for Downloaded ISO (non-qcow) media (`btn-check`).
> qcow2 Downloaded media does not render this button.

#### Given

1. A Downloaded ISO media row exists in `#media`.

#### When

1. They click the **Check media status** (refresh icon, `btn-check`) button on the row.
2. A PNotify confirmation dialog appears asking "Do you really want to update the media status?".
3. They click **Ok** to confirm.

#### Then

1. `PUT /api/v4/admin/item/media/{media_id}/check` is called (the request
   fires — the HTTP status is not asserted because test environments without
   a real hypervisor may return 428 when no RQ worker is available).

---

### Scenario C7 — *Show last task info fetches task and shows PNotify*

> Available for all Downloaded ISO (non-qcow) media rows (`btn-task`).
> qcow2 Downloaded media does not render this button.

#### Given

1. A Downloaded ISO media row exists in `#media` and has a `task` id
   associated (i.e. the row data contains a non-null `task` field).

#### When

1. They click the **Show last task info** (tasks icon, `btn-task`) button on the row.

#### Then

1. `GET /api/v4/task/{task_id}` is called and responds with status `< 400`.
2. A PNotify appears whose title matches `last task info`.

---

## SECTION D — Secondary table (`#mediaOtherTable`) row actions

> Scenarios D1–D3 require that a status with at least one media item has
> been selected in the `#status` dropdown (i.e. `#mediaOtherTable` is
> visible and non-empty). If no media exists for any non-Downloaded status,
> these tests are skipped.

### Scenario D1 — *Expanding a row in the secondary table shows domains detail*

#### Given

1. `#mediaOtherTable` is visible and has at least one row.

#### When

1. The admin clicks the **expand** (`+`) button on the first row of
   `#mediaOtherTable`.

#### Then

1. `GET /api/v4/admin/items/media/domains/{media_id}` is called and responds
   with status `< 400`.
2. A child table (`#cl{media_id}`) appears below the row.
3. Clicking the expand button again hides the child table.

---

### Scenario D2 — *Check media status from the secondary table*

#### Given

1. A row exists in `#mediaOtherTable` (any status).

#### When

1. They click `btn-check` on a row.
2. They confirm the PNotify dialog.

#### Then

1. `PUT /api/v4/admin/item/media/{media_id}/check` is called (the request
   fires — the HTTP status is not asserted because test environments without
   a real hypervisor may return 428 when no RQ worker is available).

---

### Scenario D3 — *Show last task info from the secondary table*

#### Given

1. A row exists in `#mediaOtherTable` with a non-null `task` field.

#### When

1. They click `btn-task` on the row.

#### Then

1. `GET /api/v4/task/{task_id}` responds with status `< 400`.
2. A PNotify of type `info` appears with the task detail.

---

## Cleanup

**afterEach**: attempts `DELETE /api/v4/item/media/{id}` for any media created
by B7. The call may return 428 (`unable_to_delete_downloading_media`) if the
download is still in progress — the error is silenced so it does not mask real
test failures.

**beforeAll**: deletes all leftover `e2e-media-<worker>-*` entries from
previous runs (both Downloaded and non-Downloaded) before the suite starts.
This is the authoritative cleanup step, since afterEach cannot delete media
that is still actively downloading.

**Known limitations**:

- The `DELETE` endpoint returns 428 for media in `deleted` status
  (`unable_to_delete_downloading_media`). Entries that reach `deleted` state
  (e.g. after a check with no physical file) cannot be removed by the tests
  and accumulate in the DB across runs. They do not affect test correctness
  because `loadOtherTable` explicitly excludes `deleted` from its candidates.

- Media created by B7 starts downloading immediately. If the suite runs only
  once (e.g. in CI), `afterEach` cannot delete it (428 — still downloading)
  and `beforeAll` never gets another chance to retry. The entry remains in the
  DB until a subsequent run where `beforeAll` finds it in a deletable state.
  If B7 runs again before the previous entry finishes downloading, a new entry
  is created and both accumulate. A backend force-delete or abort+delete flow
  would be needed to fully resolve this. B7 is skipped only when
  `REPO_MEDIA_NAME` is not found in the repository catalogue — which happens
  when the runner has no outbound internet access to `repository.isardvdi.com`.
  In environments where the repository is reachable (including CI runners with
  internet access, given the `resources.code` and `resources.url` already set
  in `config.json`), B7 runs and the accumulation problem applies equally.

---

## Expected results — global summary

| Scenario | Covered in test? | Key checks |
| --- | --- | --- |
| A1 — Page loads, #media DataTable visible | ✅ | GET Downloaded ok, table visible |
| A2 — Status dropdown populates | ✅ | Dropdown enabled, options from API, Downloaded excluded |
| A3 — Select status loads #mediaOtherTable | ✅ | GET by status ok, secondary table visible |
| B1 — Upload from URL modal opens | ✅ | Modal visible, fields empty, Start download button present |
| B2 — http:// URL blocked by Parsley | ✅ | parsley-error on #url, no POST |
| B3 — Name auto-fills from URL filename on focus | ✅ | #name gets filename from URL when focused while empty |
| B4 — Short name (<4 chars) blocked by Parsley | ✅ | parsley-error on #name, no POST |
| B5 — Long name (>60 chars) blocked by Parsley | ✅ | parsley-error on #name, no POST |
| B6 — Type not selected blocked by Parsley | ✅ | parsley-error on #kind, no POST |
| B7 — Valid form fires POST and closes modal | ⏭ `skip` if `REPO_MEDIA_NAME` not in catalogue | POST ok, modal closes, success PNotify |
| C1 — Expand row shows domains table | ✅ (skip if table empty) | GET domains ok, child table visible |
| C2 — Delete Downloaded media | ✅ | Uses `e2e-delete-target` fixture, DataTable filter, confirm modal, DELETE ok, row absent after page reload |
| C3 — Create desktop modal opens pre-filled | ✅ (skip if no ISO media) | Modal open, media id pre-filled, installs table loaded |
| C4 — Alloweds modal opens | ✅ (skip if no ISO media) | POST item/allowed/table/media ok, modal visible |
| C5 — Change owner Select2 search | ✅ (skip if no ISO media) | POST items/alloweds/term/users ok, results shown |
| C6 — Check media status (ISO Downloaded) | ✅ (skip if no ISO media) | Confirm PNotify, PUT check fires (status not asserted) |
| C7 — Show last task info (ISO Downloaded) | ✅ (skip if no ISO media with task) | GET task ok, PNotify title matches "last task info" |
| D1 — Expand row in secondary table | ✅ (skip if secondary table empty) | GET domains ok, child table visible |
| D2 — Check status from secondary table | ✅ (skip if secondary table empty) | Confirm PNotify, PUT check fires (status not asserted) |
| D3 — Show task info from secondary table | ✅ (skip if secondary table empty) | GET task ok, info PNotify shown |

## APIs touched by the flows (reference)

- `GET    /api/v4/admin/items/media/Downloaded` — list Downloaded media (main table, A1)
- `GET    /api/v4/admin/items/media/{status}` — list media by status (secondary table, A3)
- `GET    /api/v4/admin/item/media/status` — list available statuses with counts (A2)
- `GET    /api/v4/admin/items/downloads/media` — repository catalogue of downloadable media (B7)
- `POST   /api/v4/item/media` — upload media from URL (B7)
- `DELETE /api/v4/item/media/{media_id}` — delete media (C2)
- `GET    /api/v4/admin/items/media/domains/{media_id}` — domains using a media item (C1, D1)
- `GET    /api/v4/item/media/{media_id}/get-desktops` — domains for delete modal (C2)
- `PUT    /api/v4/admin/item/media/{media_id}/check` — check/refresh media status (C6, D2)
- `GET    /api/v4/task/{task_id}` — fetch last task info for a media item (C7, D3)
- `PUT    /api/v4/item/media/{media_id}/abort` — abort active download (out of scope)
- `PUT    /api/v4/item/media/{media_id}/download` — retry failed download (out of scope)
- `PUT    /api/v4/item/media/{media_id}/change-owner/{user_id}` — change owner (out of scope: submission)
- `POST   /api/v4/item/allowed/table/media` — load current alloweds for a media item (C4)
- `POST   /api/v4/items/alloweds/term/users` — Select2 user search for change owner (C5)
- `GET    /api/v4/items/media/installs` — OS hardware templates for desktop creation (C3)
- `POST   /api/v4/item/desktop/from-media` — create desktop from media (out of scope: submission)
