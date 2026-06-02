# Notification management in webapp

Human-readable functional specification of the **manage**, **templates**,
and **logs** flows for the notification administration panel. Serves as the
contract for the E2E test `tests/webapp/notifications.spec.js`.

## Scope

- **Component**: administration panel.
- **Screens**:
  - **Manage Notifications** — `/isard-admin/admin/notifications_manage`
  - **Notification Templates** — `/isard-admin/admin/notifications_templates`
  - **Notification Logs** — `/isard-admin/admin/notifications_logs`
- **Actions covered**:
  - **Manage**: create, edit, delete (with/without logs), validation, delete
    button absence for system-owned notifications.
  - **Templates**: create a custom template, edit it, delete it, verify system
    templates are read-only (no delete button).
  - **Logs**: status dropdown populates, user table loads on status selection,
    user detail row expands with log entries, delete individual log entry from
    detail panel, delete user row from main table, delete all data.
- **Out of scope**: the end-to-end flow that causes notifications to appear for
  users (desktop start, login, scheduler), alloweds configuration UI,
  default-language checkbox behavior, footer preview (same toggle path as body preview),
  parameters click-to-copy (clipboard API).

## Common role and prerequisites

| Element | Expected value |
| --- | --- |
| Role | Administrator of the `default` category |
| Session | Logged in to the webapp |
| Tables | DataTable for the section has loaded and is visible |

## Common data

| Field | Sample value | Notes |
| --- | --- | --- |
| Notification name | `e2e-notif-<worker>-<timestamp>` | Used to identify and clean up after each test |
| Template name | `e2e-tmpl-<worker>-<timestamp>` | Same pattern |
| Trigger | `login` | Only `login` and `start_desktop` are valid |
| Action | `custom` | Does not require a backend producer |
| Display | `modal` | Modal display mode |
| Order | `0` | Lower number = shown first |
| Keep time | `168` | Hours (1 week) |

Names are stored in `testInfo.annotations` so `afterEach` can clean them up
even if assertions fail mid-test.

---

## SECTION A — Manage Notifications

### Scenario A1 — *admin creates a notification and sees it listed*

#### Given

1. The administrator is on `/isard-admin/admin/notifications_manage`.
2. The `#notifications-table` DataTable has loaded.

#### When

1. They press the **Add notification** button.
2. The `#modalNotification` dialog opens.
3. They fill in:
   - **Name** → unique e2e name
   - **Trigger** → `login`
   - **Display** → `modal`
   - **Action** → `custom`
   - **Template** → first available template in the dropdown
   - **Order** → `0`
4. They confirm by pressing **Send**.

#### Then

1. `POST /api/v4/admin/item/notification` responds with status `< 400`.
2. The modal closes.
3. A success PNotify ("Notification added") appears.
4. A new row with the entered name appears in `#notifications-table`.
5. `GET /api/v4/admin/items/notifications` returns the new notification with the
   expected name and trigger.

---

### Scenario A2 — *admin edits a notification's name*

#### Given

1. A notification created by this test exists (via API) and is visible
   in `#notifications-table`.

#### When

1. On the notification row, they press the **pencil** icon.
2. The `#modalNotification` dialog opens with the current name pre-filled.
3. They change the name to `<original>-edited`.
4. They press **Send**.

#### Then

1. `PUT /api/v4/admin/item/notification/{id}` responds with status `< 400`.
2. The modal closes.
3. A success PNotify ("Notification updated") appears.
4. The row in `#notifications-table` shows the updated name.
5. `GET /api/v4/admin/item/notification/{id}` returns the notification with the
   updated name.

---

### Scenario A3 — *admin deletes a notification keeping the logs*

#### Given

1. A notification created by this test exists and is visible in
   `#notifications-table`.

#### When

1. They press the **delete** (trash) icon on the notification row.
2. A PNotify dialog appears with three buttons: **Delete with logs**,
   **Delete without logs**, and **Cancel**.
3. They press **Delete with logs**.

#### Then

1. `DELETE /api/v4/admin/item/notification/{id}` is called with `delete_logs: true`
   in the request body and responds with status `< 400`.
2. A success PNotify ("Notification deleted successfully") appears.
3. The row disappears from `#notifications-table`.
4. `GET /api/v4/admin/items/notifications` no longer includes the notification.

---

### Scenario A4 — *admin deletes a notification without deleting the logs*

#### Given

1. A notification created by this test exists.

#### When

1. They press the **delete** icon.
2. The three-button PNotify dialog appears.
3. They press **Delete without logs**.

#### Then

1. `DELETE /api/v4/admin/item/notification/{id}` is called with `delete_logs: false`
   and responds with status `< 400`.
2. A success PNotify appears.
3. The row disappears from `#notifications-table`.

---

### Scenario A5 — *delete button is absent for desktop item_type notifications*

> Desktop-type notifications are managed by the system (scheduler, engine).
> The webapp intentionally hides the delete button for them.

#### Given

1. At least one notification with `item_type = "desktop"` exists in the
   system (present in the e2e seed data — e.g. `unused_desktops`).
2. The `#notifications-table` has loaded.

#### When

1. The admin inspects the action column of any notification row with
   `item_type = "desktop"`.

#### Then

1. The row's action cell contains a **pencil** button and an **alloweds** button.
2. The **delete** (trash) button is **absent** from that row.
3. Notification rows with `item_type = "user"` do have the delete button.

---

### Scenario A6 — *Parsley validation blocks submission with an empty name*

#### Given

1. The `#modalNotification` dialog is open (Add mode).
2. A template and trigger have been selected.
3. The **Name** field is empty.

#### When

1. They press **Send**.

#### Then

1. Client-side Parsley validation blocks the submission.
2. The `#name` field gets the `parsley-error` CSS class.
3. **No** call is made to `POST /api/v4/admin/item/notification`.
4. The dialog stays open.

---

### Scenario A7 — *selecting a template in the notification modal renders its preview*

#### Given

1. A custom template with a known title exists (created via API).
2. The `#modalNotification` dialog is open (Add mode).
3. The `#template_id` dropdown has loaded.

#### When

1. They select the known template from the `#template_id` dropdown.

#### Then

1. `GET /api/v4/admin/item/notifications/template/{id}` is called.
2. `#preview-panel` becomes visible inside the modal.
3. `#preview-panel` contains the template's title.

---

## SECTION B — Notification Templates

### Scenario B1 — *admin creates a custom template and sees it listed*

#### Given

1. The administrator is on `/isard-admin/admin/notifications_templates`.
2. The `#custom-notification-tmpls-table` DataTable has loaded.

#### When

1. They press **Add template**.
2. The `#modalNotificationTemplate` dialog opens.
3. They fill in:
   - **Name** → unique e2e template name
   - **Language** → `English`
   - **Title** → `e2e test title`
   - **Body** → `<p>e2e test body</p>`
4. They confirm by pressing **Add Notification Template**.

#### Then

1. `POST /api/v4/admin/item/notifications/template` responds with status `< 400`.
2. The modal closes.
3. A success PNotify ("Notification template added successfully") appears.
4. A new row with the entered name appears in `#custom-notification-tmpls-table`.
5. `GET /api/v4/admin/items/notifications/templates/custom` includes the new template.

---

### Scenario B2 — *admin edits a custom template's title*

#### Given

1. A custom template created by this test exists (via API) and is visible
   in `#custom-notification-tmpls-table`.

#### When

1. On the template row, they press the **pencil** icon.
2. The `#modalNotificationTemplate` dialog opens in edit mode with the
   current name pre-filled.
3. They change the **Title** to a new value.
4. They press **Edit Notification Template**.

#### Then

1. `PUT /api/v4/admin/item/notifications/template/{id}` responds with status `< 400`.
2. The modal closes.
3. A success PNotify ("Notification template updated successfully") appears.
4. `GET /api/v4/admin/item/notifications/template/{id}` returns the template with
   the updated title in the expected language.

---

### Scenario B3 — *admin deletes a custom template*

#### Given

1. A custom template created by this test exists and is visible in
   `#custom-notification-tmpls-table`.

#### When

1. They press the **delete** (×) icon on the template row.
2. A PNotify confirmation dialog appears.
3. They confirm by pressing **Ok**.

#### Then

1. `DELETE /api/v4/admin/item/notifications/template/{id}` responds with
   status `< 400`.
2. A success PNotify ("Notification template deleted successfully") appears.
3. The row disappears from `#custom-notification-tmpls-table`.
4. `GET /api/v4/admin/items/notifications/templates/custom` no longer includes
   the template.

---

### Scenario B4 — *system templates have no delete button*

#### Given

1. The `#system-notification-tmpls-table` DataTable has loaded and has at
   least one row.

#### When

1. The admin inspects the action column of any system template row.

#### Then

1. Each row in `#system-notification-tmpls-table` has only the **pencil**
   (edit) button in its action cell.
2. No delete (×) button is rendered for any system template row.
3. Custom template rows in `#custom-notification-tmpls-table` do have the
   delete (×) button.

---

### Scenario B5 — *admin previews a custom template before saving*

#### Given

1. A custom template created by this test exists and is visible in
   `#custom-notification-tmpls-table`.
2. The admin opens the edit modal for that template (pencil icon).
3. The **Body** field contains some HTML text.

#### When

1. They press the **Preview** button inside the modal.

#### Then

1. The `#body` textarea is hidden and replaced by the `#body-preview` div,
   which renders the HTML content of the body.
2. The Preview button label changes to **Edit text**.
3. No API call is made (preview is purely client-side rendering).

#### And when

4. They press **Edit text**.

#### Then

5. The `#body-preview` div is hidden and the `#body` textarea is shown again
   with the original content intact.

---

### Scenario B6 — *Parsley validation blocks submission with an empty name*

#### Given

1. The `#modalNotificationTemplate` dialog is open (Add mode).
2. A language has been selected.
3. The **Name** field is empty.

#### When

1. They press **Add Notification Template**.

#### Then

1. Parsley blocks the submission.
2. The `#name` field gets the `parsley-error` CSS class.
3. **No** call is made to `POST /api/v4/admin/item/notifications/template`.
4. The dialog stays open.

---

### Scenario B7 — *expanding a custom template row shows its default language content*

#### Given

1. A custom template with a known title and body exists (created via API).
2. The `#custom-notification-tmpls-table` has loaded.

#### When

1. They press the **expand** (`+`) button in the `details-control` cell of the template row.

#### Then

1. A detail panel appears below the row with the template's default language content.
2. The panel contains the template's title text.
3. The panel contains the template's body text.

---

### Scenario B8 — *HTML script injection in body is rejected client-side*

> `checkCleanHTML` runs before any API call. If body contains `<script>`, `<iframe>`,
> or `javascript:`, the submission is blocked and an error PNotify is shown.

#### Given

1. The `#modalNotificationTemplate` dialog is open (Add mode).
2. Name and language are filled in.

#### When

1. They enter `<script>alert(1)</script>` in the **Body** field.
2. They press **Add Notification Template**.

#### Then

1. An error PNotify ("Invalid html") appears.
2. **No** call is made to `POST /api/v4/admin/item/notifications/template`.
3. The modal stays open.

---

### Scenario B9 — *expanding a system template row shows its system content*

> Uses `addDetailPannel(row.data(), "system")` which reads `template.system` —
> a different code path from B7 which reads `template.lang[default]`.

#### Given

1. At least one system template exists in the dev DB.
2. `#system-notification-tmpls-table` has loaded.

#### When

1. They press the **expand** (`+`) button on the first system template row.

#### Then

1. The parent row gets the CSS class `shown`.
2. A detail panel appears below the row with the "System default template" heading visible.

---

### Scenario B10 — *edit modal for a system template opens pre-filled*

#### Given

1. At least one system template exists in the dev DB.
2. `#system-notification-tmpls-table` has loaded.

#### When

1. They press the **pencil** icon on a system template row.

#### Then

1. `GET /api/v4/admin/item/notifications/template/{id}` is called.
2. `#modalNotificationTemplate` opens in edit mode.
3. The `#name` field is pre-filled with the system template's name.
4. The `#btn-apply` button is visible (only shown in edit mode, hidden in add mode).
5. The modal title contains "Edit Notification Template".

---

### Scenario B11 — *Apply button saves language content without closing the modal*

> The Apply button (`#btn-apply`) is only visible in edit mode. It calls
> `applyMessage()` which does a `PUT` without closing the modal — distinct from
> the main **Send** button which closes it.

#### Given

1. A custom template exists (created via API).
2. The edit modal is open with the template's English content loaded.

#### When

1. They change the **Title** field.
2. They click **Apply**.

#### Then

1. `PUT /api/v4/admin/item/notifications/template/{id}` responds with status `< 400`.
2. A success PNotify ("Language body updated successfully") appears.
3. The modal stays open.
4. `GET /api/v4/admin/item/notifications/template/{id}` confirms the title was persisted.

---

### Scenario B12 — *switching language in edit mode reloads template fields via GET*

> `changeBodyLanguage` is called when `#language` changes while the modal has
> class `editModal`. It fetches the template and populates title/body/footer for
> the selected language.

#### Given

1. A custom template with only English content exists (created via API).
2. The edit modal is open with English selected.

#### When

1. They change `#language` to a language not present in the template (e.g. `es`).

#### Then

1. `GET /api/v4/admin/item/notifications/template/{id}` is called.
2. `#default-lang` checkbox is unchecked (the new language is not the default).
3. `#title` is empty — no `es` content exists and no system fallback is available.

---

## SECTION C — Notification Logs

> **Execution order:** C tests run serially (`test.describe.serial`). Scenario C4
> deletes all `notifications_data` globally — running it concurrently with C2 or C3
> would cause race conditions where C4 deletes data the other tests depend on.

### Scenario C1 — *status dropdown populates and triggers the user table*

#### Given

1. A `notifications_data` entry with `status = "notified"` has been created for
   the admin user (same prerequisite as C2 — the test runs `setupLoginNotificationData`
   before navigating so the dropdown has at least one status to show).
2. The administrator is on `/isard-admin/admin/notifications_logs`.

#### When

1. The page loads and the `#status` dropdown is populated via
   `GET /api/v4/admin/items/notifications/statuses`.
2. They select the status **notified** from the dropdown.

#### Then

1. `GET /api/v4/admin/items/notifications/statuses` responds with status `< 400`
   and returns a list that includes at least `notified`.
2. The `#status` dropdown has at least one option beyond the placeholder.
3. On selecting **notified**, `GET /api/v4/admin/items/notifications/data/by_status/notified`
   is called and `#notifications-users-table` renders with at least one row.

---

### Scenario C2 — *user row expands to show notification log detail*

> Requires at least one `notifications_data` entry with `status = "notified"`
> in the system. The test generates this entry by:
> (1) creating a custom `login` notification via API with `display: ["fullpage"]`,
>     `force_accept: false` (required — omitting it causes a 500 from the trigger
>     endpoint), and `allowed: { roles: [], categories: false, groups: false,
>     users: false }` (empty `roles` list = allow all users; `false` = skip
>     criterion which blocks everyone when the backend bypasses the role shortcut),
> (2) calling `GET /api/v4/items/notifications/user/login/fullpage` with the
>     admin session (which triggers `notifications_data` creation for `custom`
>     action notifications), and then
> (3) navigating to the logs page.
>
> **DOM ordering note:** DataTables injects a clone of `#notifications-logs-table`
> as a child row. This clone appears **before** the original hidden template element
> in the DOM, so locators targeting the detail table must use `.first()`, not `.last()`.

#### Given

1. A custom `login` notification exists in the system (created for this test).
2. The test has called the login notifications endpoint as the admin user,
   generating a `notifications_data` entry with `status = "notified"`.
3. The logs page is open and **notified** is selected in the status dropdown.
4. The `#notifications-users-table` shows at least one row (the admin user).

#### When

1. They press the **expand** (plus) button in the first cell of the admin
   user row.

#### Then

1. `GET /api/v4/admin/items/notifications/data/status/notified/user/{admin_user_id}`
   is called.
2. A `#notifications-logs-table` detail panel appears below the row.
3. The detail table contains at least one row with the notification created
   in the prerequisite step.

---

### Scenario C3 — *admin deletes an individual notification log entry*

> Tests the per-row trash icon inside the detail panel, which is distinct
> from the "Delete all" bulk action.

#### Given

1. The same prerequisite as C2 applies: a custom `login` notification exists
   and the login notifications endpoint has been called so that at least one
   `notifications_data` entry exists for the admin user with `status = "notified"`.
2. The logs page is open, **notified** is selected, and the admin user row is
   expanded showing the `#notifications-logs-table` detail panel.
3. The detail table has at least one row.

#### When

1. They press the **delete** (trash) icon on the first row of the detail table.
2. A PNotify confirmation dialog appears.
3. They confirm by pressing **Ok**.

#### Then

1. `DELETE /api/v4/admin/item/notifications/data/{notification_data_id}` responds
   with status `< 400`.
2. A success PNotify ("Notification deleted successfully") appears.
3. The row disappears from the detail `#notifications-logs-table`.

---

### Scenario C3b — *admin deletes a user row from the main users table*

> Tests the per-row trash icon in `#notifications-users-table`, which deletes all
> notification data for that user.

#### Given

1. A `notifications_data` entry with `status = "notified"` exists for the admin
   user (same prerequisite as C2/C3).
2. The logs page is open, **notified** is selected, and at least one row is visible
   in `#notifications-users-table`.

#### When

1. They press the **delete** (trash) icon on the first row of `#notifications-users-table`.
2. A PNotify confirmation dialog appears.
3. They confirm by pressing **Ok**.

#### Then

1. `DELETE /api/v4/admin/items/notifications/data/user/{user_id}` responds with status `< 400`.
2. A success PNotify ("Notification data deleted successfully") appears.
3. The row disappears from `#notifications-users-table`.

---

### Scenario C4 — *delete all notification data clears the table*

#### Given

1. The logs page is open.
2. The **notified** status is selected and the users table has loaded.

#### When

1. They press the **Delete all** button.
2. A PNotify confirmation dialog appears.
3. They confirm by pressing **Ok**.

#### Then

1. `DELETE /api/v4/admin/items/notifications/data` responds with status `< 400`.
2. A success PNotify ("Notification data deleted successfully") appears.
3. The `#notifications-users-table` shows no rows (empty or cleared state)
   after the deletion.
4. The `#status` dropdown has no options (the JS calls `$('#status').empty()`
   after a successful delete-all).

---

## Cleanup (afterEach)

1. Notifications created by Manage tests are deleted via API
   (`DELETE /api/v4/admin/item/notification/{id}` with `delete_logs: true`).
2. Templates created by Template tests are deleted via API
   (`DELETE /api/v4/admin/item/notifications/template/{id}`).
3. For Scenarios C2, C3, C3b, and C4, the custom notification created to generate
   log data is also deleted (which also cleans its associated `notifications_data`
   entries via `delete_logs: true`).
4. Cleanup errors are silenced to avoid masking real test failures.

---

## Expected results — global summary

| Scenario | Covered in test? | Key checks |
| --- | --- | --- |
| A1 — Create notification | ✅ | Modal opens, POST ok, row visible, API persistence |
| A2 — Edit notification | ✅ | Modal pre-filled, PUT ok, row updated, API persistence |
| A3 — Delete with logs | ✅ | 3-button dialog, `delete_logs=true`, row gone, not in API |
| A4 — Delete without logs | ✅ | 3-button dialog, `delete_logs=false`, row gone |
| A5 — No delete for desktop type | ✅ | Trash button absent for `item_type=desktop` rows |
| A6 — Parsley validation | ✅ | Empty name → Parsley error, no POST, modal open |
| A7 — Template preview in notification modal | ✅ | Selecting template fires GET, preview renders title |
| B1 — Create template | ✅ | Modal opens, POST ok, row in custom table, API persistence |
| B2 — Edit template | ✅ | Modal pre-filled, PUT ok, API persistence |
| B3 — Delete template | ✅ | Confirm dialog, DELETE ok, row gone, not in API |
| B4 — System templates read-only | ✅ | No delete button in `#system-notification-tmpls-table` |
| B5 — Template preview | ✅ | Preview button renders HTML, edit button restores textarea |
| B6 — Parsley validation | ✅ | Empty name → Parsley error, no POST |
| B7 — Custom template row expand | ✅ | Detail panel shows default language title and body |
| B8 — HTML injection blocked | ✅ | `<script>` in body → error PNotify, no POST |
| B9 — System template row expand | ✅ | Detail panel shows "System default template" heading |
| B10 — Edit system template modal | ✅ | Name pre-filled, Apply visible, edit mode title |
| B11 — Apply button saves without closing | ✅ | PUT ok, PNotify success, modal stays open, API verified |
| B12 — Language switch reloads fields | ✅ | GET fired on language change, default-lang unchecked, title empty |
| C1 — Status dropdown + table | ✅ | Dropdown populates, `by_status` API called, table renders |
| C2 — User row expand | ✅ | Detail table loads with at least one log entry |
| C3 — Delete individual log entry | ✅ | DELETE ok, success PNotify, row removed from detail table |
| C3b — Delete user row from main table | ✅ | DELETE ok, success PNotify, row removed from users table |
| C4 — Delete all data | ✅ | DELETE all ok, table empty, status dropdown cleared |

## APIs touched by the flows (reference)

- `POST   /api/v4/admin/item/notification` — create notification
- `PUT    /api/v4/admin/item/notification/{id}` — edit notification
- `DELETE /api/v4/admin/item/notification/{id}` — delete notification (body: `{delete_logs: bool}`)
- `GET    /api/v4/admin/item/notification/{id}` — get single notification
- `GET    /api/v4/admin/items/notifications` — list all notifications
- `GET    /api/v4/admin/items/notification/actions` — list available actions (for the modal dropdown)
- `POST   /api/v4/admin/item/notifications/template` — create template
- `PUT    /api/v4/admin/item/notifications/template/{id}` — edit template
- `DELETE /api/v4/admin/item/notifications/template/{id}` — delete template
- `GET    /api/v4/admin/item/notifications/template/{id}` — get single template
- `GET    /api/v4/admin/items/notifications/templates/custom` — list custom templates
- `GET    /api/v4/admin/items/notifications/templates/system` — list system templates
- `GET    /api/v4/admin/items/notifications/statuses` — list valid statuses
- `GET    /api/v4/admin/items/notifications/data/by_status/{status}` — users with notifications of this status
- `GET    /api/v4/admin/items/notifications/data/status/{status}/user/{user_id}` — notification log entries per user
- `DELETE /api/v4/admin/items/notifications/data/user/{user_id}` — delete all notification data for a specific user
- `DELETE /api/v4/admin/item/notifications/data/{notification_data_id}` — delete a single notification data entry
- `DELETE /api/v4/admin/items/notifications/data` — delete all notifications data
- `GET    /api/v4/items/notifications/user/{trigger}/{display}` — trigger custom notification creation (used in C2 prerequisite)
