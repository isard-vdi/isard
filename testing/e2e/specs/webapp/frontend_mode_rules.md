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
| Administration page | A | The previous one (`test/7478-frontend-mode-rules-admin-e2e`) |
| API contract and effect of the rule on the user | B, C | This one |

Requirements of the effect on the user and the scenarios that cover
them:

| Requirement | Scenarios |
| --- | --- |
| On login the user lands on the frontend of the rule applied by category | C1 |
| … by group | C2 |
| … by role | C3 |
| … by specific user | C4 |
| Priority when more than one rule matches | C6 (and C3, C5) |
| Default behaviour when no rule matches | C7 |
| One scenario per frontend mode | `deprecated` C8, `actual` C9, `hidden` C12, `all` C13 |

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
6. `get-config` is cached per user for `USER_CONFIG_CACHE_TTL` seconds
   (60 by default, 1 on the e2e stack) and carries the frontend mode. A
   rule change therefore takes up to that long to reach `get-config`,
   and the frontends only read `get-config` on page load, so the user
   also has to reload.

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
| Control user | `user_e2e_NN` (category `default`), never matched by a test rule. Its mode is read once before the scenarios (**control mode**) and must not change |
| Installation mode | Whatever `FRONTEND_MODE` the stack runs with (`all` in CI). Read at runtime from the `get-config` of `fmre2e-user-b`, before any scenario creates a rule, and referred to below as **installation mode** |
| Desktop scenarios (C16–C18) | Hypervisor online, a template allowed to the target user that needs no GPU booking (the first enabled one without GPU reservables among the user's allowed templates; `template-test-001` in CI) and a `volatile` quota of at least 3 |
| Bookings menu (C10) | `FRONTEND_SHOW_BOOKINGS=True` on the stack, set by `testing/config/isardvdi.e2e.cfg.template`: it is off by default and hides the **Bookings** entry from every non-admin |

### Seed data

A rule scoped to a category, group or role reaches every user in it, so
those scenarios must never target the shared `default` category: a
`deprecated` rule on it would redirect every other spec running in
parallel. The scenarios use a dedicated category seeded in
`testing/src/isardvdi_testing/data/` (same approach as `qle2e`). Nobody
else logs in with these accounts, so the rules can point at them without
changing the frontend of any running spec:

| Item | Value | Used for |
| --- | --- | --- |
| Category | `fmre2e` (hidden from the login dropdown) | Category-scoped rules |
| Groups | `fmre2e-group-a`, `fmre2e-group-b` | Group-scoped rules |
| `fmre2e-user-a` | role `user`, group A | Main target user |
| `fmre2e-user-b` | role `user`, group B | Same category, other group |
| `fmre2e-advanced` | role `advanced`, group A, disclaimer acknowledged | Role-scoped rule (C3), group member (C2) |
| `fmre2e-manager` | role `manager`, group A | Planning page under `actual` (C11); not used by section A |

The ids equal the usernames and the password is the one of the other
e2e accounts. The alloweds selectors search by display name, hence the
names above. The accounts and the category are listed in
`fixtures/login.js` (`users.fmre2e_*`, `categories.fmre2e`).
`fmre2e-advanced` is seeded with `disclaimer_acknowledged: true`:
advanced users otherwise get a disclaimer token at login instead of a
session. The seeded template `template-test-001` (category `default`) is
shared with the `fmre2e` category through its `allowed.categories`, so the
temporary-desktop scenarios find a template on a stack that only has the
seed, as in CI. On a stack with more templates they use the first one by
name.

## Common data

| Field | Sample value | Notes |
| --- | --- | --- |
| Name | `e2e-fmr-<scenario>-<timestamp>` | Required, 1–50 chars. The `e2e-fmr-` prefix identifies leftovers |
| Description | `created by e2e` | Optional, up to 255 chars; stored as `""` when omitted |
| Frontend mode | `deprecated` \| `actual` \| `all` \| `hidden` | Required |
| Priority | From `nextFrontendModeRulePriority()` | Required, integer, unique |
| Allowed | `{ users: [<id>] }` and the like | Unset dimensions are stored as `false` |

When a scenario must prove that the mode comes from the rule, the rule
uses the **contrast mode** (different from the installation mode). Where
the scenario needs one specific mode and the installation mode is that
same mode, a lower-priority **guard rule** on the `fmre2e` category is
created first so that the mode can only come from the rule under test.
Both are described at the top of section C, with the one exception to
the mode the guard rule carries.

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
| `waitForFrontendMode(client, expected, { timeoutMs = 65000, intervalMs = 250 })` | Polls `getUserConfig` with the **target user's** client, every `intervalMs`, until `frontend_mode` equals `expected` |

Other helpers section C relies on:

| Helper | Where | Behaviour |
| --- | --- | --- |
| `loginHelpers.apiLogin(playwright, baseURL, user, categories)` | `fixtures/login.js` | Logs a user in through `POST /authentication/login`, without a browser, and returns an `APIRequestContext` carrying the Bearer token |
| `apiv4ClientForRequest(request)` | `fixtures/apiv4/client.js` | SDK client over a bare `APIRequestContext` (`apiv4ClientForPage` now delegates to it) |
| `targets` fixture | the spec file | `targets.api(key)` → SDK client of an API-only login; `targets.browser(key)` → `{ page, client }` of a browser login on a fresh context. Closes everything it opened when the test ends |
| `getTemporaryDesktopTemplate(client)` | `fixtures/apiv4/desktops.js` | First enabled template allowed to the caller without GPU reservables |
| `createTemporaryDesktopAndTrack(client, testInfo, templateId)` | idem | `POST new-nonpersistent` as the caller; tracks the returned id as `desktop-id` and returns the raw SDK result |
| `listTemporaryDesktops(client, templateId)` | idem | The caller's temporary desktops of the template |
| `waitForTemporaryDesktops(client, templateId, predicate)` / `waitForTemporaryDesktopsSettled(…)` | idem | Poll that list until the predicate holds / until every desktop is `Started`, `WaitingIP` (started, wireguard interface, no guest IP yet), `Stopped` or `Failed` |
| `deleteTemporaryDesktops(client, templateId)` | idem | Deletes them and waits until the list is empty |

Safety guard: `createFrontendModeRuleAndTrack`, `updateFrontendModeRule`
and `setFrontendModeRuleAllowed` throw when any `allowed` dimension is `[]`, because that rule would apply
to every user of the stack (see *How a rule is applied*, point 3).

Rules created through the UI are tracked with
`track(testInfo, 'frontend-mode-rule-id', id)` as soon as they exist.

## Concurrency & ordering

- The rules are global configuration: the file runs with
  `test.describe.configure({ mode: 'default' })`, one test at a time and
  in order. It is not `serial`: every scenario creates the rules it
  needs, so a failure does not skip the scenarios after it and a retry
  repeats only the failed one.
- No rule may change the mode of users outside the `fmre2e` category.
  The two rules that reach further (`roles: [advanced]` in C3,
  `roles: [admin]` in C5) carry the installation mode, so those users
  keep getting what they already had.
- Section C scenarios poll `get-config` up to 65 s after every rule
  change and raise the test timeout to 300 s (420 s for the
  temporary-desktop ones), which covers a stack with the default 60 s
  cache. With `USER_CONFIG_CACHE_TTL=1`, set by
  `testing/config/isardvdi.e2e.cfg.template`, a change is seen within a
  couple of seconds.
- The installation mode is read from an `fmre2e` user before any
  scenario creates a rule, so a rule left on the stack by hand that
  reaches the control user does not change what the scenarios expect.
- A target user logs in on a **new browser context** per test, so
  `localStorage.preferredFrontend` starts empty.
- The sessions service keeps one session per user: a test never holds
  two live sessions of the same account (API-only login first, browser
  login afterwards).
- *Without reloading the page*: after the first load the test sets a
  marker on `window` and asserts it is still there once the table shows
  the change. Checked in A2, A2b, A9, A11, A11b, A11d and A13. The table
  has no alloweds column, so for A13 the change shows when the dialog is
  reopened on the same page load.

## Implementation status

| Section | Spec file | Status |
| --- | --- | --- |
| A | `tests/webapp/frontend_mode_rules.spec.js` | ✅ every scenario automated |
| B | `tests/webapp/frontend_mode_rules.spec.js` | ✅ B1, B2 automated |
| C | `tests/webapp/frontend_mode_rules.spec.js` | ✅ C1–C18 automated |

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

### Scenario A2 — *admin creates a rule and sees it listed without reloading*

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
> the confirmation) and **A8b** (assertion 2).

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

1. A rule exists with `allowed = { users: [fmre2e-user-a] }` and mode
   `deprecated`.

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

Common mechanics of every scenario:

- **Installation mode** is read once (`beforeAll`) from the `get-config`
  of `fmre2e-user-b`, through an API-only login, while no test rule
  exists. It is not read from the control user: a rule left on the stack
  by hand can reach the `default` category, never `fmre2e`.
- **Control mode** is what the control user gets at that same moment.
  No scenario may change it.
- **Contrast mode** is a mode that differs from the installation mode and
  lands on the other frontend after the login: `actual`, or `deprecated`
  when the installation mode is `actual`. A user can only get it from a
  rule.
- **Waiting for the mode**: the target user is first logged in through
  the API only and `get-config` is polled (up to 65 s) until it returns
  the expected mode. Only then is the user logged in with the browser, so
  the landing is decided by the rule and not by the cache. Every login
  ends the user's previous session, so the browser session is the one the
  test keeps using.
- **Landing**: the login sends a user without a stored preference to
  `/`. With `actual` the old frontend redirects it to
  `/frontend/desktops` (new frontend, `[data-sidebar="sidebar"]`);
  with any other mode it stays on `/desktops` (old frontend,
  `#main-layout`). The layout only renders once the router guard that
  applies the mode let the route through, so "stays on" is asserted by
  the URL after the layout is visible.
- **Switch button**: `.frontend-toggler` in the old frontend, the button
  *Switch to legacy interface* / *No legacy equivalent* in the new one.
  Absence is checked after the page's requests settle.
- **Guard rule**: when the mode under test equals the installation mode,
  a lower-priority rule on the whole `fmre2e` category with another mode
  (`hidden`, or `all` when testing `hidden`) is created first, so the mode
  can only come from the rule under test. C14 goes through two modes
  (`hidden`, then `deprecated`) and its guard uses `all`, which is
  neither.

### Who a rule reaches

#### Scenario C1 — *a category rule reaches its users and nobody else* (CE-01)

##### Given

1. A rule with `categories: [fmre2e]` and mode `all` (guard rule when the
   installation mode is `all`).

##### Then

1. `fmre2e-user-b` (same category) gets `all` from `get-config`.
2. `fmre2e-user-a` logs in, lands on `/desktops` (old frontend) and sees
   the switch button.
3. The control user (category `default`) still gets the control mode.

#### Scenario C2 — *a group rule reaches only the members of the group*

##### Given

1. A rule with `groups: [fmre2e-group-a]` and the contrast mode.

##### Then

1. `fmre2e-advanced` (group A) gets the contrast mode.
2. `fmre2e-user-b` (group B) gets the installation mode.
3. `fmre2e-user-a` (group A) logs in and lands on the frontend of the
   contrast mode.

#### Scenario C3 — *a role rule reaches the users of the role*

##### Given

1. Rule `users: [fmre2e-advanced]`, priority `P`, contrast mode.
2. Rule `roles: [advanced]`, priority `P+1`, **installation mode**.

> `roles: [advanced]` reaches every advanced user of the stack, so it
> carries the installation mode and changes nothing for them. The lower
> rule shows whether the role rule applies.

##### Then

1. `fmre2e-advanced` logs in and lands on the frontend of the
   installation mode: the role rule outranks the user rule.
2. After deleting the role rule through the SDK, within 60 s
   `get-config` returns the contrast mode and opening `/` lands on its
   frontend.

#### Scenario C4 — *a user rule reaches only that user*

##### Given

1. A rule with `users: [fmre2e-user-a]` and the contrast mode.

##### Then

1. `fmre2e-user-b` gets the installation mode.
2. `fmre2e-user-a` logs in and lands on the frontend of the contrast
   mode.

#### Scenario C5 — *matching one dimension is enough* (CE-09)

##### Given

1. Rule `users: [fmre2e-user-a]`, priority `P`, contrast mode.
2. Rule `categories: [fmre2e]` **and** `roles: [admin]`, priority `P+1`,
   installation mode (it also reaches the admins of the stack, so it
   changes nothing for them).

##### Then

1. `fmre2e-user-a` (category `fmre2e`, role `user`) logs in and lands on
   the frontend of the installation mode: the second rule applies
   although the role does not match.
2. After deleting it, within 60 s the user gets the contrast mode and `/`
   lands on its frontend.

#### Scenario C6 — *the highest priority wins* (CE-08)

##### Given

1. Rule `categories: [fmre2e]`, priority `P+1`, mode `all` (guard rule at
   `P` when the installation mode is `all`).
2. Rule `users: [fmre2e-user-a]`, priority `P+11`, mode `actual`.

##### Then

1. `fmre2e-user-b` gets `all`.
2. `fmre2e-user-a` logs in and lands on `/frontend/desktops`.
3. After raising the category rule to `P+21` through the SDK,
   `fmre2e-user-a` gets `all` within 60 s; opening `/` lands on
   `/desktops` with the switch button.

#### Scenario C7 — *a user no rule matches gets the installation mode*

##### Given

1. A rule with `users: [fmre2e-user-b]` and the contrast mode: rules
   exist, but none matches `fmre2e-user-a`.

##### Then

1. `fmre2e-user-b` gets the contrast mode.
2. `fmre2e-user-a` logs in, gets the installation mode and lands on its
   frontend; the switch button shows only if that mode is `all`.
3. The control user still gets the control mode.

### One scenario per mode

#### Scenario C8 — *`deprecated` sends the user to the old frontend* (CE-11)

##### Given

1. A rule with mode `deprecated` matches the user (guard rule when the
   installation mode is `deprecated`).

##### Then

1. The login lands on `/desktops` (old frontend) without switch button.
2. Opening `/frontend/desktops` ends on `/desktops`, without switch
   button.
3. Opening `/frontend/profile` ends on `/profile`.

> The spec used `/frontend/templates`; templates are not open to the
> `user` role, so the new frontend answers 403 before the mode applies.
> The profile has an equivalent in both frontends and is open to every
> role.

#### Scenario C9 — *`actual` sends the user to the new frontend*

##### Given

1. A rule with mode `actual` matches the user (guard rule when the
   installation mode is `actual`).

##### Then

1. The login lands on `/frontend/desktops`, without switch button and
   with `localStorage.preferredFrontend` unset.
2. Opening `/desktops` ends on `/frontend/desktops`.
3. Opening `/profile` ends on `/frontend/profile`; still no switch button
   and no stored preference.

#### Scenario C10 — *an `actual` user reaches their bookings in the old frontend* (CE-03)

##### Given

1. A rule with mode `actual` matches the user (guard rule when the
   installation mode is `actual`).

##### When

1. The user logs in (lands on `/frontend/desktops`) and opens the
   **Bookings** entry of the new frontend sidebar.
2. Later they open `/booking/summary` directly by URL.
3. Then they open `/desktops`.

##### Then

1. After step 1 the browser ends on `/booking/summary` (old frontend) and
   stays there; the calendar renders and the user's bookings request
   (`GET /api/v4/items/bookings`) answers `200`. No switch button.
2. After step 2 the page also stays on `/booking/summary`.
3. After step 3 the browser ends on `/frontend/desktops`: only the
   bookings and plannings routes are exempt from the redirect.

> The scenario checks that the user's bookings are requested and the
> page renders them; it does not seed a booking (that needs a GPU plan
> for the category). The listing itself is covered by
> `tests/vue2/bookings.spec.js`.

#### Scenario C11 — *an `actual` manager reaches the planning in the old frontend*

##### Given

1. A rule with mode `actual` and `users: [fmre2e-manager]` (guard rule
   when the installation mode is `actual`; the manager belongs to the
   `fmre2e` category, so it reaches them).

##### Then

1. The manager logs in and lands on `/frontend/desktops`.
2. Opening `/planning` stays on `/planning` (old frontend) and the
   planning page renders, without switch button.
3. Opening `/desktops` then ends on `/frontend/desktops`.

> The page only admits the `admin` and `manager` roles, hence the
> dedicated manager. The scenario checks that the route is reachable,
> not the planning contents.

#### Scenario C12 — *`hidden` allows both frontends without the switch* (CE-12)

##### Given

1. A rule with mode `hidden` matches the user (guard rule when the
   installation mode is `hidden`).

##### Then

1. The login lands on `/desktops` (old frontend), without switch button.
2. `/frontend/desktops` renders in the new frontend, with no redirect and
   no switch button.
3. `/desktops` renders in the old frontend, with no redirect and no
   switch button.

#### Scenario C13 — *`all` shows the switch and it changes frontend* (CE-01)

##### Given

1. A rule with mode `all` matches the user (guard rule when the
   installation mode is `all`).

##### When

1. The user logs in and presses the switch button.
2. In the new frontend they press the switch button again.
3. They open the new-desktop form of each frontend.

##### Then

1. The login lands on `/desktops`, with the button *Switch to new
   interface*; pressing it lands on `/frontend/desktops` and stores
   `preferredFrontend = vue3`.
2. The button *Switch to legacy interface* is visible; pressing it lands
   on `/desktops` and stores `preferredFrontend = vue2`.
3. Neither `/frontend/desktops/new` nor `/desktops/new` shows the button.

### Changes made from the administration page

#### Scenario C14 — *changing the mode of a rule changes what its users get*

##### Given

1. A rule with mode `hidden` matches the user, who has
   `/frontend/desktops` open (guard rule with mode `all` when the
   installation mode is `hidden` or `deprecated`, the two modes the rule
   goes through).

##### When

1. The admin edits the rule to `deprecated` from the edit dialog (as in
   A11).
2. The user reloads the page.

##### Then

1. Within 60 s `get-config` returns `deprecated` and, after the reload,
   `/frontend/desktops` ends on `/desktops`.

#### Scenario C15 — *editing the alloweds from the dialog changes who the rule reaches*

##### Given

1. A rule with `users: [fmre2e-user-b]` and the contrast mode.
   `fmre2e-user-a` gets the installation mode.

##### When

1. The administrator adds `groups: [fmre2e-group-a]` from the alloweds
   dialog (as in A13).
2. Later they uncheck **Set groups** and save again.

##### Then

1. After step 1, within 60 s `get-config` returns the contrast mode for
   `fmre2e-user-a`; `fmre2e-user-b` keeps it.
2. After step 2, within 60 s `fmre2e-user-a` is back to the installation
   mode and `fmre2e-user-b` keeps the contrast mode.

### Temporary desktops

The template `T` is the first enabled one allowed to the user that needs
no GPU booking. Leftover temporary desktops of `T` are deleted before each
scenario, and every desktop is tracked and deleted in `afterEach`.

#### Scenario C16 — *an `actual` user can hold several temporary desktops* (CE-13)

##### Given

1. A rule with mode `actual` matches the user (guard rule when the
   installation mode is `actual`); `get-config` returns
   `multiple_temporal_desktops = true`.

##### When

1. The user creates a temporary desktop from `T` twice
   (`POST /api/v4/item/desktop/new-nonpersistent`).

##### Then

1. Both calls respond with status `< 400` and return **different** ids.
2. The user has exactly those two temporary desktops of `T`.

#### Scenario C17 — *choosing the new frontend under `all` does not give the `actual` behaviour* (CE-05)

##### Given

1. A rule with mode `all` matches the user (guard rule when the
   installation mode is `all`), who logs in and switches to the new
   frontend with the button (`preferredFrontend = vue3`).
2. `get-config` returns `multiple_temporal_desktops = false`.

##### When

1. With that same session they create a temporary desktop from `T`, wait
   for it to settle and create one again.

##### Then

1. The second request returns the **same** desktop id as the first.
2. The user has exactly one temporary desktop of `T`.

> The requests go through the API with the session that switched: the
> server decides by the mode, it does not know which frontend sends them.
> While the first desktop is still being created the endpoint answers
> `428`, hence the wait.

#### Scenario C18 — *leaving `actual` collapses the temporary desktops of a template* (CE-04)

##### Given

1. A rule with mode `actual` is the only one matching the user (guard
   rule when the installation mode is `actual`).
2. The user has three temporary desktops of `T`, settled.

##### When

1. The admin deletes the rule.
2. Once `get-config` no longer returns `actual`, the user starts `T`
   again.

##### Then

1. The returned id is new, and within 60 s the three previous desktops
   are gone.
2. Exactly one temporary desktop of `T` exists: the new one.

---

## Cleanup (afterEach)

- `cleanupTrackedResources(apiv4Admin, testInfo)` deletes every tracked
  rule, even when assertions fail; in section C also the temporary
  desktops (admin client, after the rules).
- Section C: the `targets` fixture closes the target users' browser
  contexts and API sessions.
- `beforeAll` runs `purgeE2eFrontendModeRules`; `afterAll` asserts that no
  `e2e-fmr-` rule is left.

## Traceability with the project acceptance cases

| Case | Scenario(s) | Automation |
| --- | --- | --- |
| CE-01 | C1, C13 | ✅ category rule with `all`, switch button, other category keeps the mode it had |
| CE-03 | C10 | ✅ route and bookings request; no booking is seeded (see *Known issues*, point 3) |
| CE-04 | C18 | ✅ |
| CE-05 | C17 | ✅ |
| CE-07 | A5, A6, A12, A12b, B1 | ✅ create and edit, in the form and from the server |
| CE-08 | C6 | ✅ |
| CE-09 | C5 | ✅ with the role rule carrying the installation mode |
| CE-11 | C8 | ✅ |
| CE-12 | C12 | ✅ |
| CE-13 | C16 | ✅ |

CE-02, CE-10, CE-14, CE-15, CE-16 and CE-17 are not part of this
contract. Scenarios without a case (A1–A4, A7–A11d, A13–A14, B2, C2–C4,
C7, C9, C11, C14, C15) are added for coverage of the page, of the
dimensions a rule can target, of the default behaviour and of the
remaining modes.

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
  reuses the template's desktop unless the caller's mode is `actual`;
  `428` while that desktop is still being created.
- `POST   /authentication/login?provider=form&category_id=…` — API-only
  login of the target users.
- `GET    /api/v4/items/desktops` — the caller's desktops; filtered by
  `type = nonpersistent` and `template`.
- `GET    /api/v4/items/bookings` — the bookings the old frontend's
  summary page lists.

## Relevant database state

- `frontend_mode_rules` table: `id` (server-generated), `name`,
  `description`, `priority`, `frontend_mode`, `allowed`
  (`users` / `groups` / `categories` / `roles`, each `false` or a list).

## Known issues / cases not covered

1. **Empty alloweds list**: checking a dimension in the add or the
   alloweds dialog without
   selecting any value sends `[]`, which applies the rule to every user.
   It is not automated because it would change the frontend of every
   parallel spec; it stays a manual check on an isolated stack.
2. **A rule change is not immediate**: `get-config` serves
   `frontend_mode` from the per-user config body, cached for
   `USER_CONFIG_CACHE_TTL` seconds (60 by default). A write clears the
   rules cache but not that one, so the change takes up to that long to
   reach the user, as the ticket states. Assertions therefore always
   poll up to 65 s. The e2e stack sets the variable to 1 so the spec
   does not spend a minute per rule change; production keeps 60.
3. **Bookings of the user (CE-03)**: C10 checks that the bookings page
   of the old frontend is reached, stays, renders and requests the
   user's bookings (`200`). It does not seed a booking, which needs a
   bookable GPU planned for the `fmre2e` category.
4. **Role-only and admin-role rules**: a rule with `roles: [...]`
   reaches every user of that role in the stack. C3 and C5 only create
   them with the installation mode and prove they apply through a
   lower-priority rule; a role rule with a different mode stays a manual
   check on an isolated stack. "Changes nothing" assumes the stack has
   no rule of its own on those users: if one gives an advanced user or
   an admin a mode other than the installation one, C3 and C5 outrank
   it while they run.
5. **Temporary desktops from the UI (CE-05)**: C17 switches frontend
   with the button and then sends the two requests through the API with
   that session, not by clicking a template in the new frontend.
6. **Installation mode read from a cached `get-config`**: section C
   reads it once per worker. After a failure Playwright starts a new
   worker, which reads it again; on a stack with the default 60 s cache
   that read can still return the mode of the rule the failed scenario
   had on `fmre2e-user-b` (C1, C6, C7, C15 and the guard rules), and the
   remaining scenarios would then expect the wrong mode. With
   `USER_CONFIG_CACHE_TTL=1` the cache has expired by then.
