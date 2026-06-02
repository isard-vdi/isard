# Login Configuration (admin webapp)

Functional, traceable specification for **Config → Login** in legacy admin webapp.

## Context

- **Page**: `/isard-admin/admin/login`
- **Template**: `webapp/webapp/webapp/templates/admin/pages/login.html`
- **Main JS**: `webapp/webapp/webapp/static/admin/js/login.js`
- **Modal template**: `webapp/webapp/webapp/templates/admin/pages/login_modals.html`
- **Field snippet**: `webapp/webapp/webapp/templates/snippets/login_notification_fields.html`
- **Helper JS**: `webapp/webapp/webapp/static/js/snippets/login_notification.js`

## Resource / action matrix

| Resource | View | Enable/Disable | Edit | Notes |
| --- | --- | --- | --- | --- |
| Left login notification (`cover`) | ✅ | ✅ | ✅ | checkbox `#enable_cover_notification_checkbox` |
| Right login notification (`form`) | ✅ | ✅ | ✅ | checkbox `#enable_form_notification_checkbox` |

## Roles and preconditions

| Item | Expected value |
| --- | --- |
| Main role | Authenticated admin |
| Route access | Admin only |
| Initial state | API available and login config present |

---

## Scenarios

### A1 — initial load of Login config page

- **UI steps**:
  1. Open `/isard-admin/admin/login`.
  2. Wait for `#LoginNotificationsPanel` and `#preview-panel`.
- **Expected UI**:
  - Two checkboxes are visible (left and right login notifications).
  - Preview panel renders current notification cards.
- **Expected network**:
  - `GET /api/v4/admin/login-config` → 2XX.

### A2 — enable/disable left notification

- **UI steps**:
  1. Toggle `#enable_cover_notification_checkbox`.
- **Expected UI**:
  - Success PNotify appears (`Notification cover enabled/disabled`).
  - Preview refreshes reflecting current enabled state.
- **Expected network**:
  - `PUT /api/v4/login_config/notification/cover/enable` with `{ enabled: bool }` → 2XX.
  - Follow-up refresh: `GET /api/v4/admin/login-config` → 2XX.
- **Cleanup**:
  - Restore original `enabled` value.

### A3 — enable/disable right notification

- **UI steps**:
  1. Toggle `#enable_form_notification_checkbox`.
- **Expected UI**:
  - Success PNotify appears (`Notification form enabled/disabled`).
  - Preview refreshes reflecting current enabled state.
- **Expected network**:
  - `PUT /api/v4/login_config/notification/form/enable` with `{ enabled: bool }` → 2XX.
  - Follow-up refresh: `GET /api/v4/admin/login-config` → 2XX.
- **Cleanup**:
  - Restore original `enabled` value.

### A4 — open edit modal with prefilled data

- **UI steps**:
  1. Click `#btnEditLoginNotification`.
- **Expected UI**:
  - Modal `#modalEditLoginNotification` opens.
  - Fields for `cover_*` and `form_*` are prefilled.
- **Expected network**:
  - `GET /api/v4/admin/login-config` on open → 2XX.

### A5 — edit login notifications and save

- **UI steps**:
  1. In modal, update at least title/description for cover and form.
  2. Click `#modalEditLoginNotification #send`.
- **Expected UI**:
  - Success notification (`Login notification updated successfully`).
  - Modal closes.
  - Preview panel updates with new text/styles.
- **Expected network**:
  - `PUT /api/v4/login_config/notification` → 2XX (API currently returns 204).
  - Refresh call `GET /api/v4/admin/login-config` → 2XX.
- **Cleanup**:
  - Restore original login notification payload.

### A6 — edit validation blocks invalid payload

- **UI steps**:
  1. Open edit modal.
  2. Input invalid URL in `cover_link_url` or `form_link_url` (e.g. `javascript:alert(1)`).
  3. Submit.
- **Expected UI**:
  - Error notification appears.
  - Modal remains open.
- **Expected network**:
  - `PUT /api/v4/login_config/notification` → 4XX.
- **Cleanup**:
  - Restore valid field value.

## Notes

- Preview rendering escapes HTML in helper code; assertions should validate rendered text, not raw HTML injection.
- Checkbox toggles are asynchronous and call `showConfig()` after PUT; use explicit waits on refresh GET to avoid flaky assertions.
