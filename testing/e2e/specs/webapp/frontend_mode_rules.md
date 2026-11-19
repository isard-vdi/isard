# Frontend mode rules (admin webapp)

Human-readable functional specification of the **frontend mode rules**:
their management from the legacy admin (**Config → Frontend**) and the
effect a rule has on the frontend each user gets. Serves as the contract
for the E2E test `tests/webapp/frontend_mode_rules.spec.js`.

## Scope

- **Component**: administration panel + both user frontends.
- **Screen**: **Config → Frontend**, route `/isard-admin/admin/frontend_mode`
  (admin only, `@isAdmin` in `webapp/src/webapp/views/AdminViews.py`).
- **Actions covered**:
  - List the rules ordered by priority.
  - Create a rule (name, description, frontend mode, priority, alloweds).
  - Edit a rule's fields.
  - Edit a rule's alloweds.
  - Delete a rule (with confirmation).
  - The effect of the applied rule on the user: `get-config`, the switch
    button, the redirects between frontends, and the temporary-desktop
    behaviour tied to the `actual` mode.
- **Out of scope**: the project acceptance cases not required by the
  ticket (CE-02, CE-10, CE-14, CE-15, CE-16, CE-17) and the exhaustive
  payload validation and role checks of the endpoints, already covered by
  the unit suite
  `component/apiv4/tests/routes/test_admin_frontend_mode_rules.py`.

## Delivery

The contract is delivered in two merge requests:

| Part | Sections | Merge request |
| --- | --- | --- |
| Administration page | A | This one |
| API contract and effect of the rule on the user | B, C | A later one |

Requirements of the administration page and the scenarios that cover
them:

| Requirement | Scenarios |
| --- | --- |
| The table loads with the existing rules | A1 |
| A rule can be created from the form | A2, A2b; validations in A3–A7 |
| A rule can be edited | A11, A11b, A11c, A11d, A12, A12b |
| Its alloweds can be modified | A13, A13b, A13c |
| It can be deleted with confirmation | A9, A10 |
| Every action shows in the table without reloading the page | A2, A2b, A9, A11, A11b, A11d, A13 |

## Context

- **Template**: `webapp/src/webapp/templates/admin/pages/frontend_mode.html`
- **Modals**: `webapp/src/webapp/templates/admin/pages/frontend_mode_modals.html`
  (one dialog, `#modalFrontendModeRule`, shared by *add* and *edit*)
- **Main JS**: `webapp/src/webapp/static/admin/js/frontend_mode.js`
- **Alloweds snippet**: `webapp/src/webapp/templates/snippets/alloweds_add.html`
  + `webapp/src/webapp/static/js/snippets/alloweds.js`
- **Alloweds dialog** (shared): `webapp/src/webapp/templates/snippets/alloweds_form.html`,
  opened by `modalAllowedsFormShow('frontend_mode_rules', rule)`
- **Routes**: `component/apiv4/src/api/routes/admin/frontend_mode_rules.py`
- **Alloweds routes** (shared): `component/apiv4/src/api/routes/admin/alloweds.py`
  + `component/apiv4/src/api/services/admin/alloweds.py`
- **Model**: `component/_common/src/isardvdi_common/models/frontend_mode_rules.py`
- **Rule resolution**: `get_frontend_mode_rule` in
  `component/_common/src/isardvdi_common/helpers/rules.py`
- **New frontend**: guard in `component/frontend/src/router/index.ts`,
  `components/frontend-toggler/FrontendToggler.vue`, `lib/frontendModeMap.ts`
- **Old frontend**: guard in `old-frontend/src/router/index.js`,
  `components/FrontendToggler.vue`, `shared/frontendModeMap.js`

## Resource / action matrix

| Action | UI | API | Notes |
| --- | --- | --- | --- |
| List | ✅ | ✅ | Ordered by priority, highest first |
| Create | ✅ | ✅ | Modal `#modalFrontendModeRule` in *add* mode |
| Edit fields | ✅ | ✅ | Same modal in *edit* mode: pre-filled from `GET` of the rule, alloweds panel hidden, saved with `PUT` |
| Edit alloweds | ✅ | ✅ | Shared dialog `#modalAlloweds`, through the generic alloweds endpoints |
| Delete | ✅ | ✅ | PNotify confirmation |

## How a rule is applied (behaviour under test)

1. Rules are evaluated from the highest priority to the lowest; the
   **first** rule that matches the user applies and the rest are ignored.
2. A rule matches when **any** of its `allowed` dimensions (`users`,
   `groups`, `categories`, `roles`) matches the user. Dimensions are not
   combined with AND.
3. For each dimension: `false` never matches, a list matches the ids it
   contains, and **an empty list `[]` matches every user**.
4. When no rule matches, the user gets the installation `FRONTEND_MODE`.
5. Priorities are unique across rules.
6. The rules are cached for 60 s. A change may therefore take up to 60 s
   to reach `get-config`, and the frontends only read `get-config` on
   page load, so the user also has to reload.

| Mode | New frontend (`/frontend/*`) | Old frontend (`/*`) | Switch button | Temporary desktops per template |
| --- | --- | --- | --- | --- |
| `deprecated` | Redirects to the old one | Reachable | Hidden | One, reused |
| `actual` | Reachable | Redirects to the new one, except bookings and plannings | Hidden | Several |
| `all` | Reachable | Reachable | Visible | One, reused |
| `hidden` | Reachable | Reachable | Hidden | One, reused |

Under `actual` the old frontend keeps serving the routes the new one does
not have yet: `/booking/*` and `/planning` (`VUE2_ONLY_ROUTES` in
`old-frontend/src/shared/frontendModeMap.js`). The new frontend links to
them, so they must not bounce back.

## Common roles and prerequisites

| Element | Expected value |
| --- | --- |
| Admin | `authenticatedPage` / `apiv4Admin` (`admin_e2e_NN`) |
| Non-admin | `managerE2EPage` (`manager_e2e_NN`), only for A14. `@isAdmin` logs the Flask session out when it rejects the manager, so A14 re-bridges it (`bridgeAdminSession`) before finishing: the session is shared by the whole worker |
| Target users | Dedicated accounts of the `fmre2e` category (see below), logged in on a fresh context per test |
| Control user | `user_e2e_NN` (category `default`), never matched by a test rule |
| Installation mode | Whatever `FRONTEND_MODE` the stack runs with (`all` in CI). Read at runtime from the control user's `get-config` and referred to below as **installation mode** |
| Desktop scenarios | Hypervisor online, a template allowed to the target user and a `volatile` quota of at least 3 |

### Seed data

A rule scoped to a category, group or role reaches every user in it, so
those scenarios must never target the shared `default` category: a
`deprecated` rule on it would redirect every other spec running in
parallel. The scenarios use a dedicated category seeded in
`testing/src/isardvdi_testing/data/` (same approach as `qle2e`). Nobody
else logs in with these accounts, so section A can point its rules at
them without changing the frontend of any running spec:

| Item | Value | Used for |
| --- | --- | --- |
| Category | `fmre2e` (hidden from the login dropdown) | Category-scoped rules |
| Groups | `fmre2e-group-a`, `fmre2e-group-b` | Group-scoped rules |
| `fmre2e-user-a` | role `user`, group A | Main target user |
| `fmre2e-user-b` | role `user`, group B | Same category, other group |
| `fmre2e-advanced` | role `advanced`, group A | Role-scoped rules |
| `fmre2e-manager` | role `manager`, group A | Planning page under `actual` (C7b); not used by section A |
| Template | `template-test-001` shared with the category | Temporary desktops |

The ids equal the usernames and the password is the one of the other
e2e accounts. The alloweds selectors search by display name, hence the
names above. Still pending, with section C: the template share and the
entries of the accounts and the category in `fixtures/login.js`
(`users`, `categories`).

## Common data

| Field | Sample value | Notes |
| --- | --- | --- |
| Name | `e2e-fmr-<scenario>-<timestamp>` | Required, 1–50 chars. The `e2e-fmr-` prefix identifies leftovers |
| Description | `created by e2e` | Optional, up to 255 chars; stored as `""` when omitted |
| Frontend mode | `deprecated` \| `actual` \| `all` \| `hidden` | Required |
| Priority | From `nextFrontendModeRulePriority()` | Required, integer, unique |
| Allowed | `{ users: [<id>] }` and the like | Unset dimensions are stored as `false` |

When a scenario must prove that the mode comes from the rule, the rule
uses a mode **different from the installation mode**. Where the scenario
needs `all` specifically and the installation mode is also `all`, a
lower-priority `hidden` rule on the `fmre2e` category is created first so
that `all` can only come from the rule under test.

## Fixtures (SDK)

Module `fixtures/apiv4/frontendModeRules.js`, exported from
`fixtures/apiv4/index.js`. It uses the generated SDK
(`src/gen/apiv4/sdk.gen`), which exposes the rule operations as
`getAllFrontendModeRules`, `getFrontendModeRule`,
`createFrontendModeRule`, `updateFrontendModeRule` and
`deleteFrontendModeRule`, next to the existing `getUserConfig`. The SDK
is not versioned: a local checkout must run the codegen (`./build.sh`)
to get them.

| Helper | Behaviour |
| --- | --- |
| `registerResource('frontend-mode-rule-id', …)` | Registers the deleter (`deleteFrontendModeRule`) so `cleanupTrackedResources(apiv4Admin, testInfo)` removes tracked rules in `afterEach`, even when assertions fail. Order before desktops |
| `nextFrontendModeRulePriority(client)` | Returns a free priority above every existing rule (`max(priority) + 1`, starting at `1_000_000`), so test rules outrank any rule already in the stack |
| `listFrontendModeRules(client)` | Returns the `rules` array of the list endpoint |
| `createFrontendModeRuleAndTrack(client, testInfo, overrides)` | Creates a rule with default name/priority and tracks it. `POST` answers `204` with no body, so the id is resolved by listing the rules and matching the name and the (unique) priority. Returns the stored rule |
| `findFrontendModeRuleByName(client, name)` | Looks a rule up in the list; used to track rules created through the UI |
| `updateFrontendModeRule(client, id, body)` | Thin wrapper over the SDK `PUT` |
| `setFrontendModeRuleAllowed(client, id, allowed)` | Replaces the alloweds through `adminAllowedUpdate` (`table: 'frontend_mode_rules'`), the same endpoint the dialog uses. Already in the generated SDK |
| `getFrontendModeRuleAllowed(client, id)` | Reads the alloweds enriched with names through `allowedTable`, as the dialog does. Already in the generated SDK |
| `purgeE2eFrontendModeRules(client)` | Deletes every rule whose name starts with `e2e-fmr-` (`E2E_FRONTEND_MODE_RULE_PREFIX`). Run in `beforeAll` to recover from an aborted run |
| `waitForFrontendMode(client, expected, { timeoutMs = 65000 })` | Polls `getUserConfig` with the **target user's** client until `frontend_mode` equals `expected` |

Safety guard: `createFrontendModeRuleAndTrack`, `updateFrontendModeRule`
and `setFrontendModeRuleAllowed` throw when any `allowed` dimension is `[]`, because that rule would apply
to every user of the stack (see *How a rule is applied*, point 3).

Rules created through the UI are tracked with
`track(testInfo, 'frontend-mode-rule-id', id)` as soon as they exist.

## Concurrency & ordering

- The rules are global configuration: the file runs with
  `test.describe.configure({ mode: 'serial' })`.
- No rule may match users outside the `fmre2e` category.
- Section C scenarios wait up to 65 s for the cache; they raise the test
  timeout to 120 s.
- A target user logs in on a **new browser context** per test, so
  `localStorage.preferredFrontend` starts empty.
- *Without reloading the page*: after the first load the test sets a
  marker on `window` and asserts it is still there once the table shows
  the change. Checked in A2, A2b, A9, A11, A11b, A11d and A13. The table
  has no alloweds column, so for A13 the change shows when the dialog is
  reopened on the same page load.

## Implementation status

| Section | Spec file | Status |
| --- | --- | --- |
| A | `tests/webapp/frontend_mode_rules.spec.js` | ✅ every scenario automated; A8b is `test.fail` (see *Known issues*, point 1) |
| B | — | ⏳ later merge request |
| C | — | ⏳ later merge request |

---

## SECTION A — Managing rules from Config → Frontend

### Scenario A1 — *admin opens the page and sees the rules by priority*

#### Given

1. The administrator is authenticated in the webapp.
2. Two rules exist (created through the SDK) with priorities `P` and `P+1`.

#### When

1. They open **Config → Frontend** from the sidebar.

#### Then

1. `GET /api/v4/items/frontend-mode-rules` responds with status `< 400`.
2. `#frontend-mode-rules-table` shows the columns **Name**,
   **Description**, **Frontend Mode**, **Priority** and **Action**.
3. The row with priority `P+1` is above the row with priority `P`.
4. Each row has the buttons `#btn-edit`, `#btn-alloweds` and `#btn-delete`.
5. The warning `#frontend-mode-warning` is visible and explains that the
   highest priority wins and that leaving `actual` deletes temporary
   desktops.
6. The mode label carries the mode description as its `title`.

### Scenario A2 — *admin creates a rule and sees it listed*

#### Given

1. The administrator is on the page and the table has loaded.

#### When

1. They press **Add rule** (`.btn-add-frontend-mode-rule`).
2. The dialog `#modalFrontendModeRule` opens with an empty form and the
   **Applies to** panel expanded with every dimension unchecked.
3. They fill **Name**, **Description**, pick a **Frontend mode** and type
   a free **Priority**.
4. They check **Set users** and select `fmre2e-user-a`.
5. They press **Add rule** (`#modalFrontendModeRule #send`).

#### Then

1. `POST /api/v4/item/frontend-mode-rule` responds with `204`.
2. The dialog closes, the notification *Rule added successfully* appears
   and the table reloads with the new row, without reloading the page.
3. Queried through the SDK, the rule has the typed name, description,
   mode and priority, a server-generated `id`, and
   `allowed = { users: [<id>], groups: false, categories: false, roles: false }`.
4. The new row shows the typed values and, having the highest priority,
   is the first row of the table.

### Scenario A2b — *a rule with only the required fields matches nobody*

#### When

1. The administrator opens the dialog, fills only **Name**, **Frontend
   mode** and **Priority**, leaves every **Applies to** dimension
   unchecked and presses **Add rule**.

#### Then

1. `POST /api/v4/item/frontend-mode-rule` responds with `204`.
2. The rule is stored with `description = ""` and every `allowed`
   dimension `false` (never `[]`, which would match every user).
3. The row appears with an empty description, without reloading the page.

### Scenario A3 — *the frontend mode selector offers the four modes*

#### When

1. The administrator opens the **Add rule** dialog.

#### Then

1. `#frontend_mode` lists `Choose...` plus `deprecated`, `actual`, `all`
   and `hidden`, each followed by its description.

### Scenario A4 — *required fields block the creation*

#### When

1. The administrator opens the dialog and presses **Add rule** with the
   form empty; then with a non-integer priority (`1.5`).

#### Then

1. Parsley marks **Name**, **Frontend mode** and **Priority** as invalid;
   the priority shows *The priority must be a whole number.* for `1.5`.
2. No `POST /api/v4/item/frontend-mode-rule` is sent.
3. The dialog stays open and the table is unchanged.

### Scenario A5 — *a priority already listed is rejected in the form* (CE-07)

#### Given

1. A rule with priority `P` exists and is listed in the table.

#### When

1. The administrator fills the dialog with priority `P` and presses
   **Add rule**.

#### Then

1. The priority field shows *Another rule already has this priority.*
2. No `POST` is sent, the dialog stays open and no rule is created.
3. Changing the priority to a free value and submitting creates the rule.

### Scenario A6 — *a priority taken after the table loaded is rejected by the server* (CE-07)

#### Given

1. The administrator has the page open.
2. A rule with priority `P` is then created through the SDK, so the
   loaded table does not contain it.

#### When

1. They submit the dialog with priority `P`.

#### Then

1. `POST /api/v4/item/frontend-mode-rule` responds with `409` and
   `description_code = duplicated_priority`.
2. The priority field shows *Another rule already has this priority.*;
   the dialog stays open and no error notification replaces it.
3. Typing in the priority field clears the message.
4. Only one rule with priority `P` exists.

### Scenario A7 — *cancelling the dialog creates nothing and resets the form*

#### When

1. The administrator fills the dialog and presses **Cancel**.
2. They open the dialog again.

#### Then

1. No `POST` was sent and the table is unchanged.
2. The form is empty, without validation messages, and every alloweds
   checkbox is unchecked.

### Scenario A8 — *HTML in the name is shown as text*

#### Given

1. A rule named `e2e-fmr-<img src=x onerror=alert(1)>` exists (SDK); the
   prefix keeps it purgeable.

#### When

1. The administrator opens the page and presses `#btn-delete` on its
   row, then cancels.
2. They press `#btn-alloweds` on the same row.

#### Then

1. The table cell and the delete confirmation show the name literally.
2. The title of the alloweds dialog (`#alloweds_name`) shows the name
   literally.
3. No `<img>` element is injected and no browser dialog is raised.

> Automated as two tests: **A8** (assertions 1 and 3 on the table and
> the confirmation) and **A8b** (assertion 2), which is `test.fail` —
> see *Known issues*, point 1.

### Scenario A9 — *admin deletes a rule with confirmation*

#### Given

1. A rule exists (SDK) and is listed.

#### When

1. The administrator presses `#btn-delete` on its row.
2. The confirmation names the rule and warns that its users fall back to
   the next matching rule or to the global frontend mode.
3. They confirm.

#### Then

1. `DELETE /api/v4/item/frontend-mode-rule/{id}` responds with `204`.
2. The notification *Rule "…" deleted successfully* appears and the row
   disappears, without reloading the page.
3. `GET /api/v4/item/frontend-mode-rule/{id}` responds with `404`.
4. The other rules are still listed.

### Scenario A10 — *admin cancels a deletion*

#### When

1. The administrator presses `#btn-delete` and cancels the confirmation.

#### Then

1. No `DELETE` is sent and the rule is still listed and present in the API.

### Scenario A11 — *admin edits a rule and the row shows the new values*

#### Given

1. Rules `R1` (priority `P`, with a description and
   `allowed = { users: [fmre2e-user-a] }`) and `R2` (priority `P+1`)
   exist and are listed.

#### When

1. The administrator presses `#btn-edit` on `R1`.
2. The dialog `#modalFrontendModeRule` opens titled *Edit frontend mode
   rule*, with the submit button labelled **Save changes** and the
   **Applies to** panel (`#alloweds-frontend-mode-rule`) hidden.
3. **Name**, **Description**, **Frontend mode** and **Priority** are
   pre-filled with `R1`'s values.
4. They change the name, the description and the mode, keep the
   priority and press **Save changes** (`#modalFrontendModeRule #send`).

#### Then

1. Opening the dialog calls `GET /api/v4/item/frontend-mode-rule/{id}`
   → status `< 400`.
2. Saving calls `PUT /api/v4/item/frontend-mode-rule/{id}` → `204`, with
   a body carrying `name`, `description`, `frontend_mode` and `priority`
   and **no** `allowed`.
3. The dialog closes, the notification *Rule updated successfully*
   appears and the row shows the new values, without reloading the page.
4. In the API, `R1` keeps its `id`, priority and `allowed`; `R2` is
   unchanged.

### Scenario A11b — *the dialog switches cleanly between edit and add*

#### When

1. The administrator opens the edit dialog of a rule and closes it with
   **Cancel**.
2. They press **Add rule**.
3. They cancel and open the edit dialog of the rule again, empty the
   **Description** and save.

#### Then

1. After step 1 no `PUT` was sent and the rule is unchanged in the API.
2. After step 2 the dialog is titled *Add frontend mode rule*, the
   button reads **Add rule**, the form is empty and the **Applies to**
   panel is visible with every dimension unchecked.
3. After step 3 the rule is stored with `description = ""` and the row
   shows an empty description.

### Scenario A11c — *editing blocks invalid values*

#### When

1. The administrator opens the edit dialog, empties **Name** and saves;
   then restores the name, types priority `1.5` and saves.

#### Then

1. Parsley marks the name as required and the priority shows *The
   priority must be a whole number.*
2. No `PUT` is sent, the dialog stays open and the rule is unchanged.

### Scenario A11d — *editing a rule deleted meanwhile reports it and refreshes the table*

#### Given

1. The administrator has the page open and a rule `R` is listed.
2. `R` is then deleted through the SDK.

#### When

1. They press `#btn-edit` on the stale row of `R`.

#### Then

1. `GET /api/v4/item/frontend-mode-rule/{id}` responds with `404`.
2. The notification *ERROR loading rule* appears and the dialog does not
   open.
3. The table reloads and the row of `R` disappears.

### Scenario A12 — *editing a rule to a priority already listed is rejected in the form* (CE-07)

#### Given

1. Rules `R1` (priority `P`) and `R2` (priority `P+1`) exist and are
   listed.

#### When

1. The administrator edits `R1`, sets priority `P+1` and saves.
2. They set the priority back to `P` and save.

#### Then

1. After step 1 the priority field shows *Another rule already has this
   priority.*, no `PUT` is sent and the dialog stays open.
2. After step 2 the rule's own priority is accepted: `PUT` responds with
   `204` and the dialog closes.
3. `R1` has priority `P` and `R2` priority `P+1`.

### Scenario A12b — *a priority taken after the table loaded is rejected by the server on edit* (CE-07)

#### Given

1. The administrator has the page open with `R1` (priority `P`) listed.
2. A rule with priority `P+5` is then created through the SDK, so the
   loaded table does not contain it.

#### When

1. They edit `R1`, set priority `P+5` and save.

#### Then

1. `PUT /api/v4/item/frontend-mode-rule/{id}` responds with `409` and
   `description_code = duplicated_priority`.
2. The priority field shows *Another rule already has this priority.*;
   the dialog stays open and no error notification replaces it.
3. Typing in the priority field clears the message.
4. `R1` keeps priority `P`.

### Scenario A13 — *admin edits the alloweds of a rule*

#### Given

1. A rule exists with `allowed = { users: [fmre2e-user-a] }` and a mode
   different from the installation mode.

#### When

1. The administrator presses `#btn-alloweds` on its row.
2. The dialog `#modalAlloweds` opens titled *Edit "<rule name>"
   permissions*, with the panel heading **Applies to** and without the
   unassignment warning (`#allowed-warning` hidden).
3. **Set users** is checked with `fmre2e-user-a` selected; **Set roles**,
   **Set categories** and **Set groups** are unchecked.
4. They check **Set groups**, select `fmre2e-group-b`, and press
   **Update permissions** (`#modalAlloweds #send`).

#### Then

1. Opening the dialog calls
   `POST /api/v4/item/allowed/table/frontend_mode_rules` with the rule id
   → status `< 400`.
2. Saving calls `POST /api/v4/item/allowed/update/frontend_mode_rules`
   → `204`.
3. The dialog closes and the notification *Alloweds updated successfully*
   appears.
4. In the API the rule has `users: [fmre2e-user-a]`,
   `groups: [fmre2e-group-b]`, `categories: false`, `roles: false`; name,
   description, mode and priority are unchanged.
5. Reopening the dialog, without reloading the page, shows both
   selections.
6. The row of the rule is still listed with the same name, mode and
   priority.

### Scenario A13b — *unchecking a dimension stores it as `false`*

#### Given

1. A rule exists with `users: [fmre2e-user-a]` and
   `groups: [fmre2e-group-b]`.

#### When

1. The administrator opens the alloweds dialog, unchecks **Set groups**
   and saves.

#### Then

1. The rule has `groups: false` and still `users: [fmre2e-user-a]`.
2. Reopening the dialog, without reloading the page, shows **Set
   groups** unchecked.

### Scenario A13c — *closing the alloweds dialog without saving changes nothing*

#### When

1. The administrator opens the alloweds dialog, checks **Set groups**,
   selects a group and closes the dialog without saving.

#### Then

1. No `POST /api/v4/item/allowed/update/frontend_mode_rules` is sent.
2. The rule's `allowed` is unchanged in the API.
3. Opening the dialog of **another** rule shows that rule's alloweds, not
   the discarded selection.

### Scenario A14 — *non-admins cannot open the page*

#### When

1. A manager (`managerE2EPage`) navigates to
   `/isard-admin/admin/frontend_mode`.

#### Then

1. The page is not rendered: `#frontend-mode-rules-table` and the
   **Add rule** button are absent and the rules are not requested.
2. The sidebar of the manager has no **Frontend** entry.

> The sidebar is checked first: the rejected navigation logs the
> manager's Flask session out (see *Common roles and prerequisites*).

---

## SECTION B — API contract through the SDK

Only the priority uniqueness required by CE-07 and a not-found smoke
check; the rest of the endpoint contract lives in the unit suite.

### Scenario B1 — *priorities are unique on create and on edit* (CE-07)

#### Given

1. Rules `R1` (priority `P`) and `R2` (priority `P+1`) exist.

#### When / Then

1. Creating a rule with priority `P` → `409`, `duplicated_priority`;
   nothing is stored.
2. Editing `R2` to priority `P` → `409`, `duplicated_priority`; `R2`
   keeps `P+1`.
3. Editing `R1` sending its own priority `P` → `204`.

### Scenario B2 — *unknown rule ids answer 404*

#### When / Then

1. `GET`, `PUT` and `DELETE` on a random id each respond with `404`.

---

## SECTION C — Effect of the rule on the user

Unless stated otherwise the rules are created through the SDK and the
target user is `fmre2e-user-a`.

### Scenario C1 — *a category rule reaches its users and nobody else* (CE-01)

#### Given

1. The admin creates a rule with `categories: [fmre2e]` and a mode
   different from the installation mode.

#### When

1. `fmre2e-user-a` logs in.
2. The control user (category `default`) requests their configuration.

#### Then

1. Within 60 s `GET /api/v4/item/user/get-config` returns the rule's
   mode for `fmre2e-user-a`.
2. `fmre2e-user-b` (same category) gets the rule's mode too.
3. The control user gets the installation mode.

### Scenario C2 — *the highest priority wins* (CE-08)

#### Given

1. Rule `categories: [fmre2e]`, priority `P`, mode `all`.
2. Rule `users: [fmre2e-user-a]`, priority `P+10`, mode `actual`.

#### Then

1. `fmre2e-user-a` gets `actual`.
2. `fmre2e-user-b` gets `all`.
3. After swapping the two priorities through the SDK, `fmre2e-user-a`
   gets `all` (within 60 s).

### Scenario C3 — *matching one dimension is enough* (CE-09)

#### Given

1. A rule with `categories: [fmre2e]` **and** `roles: [admin]`, with a
   mode different from the installation mode.

#### Then

1. `fmre2e-user-a` (category `fmre2e`, role `user`) gets the rule's mode.

### Scenario C4 — *group and role dimensions match only their members*

#### Given

1. A rule with `groups: [fmre2e-group-a]`, priority `P`, mode `hidden`.
2. A rule with `roles: [advanced]` is **not** created: it would reach
   every advanced user of the stack. The role dimension is covered by C3.

#### Then

1. `fmre2e-user-a` and `fmre2e-advanced` (group A) get `hidden`.
2. `fmre2e-user-b` (group B) does not get it.

### Scenario C5 — *`deprecated` sends the user to the old frontend* (CE-11)

#### Given

1. A rule with mode `deprecated` matches the user; the installation mode
   is not `deprecated`.

#### When

1. The user opens `/frontend/desktops`.

#### Then

1. The browser ends on `/desktops` (old frontend) and the desktops list
   renders.
2. The switch button (`.frontend-toggler`) is not present.
3. Opening `/frontend/templates` ends on `/templates`.

### Scenario C6 — *`actual` sends the user to the new frontend*

#### Given

1. A rule with mode `actual` matches the user.

#### When

1. The user opens `/desktops` (old frontend).

#### Then

1. The browser ends on `/frontend/desktops`.
2. The switch button is not present.
3. `localStorage.preferredFrontend` is unset.
4. Opening `/templates` ends on `/frontend/templates`: the redirect keeps
   applying to every route that has a new-frontend equivalent.

### Scenario C7 — *an `actual` user reaches their bookings in the old frontend* (CE-03)

#### Given

1. A rule with mode `actual` matches the user, who has a booking.

#### When

1. The user opens the bookings entry of the new frontend sidebar.
2. Later they open `/booking/summary` directly by URL.
3. From the bookings page they open `/desktops`.

#### Then

1. After step 1 the browser ends on `/booking/summary` (old frontend)
   and stays there: it is not redirected to `/frontend/desktops`.
2. The user's booking is listed.
3. After step 2 the page also stays on `/booking/summary`.
4. After step 3 the browser ends on `/frontend/desktops`: only the
   bookings and plannings routes are exempt from the redirect.
5. The switch button is not present on the bookings page.

### Scenario C7b — *an `actual` manager reaches the planning in the old frontend*

#### Given

1. A rule with mode `actual` and `users: [fmre2e-manager]`.

#### When

1. `fmre2e-manager` logs in and opens `/planning` by URL.
2. From the planning page they open `/desktops`.

#### Then

1. After step 1 the browser stays on `/planning` (old frontend) and the
   planning page renders: it is not redirected to `/frontend/desktops`.
2. The switch button is not present.
3. After step 2 the browser ends on `/frontend/desktops`.

> The page only admits the `admin` and `manager` roles, hence the
> dedicated manager. The scenario checks that the route is reachable,
> not the planning contents.

### Scenario C8 — *`hidden` allows both frontends without the switch* (CE-12)

#### Given

1. A rule with mode `hidden` matches the user.

#### Then

1. `/frontend/desktops` renders in the new frontend, with no redirect and
   no switch button.
2. `/desktops` renders in the old frontend, with no redirect and no
   switch button.

### Scenario C9 — *`all` shows the switch and it changes frontend* (CE-01)

#### Given

1. A rule with mode `all` matches the user (see *Common data* when the
   installation mode is also `all`).

#### When

1. The user opens `/frontend/desktops` and presses the switch button.
2. In the old frontend they press the switch button again.

#### Then

1. The button is visible in the new frontend; pressing it lands on
   `/desktops` and stores `preferredFrontend = vue2`.
2. The button is visible in the old frontend; pressing it lands on
   `/frontend/desktops` and stores `preferredFrontend = vue3`.
3. On an edit form (e.g. new desktop) the button is not shown.

### Scenario C10 — *changing the mode of a rule changes what its users get*

#### Given

1. A rule with mode `hidden` matches the user.

#### When

1. The admin edits the rule to `deprecated` from the edit dialog (as in A11).
2. The user reloads the page.

#### Then

1. Within 60 s `get-config` returns `deprecated` and, after a reload,
   `/frontend/desktops` redirects to `/desktops`.

### Scenario C11 — *an `actual` user can hold several temporary desktops* (CE-13)

#### Given

1. A rule with mode `actual` matches the user, who has no temporary
   desktops of template `T`.

#### When

1. The user creates a temporary desktop from `T` twice
   (`POST /api/v4/item/desktop/new-nonpersistent`).

#### Then

1. Both calls respond with status `< 400` and return **different** ids.
2. The user has two temporary desktops of `T`.

### Scenario C12 — *choosing the new frontend under `all` does not give the `actual` behaviour* (CE-05)

#### Given

1. A rule with mode `all` matches the user, who switched to the new
   frontend with the button (`preferredFrontend = vue3`).

#### When

1. They create a temporary desktop from `T` twice from the new frontend.

#### Then

1. The second request returns the **same** desktop id as the first.
2. The user has exactly one temporary desktop of `T`.

### Scenario C13 — *leaving `actual` collapses the temporary desktops of a template* (CE-04)

#### Given

1. A rule with mode `actual` is the only one matching the user.
2. The user has three temporary desktops of `T`.

#### When

1. The admin deletes the rule.
2. Once `get-config` no longer returns `actual`, the user starts `T` again.

#### Then

1. The three previous desktops are deleted.
2. Exactly one temporary desktop of `T` exists, with a new id.

### Scenario C14 — *editing the alloweds from the dialog changes who the rule reaches*

#### Given

1. A rule with `users: [fmre2e-user-b]` and a mode different from the
   installation mode. `fmre2e-user-a` gets the installation mode.

#### When

1. The administrator adds `groups: [fmre2e-group-a]` from the alloweds
   dialog (as in A13).
2. Later they uncheck **Set groups** and save again.

#### Then

1. After step 1, within 60 s `get-config` returns the rule's mode for
   `fmre2e-user-a`; `fmre2e-user-b` keeps it.
2. After step 2, within 60 s `fmre2e-user-a` is back to the installation
   mode.

---

## Cleanup (afterEach)

- `cleanupTrackedResources(apiv4Admin, testInfo)` deletes every tracked
  rule, even when assertions fail; in section C also the temporary
  desktops.
- Section C: target users' browser contexts are closed.
- `beforeAll` runs `purgeE2eFrontendModeRules`; `afterAll` asserts that no
  `e2e-fmr-` rule is left.

## Traceability with the project acceptance cases

Only CE-07 is covered by the administration page; the other cases belong
to section C and arrive with the later merge request.

| Case | Scenario(s) | Automation |
| --- | --- | --- |
| CE-01 | C1, C9 | ✅ with a mode different from the installation mode |
| CE-03 | C7 | ✅ |
| CE-04 | C13 | ✅ |
| CE-05 | C12 | ✅ |
| CE-07 | A5, A6, A12, A12b, B1 | ✅ create and edit, in the form and from the server |
| CE-08 | C2 | ✅ |
| CE-09 | C3 | ✅ |
| CE-11 | C5 | ✅ |
| CE-12 | C8 | ✅ |
| CE-13 | C11 | ✅ |

CE-02, CE-10, CE-14, CE-15, CE-16 and CE-17 are not part of this
contract. Scenarios without a case (A1–A4, A7–A11d, A13–A14, B2, C4, C6,
C7b, C10, C14) are added for coverage of the page, of the alloweds edition and
of the remaining modes.

## APIs touched by the flows (reference)

- `GET    /api/v4/items/frontend-mode-rules` — list, ordered by priority
  (highest first). Response `{ rules: [...] }`. Admin only.
- `GET    /api/v4/item/frontend-mode-rule/{id}` — one rule; `404` if
  unknown. Pre-fills the edit dialog.
- `POST   /api/v4/item/frontend-mode-rule` — create. `204` with no body;
  `409` `duplicated_priority`.
- `PUT    /api/v4/item/frontend-mode-rule/{id}` — partial update; a sent
  `allowed` replaces the whole object. `204`; `404`; `409`. The edit
  dialog always sends `name`, `description`, `frontend_mode` and
  `priority`, never `allowed`.
- `POST   /api/v4/item/allowed/table/frontend_mode_rules` — body
  `{ id }`; the rule's alloweds enriched with names, used to pre-fill the
  dialog. Admin only for this table.
- `POST   /api/v4/item/allowed/update/frontend_mode_rules` — body
  `{ id, allowed, table }`; replaces the alloweds and clears the rules
  cache. `204`. Admin only for this table.
- `DELETE /api/v4/item/frontend-mode-rule/{id}` — `204`; `404`.
- `GET    /api/v4/item/user/get-config` — `frontend_mode` of the caller.
- `POST   /api/v4/item/desktop/new-nonpersistent` — temporary desktop;
  reuses the template's desktop unless the caller's mode is `actual`.

## Relevant database state

- `frontend_mode_rules` table: `id` (server-generated), `name`,
  `description`, `priority`, `frontend_mode`, `allowed`
  (`users` / `groups` / `categories` / `roles`, each `false` or a list).

## Known issues / cases not covered

1. **The alloweds dialog renders the rule name as HTML** (from reading
   the code, to confirm on a stack): the shared `modalAllowedsFormShow`
   sets `#alloweds_name` with `.html(data.name)`, so a rule name with
   markup is injected into the dialog title. A8b is marked `test.fail`
   until the shared snippet escapes the name; it will then report an
   unexpected pass and the mark must be removed.
2. **Empty alloweds list**: checking a dimension in the add or the
   alloweds dialog without
   selecting any value sends `[]`, which applies the rule to every user.
   It is not automated because it would change the frontend of every
   parallel spec; it stays a manual check on an isolated stack.
3. **Cache across processes**: the cache is cleared in the process that
   handles the write (rule endpoints and alloweds update alike);
   assertions always poll up to 60 s instead of
   assuming an immediate change.
