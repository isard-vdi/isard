# Users policies management in webapp

Human-readable functional specification of the **create**, **edit**,
**delete**, and **force-validation** flows for authentication policies
from the legacy admin. Serves as the contract for the E2E test
`tests/webapp/users_policies.spec.js`.

## Scope

- **Component**: administration panel.
- **Screen**: **Policy** section, accessible from the sidebar under
  the user-management group (route `/isard-admin/admin/policies`).
- **Actions covered**:
  - Create a new authentication policy scoped to a type, category, and role.
  - Edit the fields of an existing policy (type, category, and role
    are read-only once created).
  - Delete a policy (with confirmation; the system default policy
    cannot be deleted).
  - Force re-validation of email, disclaimer, or password at the next
    login for all users matching a policy.
- **Out of scope**: the effect of policies at login time (email
  verification flow, disclaimer page, password-change page), provider
  configuration, migration exceptions.

## Common role and prerequisites

| Element | Expected value |
| --- | --- |
| Role | Administrator of the `default` category |
| Session | Logged in to the webapp |
| Infrastructure | At least one category and one role exist in the system |
| Policy table | The `#users-password-policy` DataTable has loaded and is visible |

## Common data

| Field | Sample value | Notes |
| --- | --- | --- |
| Type | `local` | One of `local`, `google`, `saml`, `ldap` |
| Category | `default` (or `all`) | Picked from the dropdown; `all` is always the first option |
| Role | `user` (or `all`) | One of `admin`, `manager`, `advanced`, `user`; `all` targets every role |
| Digits | `1` | Minimum number of digit characters in the password |
| Character length | `8` | Minimum total password length |
| Lowercase chars | `1` | Minimum number of lowercase characters |
| Uppercase chars | `0` | Minimum number of uppercase characters |
| Special chars | `0` | Minimum number of special characters |
| Expiration days | `90` | Days until the password expires (0 = never) |
| Old passwords | `3` | How many previous passwords the system remembers |
| No username | `yes` | Whether the password may contain the username |

The created policy's `id` (returned by the table via
`GET /api/v4/admin/items/authentication/policies`) is stored in the test
metadata so that `afterEach` can clean it up even if assertions fail.

---

## Scenario 1 — *admin creates a local policy and sees it listed*

### Given

1. The administrator is authenticated in the webapp.
2. They are on the **Policy** page and the `#users-password-policy`
   table has loaded.

### When

1. They press the **Add policy** button in the header.
2. The **New Policy** dialog (`#modalPolicyAdd`) opens.
3. They pick **type** `local`, a specific **category** (e.g.
   `default`), and a specific **role** (e.g. `user`).
4. They fill in all password fields with valid numeric values.
5. They leave the **Verification required** checkbox unchecked and the
   **Disclaimer** section hidden (only visible when category = ALL).
6. They press **Add policy**.

### Then

1. The form passes client-side validation (Parsley).
2. `POST /api/v4/admin/item/authentication/policy` is called with status
   `< 400`.
3. The dialog closes and the table reloads automatically.
4. The new policy appears as a row in `#users-password-policy` showing
   the chosen type, category name, role, and the filled-in password
   values.
5. If the policy is queried via API
   (`GET /api/v4/admin/items/authentication/policies`), it is present with
   the expected field values.

---

## Scenario 1b — *creating an all-category policy without disclaimer saves `false`*

> **Known bug** — the JS condition `data['disclaimer-cb'] != 'on' && data['category'] !== "all"`
> takes the disclaimer branch for category = ALL even when the checkbox is unchecked.
> With no template selected, it sends `{ template: undefined }` which serialises to
> `{}` in JSON. The backend stores `{}` instead of `false`, leaving the disclaimer
> as a truthy empty object. This test is marked `test.fail` and will start passing
> once the bug is fixed.

### Given

1. The administrator opens the **New Policy** dialog.
2. They select type `local`, category **ALL**, and a specific role.
3. The **Disclaimer** section is visible but the checkbox is **not** checked.

### When

1. They press **Add policy**.

### Then

1. `POST /api/v4/admin/item/authentication/policy` responds with status `< 400`.
2. The created policy has `disclaimer = false` in the API response.
3. The **Disclaimer** column for that row shows **no icon** (not a green
   circle).
4. The **Force validation** button for that row does **not** offer the
   Force Accept Disclaimer option.

> **Actual (bug):** the Disclaimer column shows a green circle, the edit
> dialog opens with the disclaimer checkbox already checked, and Force
> Accept Disclaimer appears as an option — all because `disclaimer: {}`
> is stored instead of `false`.

---

## Scenario 1c — *creating a policy without email verification saves `false`*

### Given

1. The administrator opens the **New Policy** dialog.
2. They select type `local`, a specific category, and a specific role.
3. The **Verification required** checkbox is **not** checked (default state).

### When

1. They press **Add policy**.

### Then

1. `POST /api/v4/admin/item/authentication/policy` responds with status `< 400`.
2. The created policy has `email_verification = false` in the API response.

---

## Scenario 2 — *admin creates a policy for a non-local provider*

### Given

1. The administrator opens the **New Policy** dialog.
2. The providers dropdown is populated from
   `GET /api/v4/admin/items/authentication/providers`.

### When

1. They pick a non-local type (e.g. `google` or `saml`).
2. The **Password** section collapses and is hidden from the form
   (`.password_fields` is hidden).
3. They pick a category and a role.
4. They press **Add policy**.

### Then

1. `POST /api/v4/admin/item/authentication/policy` is called with status
   `< 400`; the body contains no `password` sub-object (or only
   default zeros).
2. The dialog closes and the new row appears in the table.
3. In the table, the password columns for that row show `"-"` because
   the renderer skips them for non-local types (at least one column is
   verified in the test; the full set is visually confirmed).

---

## Scenario 3 — *admin enables email verification on a policy*

### Given

1. A policy for type `local`, a specific category, and role exists
   with `email_verification = false`.

### When

1. They press the **edit** icon (pencil) on the policy row.
2. The **Edit Policy** dialog (`#modalPolicyEdit`) opens.
3. The **Verification required** checkbox is unchecked. They check it.
4. They press **Edit policy**.

### Then

1. `PUT /api/v4/admin/item/authentication/policy/{id}` is called with
   status `< 400`.
2. The dialog closes and the table reloads.
3. The **Email verification** column for that row now shows a green
   circle icon.
4. The **Force validation** button (`#btn-policy-force`, refresh/repeat
   icon `fa-repeat`) becomes visible for that row because
   `email_verification` is now truthy.

---

## Scenario 3b — *admin disables email verification in edit saves `false`*

### Given

1. A policy with `email_verification = true` exists (created via API
   before the test).
2. The administrator opens the **Edit Policy** dialog for that row.
3. The **Verification required** checkbox is **checked** (pre-filled
   from `GET /api/v4/admin/item/authentication/policy/{id}`).

### When

1. They **uncheck** the **Verification required** checkbox.
2. They press **Edit policy**.

### Then

1. `PUT /api/v4/admin/item/authentication/policy/{id}` is called with
   status `< 400`.
2. The dialog closes and the table reloads.
3. The created policy has `email_verification = false` in the API
   response (the field is cleared, not left at `true`).
4. The **Email verification** column for that row no longer shows a
   green circle icon.

---

## Scenario 4 — *admin enables disclaimer on an all-categories policy*

> The disclaimer is shown to the user **the first time they log in**
> after the policy is set (or after it is force-reset via S11). Once
> the user accepts it, the acknowledgement is stored and the disclaimer
> is not shown again until forced.

### Given

1. A policy with **category = ALL** exists (the disclaimer section is
   only available for all-category policies).
2. A notification template of a non-system kind (not `password`,
   `email`, or `deleted_gpu`) exists in the system.

### When

1. They press the **edit** icon on the all-categories policy row.
2. The dialog shows the **Disclaimer** section (not the warning
   banner).
3. They check the **Disclaimer acknowledgement required** checkbox.
4. The **Text template** dropdown appears. They pick a template from
   the list.
5. A preview of the template (title + body + footer) renders inside
   `#preview-panel`.
6. They press **Edit policy**.

### Then

1. `PUT /api/v4/admin/item/authentication/policy/{id}` is called with
   status `< 400` and the body contains
   `disclaimer: { template: "<template_id>" }`.
2. The dialog closes and the table reloads.
3. The **Disclaimer** column for that row shows a green circle icon.
4. The **Force validation** button becomes visible for that row.

---

## Scenario 4b — *disabling disclaimer in edit sends `false` in the PUT request body*

> The edit form correctly sends `false` in the PUT request body when
> the disclaimer checkbox is unchecked. The test intercepts the raw PUT
> body to confirm this (checking the response is insufficient because
> the backend normalises any falsy value before storing).

### Given

1. The system default policy (category=ALL, role=ALL, type=local) has
   `disclaimer` armed with a template via API before the test starts.
2. The administrator opens the **Edit Policy** dialog for that row.
3. The **Disclaimer acknowledgement required** checkbox is **checked**
   (pre-filled from the API).

### When

1. They **uncheck** the **Disclaimer acknowledgement required**
   checkbox.
2. They press **Edit policy**.

### Then

1. `PUT /api/v4/admin/item/authentication/policy/{id}` is called with
   status `< 400`.
2. The **PUT request body** sent by the browser contains
   `"disclaimer": false` — not `null`.
3. The dialog closes.

---

## Scenario 5 — *admin edits a policy's password parameters*

### Given

1. A `local` policy exists with specific password values (e.g.
   `digits = 0`, `expiration = 0`).

### When

1. They press the **edit** icon on the policy row.
2. The dialog opens with all password fields pre-filled with the
   current values (fetched from
   `GET /api/v4/admin/item/authentication/policy/{id}`).
3. They change **Digits** to `2`, **Expiration days** to `60`, and
   **Old passwords** to `5`.
4. **Type**, **Category**, and **Role** dropdowns are disabled
   (read-only) — the admin cannot change the scope once a policy is
   created.
5. They press **Edit policy**.

### Then

1. `PUT /api/v4/admin/item/authentication/policy/{id}` is called with
   status `< 400`.
2. The dialog closes and the table reloads.
3. The updated values (`2`, `60`, `5`) appear in the corresponding
   columns of that row.
4. If the policy is queried via API, the new values are persisted.

---

## Scenario 6 — *admin deletes a policy with confirmation*

### Given

1. A policy that is **not** the system default (category=ALL,
   role=ALL, type=local) exists with a delete button visible on its
   row.

### When

1. On the policy row, they press the **delete** icon (red ×,
   `#btn-policy-delete`).
2. A PNotify confirmation dialog appears:
   "Do you really want to delete user policy for category '…' and
   role '…'?"
3. They click **OK** to confirm.

### Then

1. `DELETE /api/v4/admin/item/authentication/policy/{id}` is called with
   status `< 400`.
2. A PNotify success notification "Policy deleted successfully"
   appears.
3. The row disappears from the `#users-password-policy` table.
4. If the policies list is queried via API, the deleted policy is no
   longer returned.

---

## Scenario 7 — *default policy has no delete button*

### Given

1. The system always has a default policy with category=ALL,
   role=ALL, and type=local. This policy acts as the fallback when
   no more specific policy matches a user at login.

### When

1. The administrator loads the Policy page.
2. They locate the row whose Category is "all", Role is "all", and
   Type is "local".

### Then

1. The row's action cell contains the **edit** pencil button but
   **no** delete button (`#btn-policy-delete`).
2. No API call to DELETE is possible for this row through the UI.

---

## Scenario 8 — *admin cancels a policy deletion*

### Given

1. A deletable policy exists.

### When

1. They press the **delete** icon on its row.
2. The PNotify confirmation dialog appears.
3. They click **Cancel**.

### Then

1. The dialog closes.
2. **No** call is made to
   `DELETE /api/v4/admin/item/authentication/policy/{id}`.
3. The row remains in the table and the policy persists when queried
   via API.

---

## Scenario 9 — *admin forces email re-verification for a policy*

### Given

1. A policy with `email_verification = true` exists; its row shows the
   **Force validation** button (`#btn-policy-force`).

### When

1. They press the **force** button on that row.
2. The **Force validation on login** dialog (`#modalForceVerification`)
   opens, showing only the buttons that apply:
   - **Force Verify Email** (`#force-email`) is visible.
   - **Force Update Password** (`#force-password`) is hidden (because
     `expiration = 0`).
   - **Force Accept Disclaimer** (`#force-disclaimer`) is **always
     visible** regardless of the policy — the JS uses `#force_disclaimer`
     (underscore) to hide it but the HTML id is `force-disclaimer`
     (hyphen), so the jQuery selector never matches.
3. A secondary PNotify confirmation appears:
   "Do you really want to force email for all users in category '…'
   and role '…' at login?"
4. They confirm.

### Then

1. `PUT /api/v4/admin/item/authentication/force_validate/email/{id}` is
   called with status `< 400`.
2. A PNotify success notification "Policy forced successfully" appears
   and the policy table reloads in the background.
3. The `#modalForceVerification` dialog **stays open** — the success
   handler does not call `modal('hide')`. The admin must close it
   manually.
4. At the database level, all users matching that policy have
   `email_verified` reset so they must re-verify at their next login
   (not verified via E2E — covered by unit tests).

---

## Scenario 9b — *force-disclaimer button is hidden when policy has no disclaimer*

> **Known bug** — the JS calls `$(modal + " #force_disclaimer").hide()`
> (underscore) but the HTML element has `id="force-disclaimer"` (hyphen).
> The jQuery selector never matches, so the button is always visible
> regardless of the policy's disclaimer state. This test is marked
> `test.fail` and will start passing once the typo is fixed.

### Given

1. A policy with a **specific category** (not ALL), `email_verification =
   true`, and `disclaimer = false` exists via API.
   A specific category is used deliberately so that the S1b bug does not
   interfere (with category=ALL the POST would store `{}` instead of
   `false`).
2. The **Force validation** button is visible on the row (because
   `email_verification` is true).

### When

1. They press the **force** button on that row.
2. The **Force validation on login** dialog opens.

### Then

1. **Force Verify Email** (`#force-email`) is visible.
2. **Force Accept Disclaimer** (`#force-disclaimer`) is **hidden** —
   because `disclaimer = false`.

---

## Scenario 10 — *admin forces password update for a policy*

### Given

1. A local policy with `password.expiration > 0` exists; its row
   shows the **Force validation** button.

### When

1. They press the **force** button.
2. The **Force validation** dialog opens.
3. **Force Update Password** (`#force-password`) is visible.
4. **Force Verify Email** (`#force-email`) is hidden (because
   `email_verification = false`).
5. They click **Force Update Password** and confirm the PNotify
   dialog.

### Then

1. `PUT /api/v4/admin/item/authentication/force_validate/password/{id}` is
   called with status `< 400`.
2. A PNotify success notification "Policy forced successfully" appears
   and the policy table reloads.
3. The `#modalForceVerification` dialog **stays open**.
4. At the database level, all users matching the policy have
   `password_last_updated` cleared (covered by unit tests).

---

## Scenario 11 — *admin forces disclaimer re-acceptance for a policy*

### Given

1. The system default policy (category=ALL, role=ALL, type=local) has
   its `disclaimer` **armed with a template via API** before the test
   starts. Its row shows the **Force validation** button.

### When

1. They press the **force** button.
2. The **Force validation** dialog opens.
3. **Force Accept Disclaimer** (`#force-disclaimer`) is visible.
4. They click **Force Accept Disclaimer** and confirm the PNotify
   dialog.

### Then

1. `PUT /api/v4/admin/item/authentication/force_validate/disclaimer/{id}`
   is called with status `< 400`.
2. A PNotify success notification "Policy forced successfully" appears
   and the policy table reloads.
3. The `#modalForceVerification` dialog **stays open**.
4. At the database level, all users matching the policy have
   `disclaimer_acknowledged` cleared (covered by unit tests).

---

## Scenario 12 — *disclaimer option is unavailable for a non-all-category policy*

### Given

1. The administrator opens the **New Policy** (or **Edit Policy**)
   dialog.
2. They pick a specific category (not ALL).

### When

1. As soon as they choose a specific category, the disclaimer
   section content (`#disclaimer-content`) hides and the warning
   banner (`#disclaimer-warning`) appears with the message:
   "Disclaimer options are only available for policies for ALL
   categories."

### Then

1. The **Disclaimer** checkbox and the template selector are not
   visible and cannot be interacted with.
2. If they switch back to **ALL**, the warning disappears and the
   disclaimer section becomes visible again.

---

## Scenario 13 — *admin tries to enable disclaimer without a template*

### Given

1. The administrator is on a policy dialog where the category is ALL
   and the disclaimer section is visible.

### When

1. They check the **Disclaimer acknowledgement required** checkbox.
2. The template dropdown appears but they leave it at the placeholder
   value ("-- Select a template --").
3. They press **Add policy** (or **Edit policy**).

### Then

1. A PNotify error notification appears:
   "If disclaimer acknowledgement is enabled, a text template must be
   selected."
2. **No** call is made to
   `POST /api/v4/admin/item/authentication/policy` (or `PUT …`).
3. The dialog stays open.

---

## Scenario 14 — *force validation button is hidden when no forceable policy is set*

### Given

1. A policy exists with `email_verification = false`, `disclaimer =
   false`, and `password.expiration = 0`.

### When

1. The policy table loads.

### Then

1. The row for that policy shows only the **edit** pencil button (and
   the delete button if applicable) — the **Force validation** button
   (`#btn-policy-force`) is **not** rendered, because none of the
   three forcing conditions is met.

---

## Cleanup (afterEach)

1. The policy `id` created by the test is recovered from the metadata
   (`testInfo.annotations` type `"policy-id"`).
2. The policy is looked up and, if it exists, deleted via
   `DELETE /api/v4/admin/item/authentication/policy/{id}`.
3. Cleanup errors are silenced to avoid masking the real reason of an
   earlier failure.

Tests that edit the system default policy (S4, S4b, S11) restore the
original values **inline at the end of the test** via a `PUT` call,
since the default policy cannot be deleted and is not tracked via
`testInfo.annotations`.

---

## Expected results — global summary

| Scenario | Covered in test? | Key checks |
| --- | --- | --- |
| S1 — Create local policy | ✅ | Form valid, POST ok, row appears with correct values, persistence via API |
| S1b — Create all-category policy, disclaimer unchecked | ✅ `test.fail` | Bug: category=ALL always sends disclaimer object on creation — `disclaimer` never saved as `false` |
| S1c — Create policy without email verification | ✅ | `email_verification = false` persisted correctly |
| S2 — Create non-local policy | ✅ | Password fields hidden, POST ok, table shows "-" for password columns |
| S3 — Enable email verification | ✅ | PUT ok, green circle in Email column, force button appears |
| S3b — Disable email verification in edit | ✅ | `email_verification = false` persisted, green circle gone |
| S4 — Enable disclaimer (all-category) | ✅ | Template selected, preview shown, PUT ok, green circle in Disclaimer column |
| S4b — Disable disclaimer in edit | ✅ | PUT request body contains `disclaimer: false` (edit form works correctly) |
| S5 — Edit password parameters | ✅ | Fields pre-filled from GET, PUT ok, table refreshed, persistence |
| S6 — Delete policy with confirmation | ✅ | PNotify confirm, DELETE ok, row disappears, not in API |
| S7 — Default policy has no delete | ✅ | No `#btn-policy-delete` on category=all + role=all + type=local row |
| S8 — Cancel deletion | ✅ | No DELETE call, row and policy persist |
| S9 — Force email re-verification | ✅ | Only email button visible, PNotify confirm, PUT email ok |
| S9b — Force-disclaimer hidden when disclaimer=false | ✅ `test.fail` | Bug: `#force_disclaimer` (underscore) never matches `id="force-disclaimer"` — button always visible |
| S10 — Force password update | ✅ | Only password button visible, PNotify confirm, PUT password ok |
| S11 — Force disclaimer re-acceptance | ✅ | Only disclaimer button visible, PNotify confirm, PUT disclaimer ok |
| S12 — Disclaimer hidden for non-all category | ✅ | Warning shown, disclaimer section hidden; hidden again on ALL |
| S13 — Disclaimer enabled without template | ✅ | PNotify error, no POST/PUT, dialog stays open |
| S14 — Force button hidden when nothing forceable | ✅ | No `#btn-policy-force` in action cell |

---

## APIs touched by the flows (reference)

- `GET    /api/v4/admin/items/authentication/policies` — list all policies.
  Response `list[PolicyResponse]`.
- `GET    /api/v4/admin/item/authentication/policy/{id}` — fetch a single
  policy (used to pre-fill the edit dialog). Response `PolicyResponse`.
- `POST   /api/v4/admin/item/authentication/policy` — create a policy.
  Body `PolicyCreateRequest`; response 204 No Content.
- `PUT    /api/v4/admin/item/authentication/policy/{id}` — edit a policy.
  Body `PolicyEditRequest`; response 204 No Content.
- `DELETE /api/v4/admin/item/authentication/policy/{id}` — delete a policy.
  Response 204 No Content; 403 if trying to delete the system default.
- `PUT    /api/v4/admin/item/authentication/force_validate/email/{id}`
  — reset `email_verified` for all matching users. Response 204.
- `PUT    /api/v4/admin/item/authentication/force_validate/disclaimer/{id}`
  — reset `disclaimer_acknowledged` for all matching users. Response 204.
- `PUT    /api/v4/admin/item/authentication/force_validate/password/{id}`
  — reset `password_last_updated` for all matching users. Response 204.
- `GET    /api/v4/admin/items/categories` — populate category dropdown in
  the Add dialog. Response `list[CategoryResponse]`.
- `GET    /api/v4/admin/items/roles` — populate role dropdown. Response
  `list[RoleResponse]`.
- `GET    /api/v4/admin/items/authentication/providers` — populate the type
  dropdown. Response `ProvidersResponse`.
- `GET    /api/v4/admin/items/notifications/templates` — populate the
  disclaimer template selector. Response `{ templates: [...] }`.
- `GET    /api/v4/admin/item/notifications/template/{id}` — fetch a single
  template to render the preview. Response `TemplateResponse`.

## Relevant database state

- `authentication` table: each row is a policy document keyed by an
  auto-generated `id`. Fields: `type`, `category`, `role`,
  `email_verification`, `disclaimer`, `password` (sub-document with
  `digits`, `length`, `lowercase`, `uppercase`, `special_characters`,
  `expiration`, `old_passwords`, `not_username`).
- `users` table: the force-validate endpoints reset
  `email_verified`, `disclaimer_acknowledged`, or
  `password_last_updated` on every user whose category + role +
  provider match the policy scope.

