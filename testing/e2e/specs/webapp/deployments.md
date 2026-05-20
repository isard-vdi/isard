# Deployment management in webapp

Human-readable functional specification of the **list**, **delete**,
**bulk delete**, **change owner**, **change co-owners**, and
**edit allowed users** flows for a deployment from the legacy admin
webapp. Serves as the contract for the E2E test
`tests/webapp/deployments.spec.js`.

## Scope

- **Component**: administration panel (legacy webapp).
- **Screen**: **Deployments** section inside the admin panel.
- **Actions covered**:
  - List deployments in the DataTables table.
  - Delete a single deployment (with confirmation).
  - Bulk delete multiple deployments (permanently or to recycle bin).
  - Change the owner of a deployment.
  - Change the co-owners of a deployment.
- **Out of scope**: creating and editing deployments (done from Vue 3
  frontend), start/stop/recreate flows, direct-viewer CSV, videowall,
  booking flows.

## Common role and prerequisites

| Element | Expected value |
| --- | --- |
| Role | Administrator of the `default` category |
| Session | Logged in to the webapp |
| Deployments | At least one deployment exists in the system |
| Users | At least one user with role `manager` available (`manager_e2e_01`) |
| Groups | At least one group with at least one user |

## Common data

| Field | Sample value | Notes |
| --- | --- | --- |
| Deployment name | `e2e-dep-<worker>-<timestamp>` | Created via API in each test |
| New owner | `manager_e2e_01` (`E2E Manager 01`) | Resolved via admin user search |
| Co-owner | `manager_e2e_01` (`E2E Manager 01`) | Resolved via admin user search |

The deployment is created via API at the start of each test and deleted
in `afterEach` to ensure a clean state.

> **Why zero desktops?** Deployments are created with a non-existent
> group ID (`00000000-0000-0000-0000-000000000000`) as the only allowed
> entity and `create_owner_desktop: false`. The API validator accepts
> the request because the list is non-empty, but since the group does
> not exist in the DB no desktops are ever created. This avoids the
> 428 error that occurs when trying to delete a deployment whose
> desktops are not in Stopped state.

---

## Scenario 1 — *admin sees the deployments table loaded*

### Given

1. The administrator is authenticated in the webapp.
2. They navigate to the **Deployments** section.

### When

1. The page loads.

### Then

1. `POST /api/v4/admin/table/deployments` responds with status `< 400`.
2. The DataTables table renders with at least one row.
3. Visible columns include at least: **Name**, **User(owner)**,
   **Co-owners**, **Desktops**, **Running**.
4. Each row has an expand button, a delete button, and a select
   checkbox.

---

## Scenario 2a — *admin expands a deployment row and sees Target users and action buttons*

### Given

1. The deployments table has loaded with at least one row.

### When

1. They click the expand button (**+**) on a deployment row.

### Then

1. The detail panel opens below the row.
2. `POST /api/v4/allowed/table/deployments` responds and the **Target
   users** block renders with a table showing **Type** and **Items**
   columns.
3. **Change owner** and **Change co-owners** buttons are visible.

---

## Scenario 2b — *admin expands a deployment row and sees the hardware panel* ⏭ skipped

> Skipped: `GET /api/v4/item/deployment/{id}/hardware` returns 500.
> `DeploymentHardwareResponse` expects interfaces as `list[str]` or
> `list[Interface]` (with `mac` field) but the DB returns `{id, name}`
> objects without `mac`. Bug reported — unskip once fixed.

### Then

1. `GET /api/v4/item/deployment/{id}/hardware` responds with status
   `< 400` and the hardware panel populates.

---

## Scenario 3 — *admin deletes a deployment without started desktops*

### Given

1. A deployment created by this test exists with zero desktops.

### When

1. They click the red **delete** button on the deployment row.
2. A PNotify confirmation dialog appears.
3. They confirm the deletion.

### Then

1. `DELETE /api/v4/item/deployment/{id}` responds with status `< 400`.
2. A PNotify notification with title **Deleted** appears.
3. The row disappears from the table. Because deletion is asynchronous,
   the test polls with page reloads until the row is gone (up to 20 s).
4. If queried via API, the deployment no longer exists.

---

## Scenario 5 — *admin bulk-deletes deployments permanently*

### Given

1. At least two deployments exist with zero desktops.

### When

1. They select the checkboxes for two or more deployments.
2. They click **Bulk Delete**.
3. The PNotify dialog shows three options: **Delete permanently**,
   **Delete and send to recycle bin**, **Cancel**.
4. They choose **Delete permanently**.

### Then

1. `DELETE /api/v4/items/deployments` is called with
   `{ ids: [...], permanent: true }` and responds with status `< 400`.
2. A PNotify notification with title **Deletion queued** appears
   ("Queued deletion of N deployment(s). Rows will disappear as the
   operation progresses.").
3. All selected rows disappear from the table. Because deletion is
   asynchronous, the test polls with page reloads until both rows are
   gone (up to 20 s).

---

## Scenario 6 — *admin bulk-deletes deployments to recycle bin*

### Given

1. At least two deployments exist with zero desktops.

### When

1. They select the checkboxes for two or more deployments.
2. They click **Bulk Delete** and choose **Delete and send to recycle
   bin**.

### Then

1. `DELETE /api/v4/items/deployments` is called with
   `{ ids: [...], permanent: false }` and responds with status `< 400`.
2. A PNotify notification with title **Deletion queued** appears.
3. All selected rows disappear from the table (polled with page reloads,
   up to 20 s).

---

## Scenario 7 — *admin tries to bulk-delete with no deployments selected*

### Given

1. No checkboxes are checked in the table.

### When

1. They click **Bulk Delete**.

### Then

1. A warning PNotify notification appears ("Select the deployments...").
2. No `DELETE /api/v4/items/deployments` call is made.

---

## Scenario 8 — *admin changes the owner of a deployment*

### Given

1. A deployment exists in the expanded detail panel.
2. `manager_e2e_01` exists in the system with role `manager`.

### When

1. They click **Change owner** in the detail panel.
2. The `#modalChangeOwnerDomain` modal opens.
3. They type `E2E Manager 01` in the SELECT2 search field and select the
   result.
4. They click **Change owner** in the modal.

### Then

1. `PUT /api/v4/item/deployment/{id}/change-owner/{new_owner_id}`
   responds with status `< 400`.
2. A PNotify notification with title **Owner changed** appears.
3. The modal closes.
4. The table row reflects the new owner name in the **User(owner)**
   column (polled with page reloads, up to 20 s).

---

## Scenario 9 — *admin changes the co-owners of a deployment*

### Given

1. A deployment exists in the expanded detail panel.
2. `manager_e2e_01` exists in the system with role `manager`.

### When

1. They click **Change co-owners** in the detail panel.
2. The `#modalChangeCoOwnersDeployment` modal opens and the current
   co-owners are loaded via `GET /api/v4/item/deployment/{id}/co-owners`.
3. They type `E2E Manager 01` in the SELECT2 field and select the result.
4. They click **Change co-owners** in the modal.

### Then

1. `PUT /api/v4/item/deployment/{id}/co-owners` responds with status
   `< 400`.
2. The modal closes.
3. The table row shows `E2E Manager 01` in the **Co-owners** column
   (polled with page reloads, up to 20 s).
4. `GET /api/v4/item/deployment/{id}/co-owners` confirms `manager_e2e_01`
   is in `co_owners`.

---

## Scenario 10 — *admin removes all co-owners from a deployment*

### Given

1. A deployment exists with `manager_e2e_01` pre-set as co-owner via
   API.

### When

1. They open the **Change co-owners** modal.
2. They click the × button on every co-owner tag to clear the SELECT2.
3. They click **Change co-owners**.

### Then

1. `PUT /api/v4/item/deployment/{id}/co-owners` is called with
   `{ co_owners: [] }` and responds with status `< 400`.
2. The modal closes.
3. The table row no longer shows `E2E Manager 01` in the **Co-owners**
   column (polled with page reloads, up to 20 s).
4. `GET /api/v4/item/deployment/{id}/co-owners` confirms `co_owners` is
   empty.

---

## Cleanup (afterEach)

1. Deployment IDs annotated during the test are collected.
2. Each deployment is deleted via
   `DELETE /api/v4/item/deployment/{id}?permanent=true`.
3. Cleanup errors are silenced to avoid masking earlier failures.

---

## Expected results — global summary

| Scenario | Status | Key checks |
| --- | --- | --- |
| S1 — Table loads | ✅ | API ok, rows visible, columns present |
| S2a — Expand row: Target users + buttons | ✅ | Alloweds API ok, section visible, buttons visible |
| S2b — Expand row: hardware panel | ⏭ | Hardware API bug — unskip once fixed |
| S3 — Delete (no started desktops) | ✅ | Confirmation, API ok, row disappears (async poll) |
| S5 — Bulk delete permanently | ✅ | `permanent=true`, "Deletion queued" notification, rows disappear (async poll) |
| S6 — Bulk delete to recycle bin | ✅ | `permanent=false`, "Deletion queued" notification, rows disappear (async poll) |
| S7 — Bulk delete with no selection | ✅ | Warning shown, no API call |
| S8 — Change owner | ✅ | SELECT2 search, API ok, User(owner) column updated (async poll) |
| S9 — Change co-owners | ✅ | Current co-owners loaded, API ok, Co-owners column updated (async poll), API confirm |
| S10 — Remove all co-owners | ✅ | `co_owners: []`, Co-owners column empty (async poll), API confirm |

## APIs touched by the flows (reference)

- `POST   /api/v4/admin/table/deployments` — load table data.
- `POST   /api/v4/allowed/table/deployments` — load Target users for detail panel.
- `GET    /api/v4/item/deployment/{id}/hardware` — hardware panel (S2b).
- `DELETE /api/v4/item/deployment/{id}` — delete single deployment.
- `DELETE /api/v4/items/deployments` — bulk delete. Body
  `{ ids: [str], permanent: bool }`.
- `PUT    /api/v4/item/deployment/{id}/change-owner/{user_id}` — change
  owner.
- `GET    /api/v4/item/deployment/{id}/co-owners` — load current
  co-owners.
- `PUT    /api/v4/item/deployment/{id}/co-owners` — update co-owners.
  Body `{ co_owners: [user_id] }`.
- `POST   /api/v4/admin/users/search` — user search for SELECT2. Body
  `{ term: str }`.

## Relevant database state

- `deployments` table: `co_owners`, `allowed`, `user` fields.
- `domains` table: desktops tagged with the deployment `tag` field —
  checked indirectly via `how_many_desktops` and `how_many_desktops_started`
  columns.

## Cases not covered (future)

- Create and edit deployment (covered by Vue 3 frontend spec).
- Start/stop/recreate desktops from the webapp.
- Direct-viewer CSV download.
- Booking flows tied to a deployment.
