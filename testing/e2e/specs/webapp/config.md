# Config (admin webapp) — coverage map

Master scope for **Config** in the legacy admin webapp.
This file defines what must be covered and links to subsection specs.

## Scope confirmation

`Config` includes these subsections:

1. **Schedulers** — creation, alloweds, deletion, edition
2. **Viewers** — edit, delete/reset
3. **System** — maintenance mode and maintenance text
4. **Login** — enable/disable and edit

## Subsection routes

- `Config → Schedulers`: `/isard-admin/admin/schedulers`
- `Config → Viewers`: `/isard-admin/admin/viewers`
- `Config → System`: `/isard-admin/admin/system`
- `Config → Login`: `/isard-admin/admin/login`

All are admin-only routes in `webapp/webapp/webapp/views/AdminViews.py` (`@isAdmin`).

## Spec files

- `testing/e2e/specs/webapp/schedulers.md`
- `testing/e2e/specs/webapp/viewers.md`
- `testing/e2e/specs/webapp/system.md`
- `testing/e2e/specs/webapp/login.md`

## Required minimum automation set

| Subsection | Required actions | Status |
| --- | --- | --- |
| Schedulers | create, alloweds update, delete, edit | Spec defined |
| Viewers | edit custom, reset/delete custom | Spec defined |
| System | maintenance mode + maintenance text | Spec already defined |
| Login | enable/disable notifications + edit notification content | Spec defined |

## Execution notes

- Use admin-authenticated fixture.
- Prefer independent tests and API-based cleanup.
- For flows mutating global config, force serial workers or isolate by state restore.
- Treat DataTable reloads and modal close/open as synchronization points.
