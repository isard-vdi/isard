# Viewers Configuration (admin webapp)

Functional, traceable specification for **Config → Viewers** in legacy admin webapp.

## Context

- **Page**: `/isard-admin/admin/viewers`
- **Template**: `webapp/webapp/webapp/templates/admin/pages/viewers_config.html`
- **Main JS**: `webapp/webapp/webapp/static/admin/js/viewers_config.js`
- **Modal template**: `webapp/webapp/webapp/templates/admin/pages/viewers_config_modals.html`

## Resource / action matrix

| Resource | View | Edit | Delete/Reset | Notes |
| --- | --- | --- | --- | --- |
| Viewer custom options (`file_rdpgw`, `file_rdpvpn`, `file_spice`) | ✅ | ✅ | ✅ (reset to default) | Delete action is implemented as **reset custom** |

## Roles and preconditions

| Item | Expected value |
| --- | --- |
| Main role | Authenticated admin |
| Route access | Admin only |
| Initial state | At least one viewer row available |

---

## Scenarios

### A1 — initial load of Viewers page

- **UI steps**:
  1. Open `/isard-admin/admin/viewers`.
  2. Wait for `#viewers-conf-table`.
- **Expected UI**:
  - Table renders with columns Viewer, Fixed, Default, Custom, actions.
- **Expected network**:
  - `GET /api/v4/admin/viewers-config` → 2XX.

### A2 — edit viewer custom options

- **UI steps**:
  1. Click row action `#btn-edit`.
  2. In `#modalEditViewersConfig`, update `#custom`.
  3. Submit `#modalEditViewersConfig #send`.
- **Expected UI**:
  - Modal closes.
  - Success notification appears.
  - Table reloads with updated custom value.
- **Expected network**:
  - `PUT /api/v4/admin/viewers-config/{viewer}` → 2XX (currently 204 in API).
  - Follow-up `GET /api/v4/admin/viewers-config` reload → 2XX.
- **Cleanup**:
  - Restore original `custom` text.

### A3 — reset (delete) viewer custom options

- **UI steps**:
  1. Click row action `#btn-reset`.
  2. Confirm PNotify dialog.
- **Expected UI**:
  - Success notification appears.
  - Table reloads.
  - Custom value equals default value after reset.
- **Expected network**:
  - `PUT /api/v4/admin/viewers-config/reset/{viewer}` → 2XX (currently 204 in API).
  - Follow-up `GET /api/v4/admin/viewers-config` reload → 2XX.

## Notes

- In this page, “delete” means clearing custom options by resetting to default.
- `viewers_config.js` has no hard validation for `custom`; it sends free text payload.
