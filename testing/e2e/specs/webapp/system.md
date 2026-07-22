# System Configuration (admin webapp)

Functional, traceable specification for the **Config → System** page in the legacy admin webapp.
It serves as the contract for Playwright E2E tests under `testing/e2e/tests/webapp/`.

## Context

- **Page**: `/isard-admin/admin/system`
- **Template**: `webapp/webapp/webapp/templates/admin/pages/system.html`
- **Main JS**: `webapp/webapp/webapp/static/admin/js/system.js`
- **SMTP JS**: `webapp/webapp/webapp/static/js/smtp.js`
- **Maintenance text modal**: `webapp/webapp/webapp/templates/admin/pages/system_modals.html`
- **SMTP forms**: `webapp/webapp/webapp/templates/snippets/smtp.html` + `smtp_form.html`

## Resource / action matrix

| Resource | View | Edit | Save | UI validations | Notes |
| --- | --- | --- | --- | --- | --- |
| Maintenance mode | ✅ | ✅ (checkbox) | ✅ (`PUT /api/v4/maintenance`) | No form validation | Must persist after reload |
| Maintenance text | ✅ (preview) | ✅ (modal) | ✅ (`PUT /api/v4/maintenance/text`) | Validation exists in UI but no dedicated negative test in current suite | Preview uses line breaks (`white-space: pre-line`) |
| SMTP configuration | ✅ (read-only form) | ✅ (modal) | ✅ (`PUT /api/v4/smtp`) | `host`, `port`, `username`, `password` required; `port` 1..65535 | **Do not include** connection testing in this scope |

## Roles, permissions, and preconditions

| Item | Expected value |
| --- | --- |
| Main role | Authenticated admin |
| Route access | Admin only (`@isAdmin` in `AdminViews.py`) |
| Non-admin behavior | Must not use this page; direct URL access redirects to `/login` |
| Required initial state | API available and valid admin session |

> **Current suite scope note**: the non-admin permissions scenario was intentionally removed from `system.spec.js` and is not currently automated in this file.

## Minimum test data

- Maintenance text:
  - `title`: `E2E maintenance title <timestamp>`
  - `body`: `Line 1 <timestamp>\nLine 2 <timestamp>`
- SMTP:
  - `enabled`: `true` or `false` depending on scenario
  - `host`: `smtp.e2e.local`
  - `port`: `587`
  - `username`: `e2e-user`
  - `password`: `e2e-password`
  - `from`: `"Isard E2E" <e2e@example.local>`

> Capture an initial snapshot of maintenance + text + smtp through API at test start, and restore it during cleanup.

---

## Scenarios

### A1 — initial load of the System page

- **Preconditions**: Admin is logged in.
- **UI steps**:
  1. Navigate to `Config → System`.
  2. Wait until the maintenance spinner disappears (`#maintenance_spinner`) and wrapper appears (`#maintenance_wrapper`).
  3. Verify that preview panel (`#preview`) and SMTP block (`#form-smtp-show`) exist.
- **Expected UI**:
  - The page renders these sections: **Maintenance mode**, **Maintenance text**, **SMTP configuration**.
- **Expected network**:
  - `GET /api/v4/maintenance/status` → **2XX**.
  - `GET /api/v4/maintenance/text` → **2XX**.
  - `GET /api/v4/smtp` → **2XX**.
- **Cleanup**: not required.

### A2 — enable maintenance mode

- **Preconditions**: Maintenance checkbox is visible.
- **UI steps**:
  1. If unchecked, check `#maintenance_checkbox`.
- **Expected UI**:
  - During update: checkbox is hidden and spinner is shown.
  - After response: checkbox is shown again and remains checked.
- **Expected network**:
  - `PUT /api/v4/maintenance` → **2XX**.
  - Current UI sends a boolean payload; validate real 2XX behavior without assuming response shape.
- **Cleanup**:
  - Restore original maintenance state at test end.

### A3 — disable maintenance mode + persistence after reload

- **Preconditions**: Maintenance is enabled (from A2 or setup).
- **UI steps**:
  1. Uncheck `#maintenance_checkbox`.
  2. Wait for spinner to finish.
  3. Reload page (`page.reload()`).
- **Expected UI**:
  - After save: checkbox is unchecked.
  - After reload: checkbox is still unchecked (persisted state).
- **Expected network**:
  - `PUT /api/v4/maintenance` → **2XX**.
  - On reload, `GET /api/v4/maintenance/status` → **2XX** and consistent with final checkbox state.
- **Cleanup**:
  - Restore original state.

### A4 — open maintenance text modal with prefilled values

- **Preconditions**: System page is open.
- **UI steps**:
  1. Click `#btn-edit-maintenance-text`.
- **Expected UI**:
  - Modal `#modalEditMaintenanceText` opens.
  - Inputs `#title` and `#text` are prefilled.
- **Expected network**:
  - On modal open: `GET /api/v4/maintenance/text` → **2XX**.
- **Cleanup**: close modal if left open.

### A5 — edit maintenance text and verify preview

- **Preconditions**: Maintenance text modal is open.
- **UI steps**:
  1. Fill `#title` and `#text` with new values (including a line break in body).
  2. Click `#modalEditMaintenanceText #send`.
  3. Wait for modal to close.
- **Expected UI**:
  - Success notification appears (`Updated`).
  - `#preview` shows exactly:
    - first line = new `title`
    - blank line
    - `body` with visible line breaks.
- **Expected network**:
  - `PUT /api/v4/maintenance/text` → **2XX**.
  - After save, UI calls `GET /api/v4/maintenance/text` to refresh preview → **2XX**.
- **Cleanup**:
  - Restore original maintenance text.

### A6 — initial SMTP display in read-only form

- **Preconditions**: System page is open.
- **UI steps**:
  1. Wait for `#form-smtp-show` to load.
- **Expected UI**:
  - SMTP fields are shown in disabled mode.
  - `enabled`, `host`, `port`, `username`, `from` should render correctly when present in backend data.
- **Expected network**:
  - `GET /api/v4/smtp` → **2XX**.
- **Notes**:
  - `password` may be hidden/redacted by backend; do not require secret visibility in read-only view.

### A7 — open SMTP modal and verify prefill

- **Preconditions**: System page is open.
- **UI steps**:
  1. Click `#btn-edit-smtp`.
- **Expected UI**:
  - `#modal-smtp-configuration` opens.
  - Editable fields are prefilled from backend data.
- **Expected network**:
  - On modal open, `GET /api/v4/smtp` runs → **2XX**.
- **Cleanup**: close modal if needed.

### A8 — edit and save SMTP (no connection test)

- **Preconditions**: SMTP modal is open.
- **UI steps**:
  1. Modify `enabled`, `host`, `port`, `username`, `password`, `from`.
  2. Click `#smtp-save`.
- **Expected UI**:
  - “Sending” notice appears, then success (`SMTP configured successfully`).
  - Modal closes.
  - Read-only panel (`#form-smtp-show`) refreshes and reflects updated non-secret values.
- **Expected network**:
  - `PUT /api/v4/smtp` → **2XX**.
  - After save, refresh with `GET /api/v4/smtp` → **2XX**.
- **Cleanup**:
  - Restore original SMTP configuration at test end.
- **Notes**:
  - **Out of scope**: `#smtp-test` button / `POST /api/v4/smtp/test`.

### A9 — SMTP client-side validations

- **Preconditions**: SMTP modal is open.
- **UI steps**:
  1. Try saving with empty `host`.
  2. Try `port` out of range (0 or 70000).
  3. Try empty `username` or `password`.
- **Expected UI**:
  - Parsley shows validation errors and blocks valid save.
- **Expected network**:
  - No `PUT /api/v4/smtp` should be considered successful when form is invalid.
- **Cleanup**: restore valid values.

---

## Risks / known issues to report

1. **Possible maintenance contract mismatch in legacy UI**:
   - `system.js` handles `GET /api/v4/maintenance/status` as a raw boolean.
   - OpenAPI defines `MaintenanceStatusResponse` (`{"enabled": bool}`).
   - Without compatibility mapping, checkbox visual state may be wrong.

2. **Possible maintenance text contract mismatch**:
   - UI expects `data.title` / `data.body` from `GET /api/v4/maintenance/text`.
   - OpenAPI documents `MaintenanceTextGetResponse` with a `text` container.
   - If backend returns strict OpenAPI shape, preview/modal field mapping may fail.

3. **SMTP password on read**:
   - Backend may hide `password` in `GET /api/v4/smtp` for admin web sessions.
   - E2E must not require password visibility in read-only panel.

## APIs touched by this screen

- `GET /api/v4/maintenance/status`
- `PUT /api/v4/maintenance`
- `GET /api/v4/maintenance/text`
- `PUT /api/v4/maintenance/text`
- `GET /api/v4/smtp`
- `PUT /api/v4/smtp`
- (out of scope in this spec) `POST /api/v4/smtp/test`

## Spec acceptance criteria

- Every scenario is Playwright-implementable without hidden interpretation.
- Coverage includes happy paths, SMTP client-side validations, and persistence after reload.
- “Broken test” vs “broken product” is clearly separated via known-issues section.
