# Schedulers Configuration (admin webapp)

Functional, traceable specification for **Config → Schedulers** in legacy admin webapp.

## Context

- **Page**: `/isard-admin/admin/schedulers`
- **Template**: `webapp/src/webapp/templates/admin/pages/schedulers.html`
- **Main JS**: `webapp/src/webapp/static/admin/js/schedulers.js`
- **Timeout rules JS**: `webapp/src/webapp/static/admin/js/desktops_priority.js`
- **Modals**: `webapp/src/webapp/templates/admin/pages/schedulers_modals.html` + `desktops_priority_modals.html`
- **Alloweds snippet**: `webapp/src/webapp/static/js/snippets/alloweds.js`

## Resource / action matrix

| Resource | Create | Edit | Delete | Alloweds | Notes |
| --- | --- | --- | --- | --- | --- |
| Timeout rules (`desktops_priority`) | ✅ | ✅ | ✅ | ✅ | This is where alloweds + edition are implemented |
| Job scheduler (`table-scheduler`) | ✅ | ❌ | ✅ | N/A | UI has no edit action for existing jobs |

## Roles and preconditions

| Item | Expected value |
| --- | --- |
| Main role | Authenticated admin |
| Route access | Admin only |
| Initial state | API available; DataTables can load |

---

## Scenarios

### A1 — initial load of Schedulers page

- **UI steps**:
  1. Open `/isard-admin/admin/schedulers`.
  2. Wait for `#desktops_priority` and `#table-scheduler` to render.
- **Expected UI**:
  - Both blocks are visible: **Desktops Timeouts** and **Job scheduler**.
- **Expected network**:
  - `POST /api/v4/admin/table/desktops_priority` → 2XX.
  - `GET /api/v4/admin/scheduler/jobs/system` → 2XX.

### A2 — create timeout rule (desktops priority)

- **UI steps**:
  1. Click `.add-new` (Desktops Timeouts).
  2. Fill required fields in `#modalAddPriority #modalAdd`.
  3. Submit `#modalAddPriority #send`.
- **Expected UI**:
  - Modal closes.
  - New rule appears in `#desktops_priority` table.
- **Expected network**:
  - `POST /api/v4/admin/table/add/desktops_priority` → 2XX.
- **Cleanup**:
  - Delete created rule.

### A3 — edit timeout rule

- **UI steps**:
  1. In created/existing row click `#btn-edit`.
  2. Update editable fields in `#modalEditPriority #modalEdit`.
  3. Submit `#modalEditPriority #send`.
- **Expected UI**:
  - Modal closes.
  - Row shows updated values after reload.
- **Expected network**:
  - `PUT /api/v4/admin/table/update/desktops_priority` → 2XX.
- **Cleanup**:
  - Restore original values.

### A4 — update alloweds for timeout rule

- **UI steps**:
  1. Click row action `#btn-alloweds`.
  2. In `#modalAlloweds`, enable at least one allowed scope checkbox.
  3. Select values through select2 controls.
  4. Submit `#modalAlloweds #send`.
- **Expected UI**:
  - Success notification (`Alloweds updated successfully`).
  - Modal closes.
- **Expected network**:
  - Open modal read: `POST /api/v4/allowed/table/desktops_priority` → 2XX.
  - Save: `POST /api/v4/admin/allowed/update/desktops_priority` → 2XX.
- **Cleanup**:
  - Restore original alloweds.

### A5 — delete timeout rule

- **UI steps**:
  1. Click row action `#btn-delete`.
  2. Confirm PNotify delete dialog.
- **Expected UI**:
  - Row is removed from table.
- **Expected network**:
  - `DELETE /api/v4/admin/table/desktops_priority/{id}` → 2XX.

### A6 — create scheduler job

- **UI steps**:
  1. Click `.btn-scheduler` to open `#modalScheduler`.
  2. Select `kind`, `action`, and time/date data.
  3. Submit `#modalScheduler #send`.
- **Expected UI**:
  - Modal closes.
  - `#table-scheduler` reloads and includes new job.
- **Expected network**:
  - Actions load: `GET /scheduler/actions` → 2XX.
  - Action schema (if used): `GET /scheduler/action/{action}` → 2XX.
  - Create job: one of
    - `POST /scheduler/system/{kind}/{action}/{hour}/{minute}` or
    - `POST /scheduler/advanced/date/system/{action}`
    with 2XX.
- **Cleanup**:
  - Delete created job.

### A7 — delete scheduler job

- **UI steps**:
  1. In `#table-scheduler`, click `#btn-scheduler-delete`.
  2. Confirm PNotify dialog.
- **Expected UI**:
  - Job row is removed.
- **Expected network**:
  - `DELETE /scheduler/{id}` → 2XX.

## Known limitations / notes

1. **No job edit UI** in `schedulers.js` for existing scheduler rows (only create/delete).
2. `schedulers.js` contains duplicated/corrupted code fragment inside `scheduler_init`; tests should synchronize with visible UI outcomes instead of internal function assumptions.
