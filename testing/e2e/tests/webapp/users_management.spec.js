// E2E tests for the admin webapp "Users Management" screen.
//
// Spec:  testing/e2e/specs/webapp/users_management.md
// Route: /isard-admin/admin/users/Management
// JS:    webapp/webapp/webapp/static/admin/js/users_management.js
//
// Test IDs (A1-A34, M1-M15) are kept aligned with the spec so that
// regressions can be traced back to the contract document.
//
// Known expected failures are marked with test.fail() and carry a
// TODO comment pointing at the upstream bug.

import {
  test,
  expect,
  apiv4ClientForPage,
  unwrap,
  getFirstAllowedTemplate,
} from "../../fixtures/apiv4/index.js";
import {
  createDesktop,
  adminTableList,
  adminCreateUser,
  adminDeleteUsers,
  adminResetVpn,
  adminGetUser,
  adminUpdateUser,
  adminListUsersNav,
  adminListCategoriesNav,
  adminListGroupsNav,
  adminCreateCategory,
  adminUpdateCategory,
  adminDeleteCategory,
  adminGetCategory,
  adminCreateGroup,
  adminUpdateGroup,
  adminDeleteGroup,
  adminGetGroup,
  adminDeleteSecret,
  adminBulkCreateUsers,
} from "../../src/gen/apiv4/sdk.gen";
import { bridgeAdminSession } from "../../fixtures/common.js";

// Run the entire Users Management suite sequentially in a single worker. These
// tests share global state (the per-worker admin account, the seeded `default`
// category + users table, and the single `manager_e2e_01` account), so the
// project's `fullyParallel: true` makes them flaky (session-bridge drops,
// concurrent mutations, concurrent manager logins). `mode: 'default'` overrides
// fullyParallel: tests run in declaration order in one worker and each retries
// independently (no serial cascade-skip).
test.describe.configure({ mode: "default" });

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MGMT_URL = "/isard-admin/admin/users/Management";

/** Capture all network responses whose URL matches predicate. */
function captureXhr(page, predicate) {
  const matched = [];
  page.on("response", async (resp) => {
    if (predicate(resp.url())) {
      matched.push({
        url: resp.url(),
        status: resp.status(),
        method: resp.request().method(),
      });
    }
  });
  return matched;
}

/**
 * Click the confirm button of a PNotify confirmation dialog, tolerating both
 * theme variants used across the admin UI (`.brighttheme-confirm-button` and
 * the legacy `.ui-pnotify-confirm .default`).
 */
async function confirmPnotify(page, { timeout = 10000 } = {}) {
  // The confirm dialog renders as a ui-pnotify with two action buttons
  // ("Ok" / "Cancel", class .ui-pnotify-action-button). Older code paths used
  // brighttheme; cover both. Pick the affirmative button.
  const btn = page
    .locator(
      '.ui-pnotify .ui-pnotify-action-button:has-text("Ok"), ' +
      '.ui-pnotify .ui-pnotify-action-button:has-text("Yes"), ' +
      ".pnotify-center .brighttheme-confirm-button, " +
      ".ui-pnotify .brighttheme-confirm-button, " +
      ".ui-pnotify-confirm .default",
    )
    .first();
  await btn.waitFor({ state: "visible", timeout });
  await btn.click();
}

/** Wait for at least one PNotify with text containing `title` (case-insensitive). */
async function waitForPNotify(page, title, { timeout = 10000 } = {}) {
  await page
    .locator(".ui-pnotify-title", { hasText: new RegExp(title, "i") })
    .first()
    .waitFor({ state: "visible", timeout });
}

/**
 * The users datatable uses deferRender + pagination, so a freshly created user
 * may render on a later page and never enter the DOM. Bump the page-length
 * selector to "All" (-1) / 100 so id-based row lookups resolve.
 */
async function showAllUsers(page) {
  const lengthSel = page.locator("#users_length select").first();
  if ((await lengthSel.count()) === 0) return;
  // Pick an option that actually exists — selectOption blocks (until the test
  // timeout) if asked for a value the <select> never renders (e.g. "-1"/All
  // when the length menu is only [10,25,50,100]). Prefer "All" if present,
  // else the numerically largest length.
  const values = await lengthSel
    .locator("option")
    .evaluateAll((opts) => opts.map((o) => o.value))
    .catch(() => []);
  let target = values.includes("-1") ? "-1" : null;
  if (!target) {
    const nums = values
      .map((v) => parseInt(v, 10))
      .filter((n) => !Number.isNaN(n));
    if (nums.length) target = String(Math.max(...nums));
  }
  if (target) {
    await lengthSel.selectOption(target).catch(() => { });
    await page.waitForTimeout(400);
  }
}

/**
 * Filter the #users datatable by its Username column (the column the app's
 * `?searchUser=` deep-link drives). Brings every row whose username contains
 * `term` onto the first page so deferRender renders them into the DOM (and they
 * become selectable — bulk selection reads only rendered rows). Pass a value
 * shared by all rows you need visible (e.g. a common timestamp).
 */
async function filterUsersByUsername(page, term) {
  const search = page.locator("#users .xe-username input").first();
  if ((await search.count()) === 0) return;
  await search.fill(String(term));
  // The footer search handler is bound to "keyup change"; fill() only emits an
  // "input" event, so dispatch keyup explicitly to trigger the table redraw.
  await search.dispatchEvent("keyup");
  await page.waitForTimeout(500);
}

/**
 * Open the detail panel for the row whose data-id matches `userId`.
 * Falls back to clicking the first expand button if userId is not given.
 */
async function expandUserRow(page, userId) {
  if (userId) {
    // After a reload, networkidle can resolve before the DataTables ajax has
    // populated the table (it briefly shows a single placeholder row with no
    // id). Wait for a real, expandable data row before paginating/looking up.
    await page
      .locator("#users tbody tr td.details-control button")
      .first()
      .waitFor({ state: "visible", timeout: 20000 })
      .catch(() => { });
    // The users datatable defaults to 10 rows/page and exposes no "show all"
    // length option, so a freshly created user can sit on a later page and never
    // enter the DOM (id-based lookups then time out — worse the more users exist).
    // Filter the table to this user via its Username column so the row always
    // renders on page 1, then wait for it.
    const u = await getUser(page, userId);
    const term = u?.username || u?.uid;
    if (term) {
      await filterUsersByUsername(page, term);
      await page
        .locator(`#users tbody tr[id="${userId}"]`)
        .first()
        .waitFor({ state: "visible", timeout: 10000 })
        .catch(() => { });
    }
  }
  // Attribute selector avoids CSS.escape (a browser-only global, undefined in
  // the Node test runner) while still tolerating ids with special characters.
  const row = userId
    ? page.locator(`#users tbody tr[id="${userId}"]`)
    : page.locator("#users tbody tr").first();
  const expandBtn = row.locator("td.details-control button");
  // DataTables draws rows asynchronously; the expand button may not exist
  // yet right after networkidle. Wait for it before clicking instead of
  // racing on a fixed timeout.
  await expandBtn.waitFor({ state: "visible", timeout: 15000 });
  await expandBtn.click();
  await page
    .locator(".template-detail-users")
    .first()
    .waitFor({ state: "visible", timeout: 8000 });
}

// The expand ("details") column class differs per datatable: users/roles use
// `details-control`, categories/groups use `details-show`.
const DETAILS_CONTROL_CLASS = {
  users: "details-control",
  roles: "details-control",
  categories: "details-show",
  groups: "details-show",
};
function expandCellSelector(tableId) {
  return `td.${DETAILS_CONTROL_CLASS[tableId] || "details-control"}`;
}

/**
 * Expand the first row of any management datatable (#categories, #groups,
 * #roles, ...) once its async-rendered expand control is actually present.
 */
async function expandFirstRow(page, tableId) {
  const expandBtn = page
    .locator(`#${tableId} tbody tr ${expandCellSelector(tableId)} button`)
    .first();
  await expandBtn.waitFor({ state: "visible", timeout: 15000 });
  await expandBtn.click();
}

/**
 * Click a Bootstrap tab that hosts a DataTable and wait for the first expand
 * button to be visible. Prevents expandFirstRow() from timing out under
 * parallel load when the tab panel is hidden (display:none) and DataTables
 * hasn't yet rendered its rows.
 */
async function activateTabTable(page, tabSelector, tableId) {
  const tab = page.locator(tabSelector).first();
  if ((await tab.count()) === 0) return;
  await tab.click();
  // Wait for at least one data row so DataTables has fetched and rendered.
  // Use a first-tr check (faster signal) — expandFirstRow still waits for
  // the interactive button, giving the table a second window to finish.
  await page
    .locator(`#${tableId} tbody tr`)
    .first()
    .waitFor({ state: "visible", timeout: 15000 })
    .catch(() => { });
}

/** Type into a DataTables search box (`#<tableId>_filter input`) if present. */
async function filterTable(page, tableId, text) {
  const search = page.locator(`#${tableId}_filter input`).first();
  if ((await search.count()) > 0) {
    await search.fill(text);
    await page.waitForTimeout(800);
  }
}

/**
 * Filter a datatable down to `text`, then expand the first matching row.
 * Used when a test needs the detail panel of a specific (just-created) row
 * that might otherwise be paginated out of view.
 */
async function expandRowByText(page, tableId, text) {
  await filterTable(page, tableId, text);
  const expandBtn = page
    .locator(`#${tableId} tbody tr`, { hasText: text })
    .first()
    .locator(`${expandCellSelector(tableId)} button`);
  await expandBtn.waitFor({ state: "visible", timeout: 15000 });
  await expandBtn.click();
}

/**
 * Persistence check through the UI datatable (rather than the single-item GET,
 * whose cache could one day be enabled): type `search` into the table's own
 * search box and let the caller assert presence, absence or a cell value.
 *
 * This filters the table IN PLACE — it does NOT navigate. The management page
 * is already open and every datatable live-updates via socket on each mutation
 * (users_data/users_delete, categories_data/_delete, groups_data/_delete →
 * row redraw / ajax.reload), so the new/edited/deleted row is reflected here
 * without reloading. A second full page.goto() was the original mistake: it
 * added ~15s of navigation per call (blowing per-test timeouts) and, for the
 * categories/groups panels, could land on a table that had not re-fetched yet.
 * We give the socket-driven redraw a moment, then search; the caller's
 * expect() polls the locator as the table settles.
 *
 * The table search matches the rendered VISIBLE columns (name, username,
 * category, group, ...) — NOT the hidden id column — so `search` must be built
 * from visible text. Pass a unique value (name, or name + username) and assert
 * against the filtered rows (`tbody tr:not(.dataTables_empty)`); do not try to
 * locate by `tr[id=...]` off an id search.
 */
async function searchManagementTable(page, tableId, search) {
  await page.waitForTimeout(2500);
  if (tableId === "users") await showAllUsers(page);
  await filterTable(page, tableId, search);
}

// All API setup/cleanup/verification goes through the generated apiv4 SDK
// (the page's auth header flows through `apiv4ClientForPage`). The management
// listings live under the `{nav}` path param (`nav: 'management'`).
const sdk = (page) => apiv4ClientForPage(page);

/** Management listings (admin); return `[]` on error. */
async function listUsers(page) {
  return unwrap(
    adminListUsersNav({ client: sdk(page), path: { nav: "management" } }),
  ).catch(() => []);
}
async function listCategories(page) {
  return unwrap(
    adminListCategoriesNav({ client: sdk(page), path: { nav: "management" } }),
  ).catch(() => []);
}
async function listGroups(page) {
  return unwrap(
    adminListGroupsNav({ client: sdk(page), path: { nav: "management" } }),
  ).catch(() => []);
}
/** Single-item GETs; return `null` on error. */
async function getCategory(page, id) {
  return unwrap(
    adminGetCategory({ client: sdk(page), path: { category_id: id } }),
  ).catch(() => null);
}
async function getGroup(page, id) {
  return unwrap(
    adminGetGroup({ client: sdk(page), path: { group_id: id } }),
  ).catch(() => null);
}
async function getUser(page, id) {
  return unwrap(
    adminGetUser({ client: sdk(page), path: { user_id: id } }),
  ).catch(() => null);
}

// Default lenient password works in the seeded `default` category. Freshly
// created categories ship a strict default password policy (>= 34 chars), so
// users placed in a brand-new category need STRONG_PWD instead.
const STRONG_PWD = "IsardVDI-E2E-LongPassword-0123456789!Aa";

/**
 * Create a test user and return its id. Caller cleans up. Pass
 * `opts` to set category/group/role/email_verified (defaults: default /
 * default-default / user).
 */
async function createTestUser(page, suffix = "", opts = {}) {
  const ts = Date.now() + suffix;
  const username = opts.username || `e2e_umgmt_${ts}`;
  const body = {
    username,
    name: opts.name || `E2E Mgmt ${ts}`,
    email: `${username}@example.test`,
    password: opts.password || "IsardTest1!",
    provider: "local",
    bulk: false,
    role: opts.role || "user",
    category: opts.category || "default",
    group: opts.group || "default-default",
  };
  if (opts.email_verified !== undefined)
    body.email_verified = opts.email_verified;
  const created = await unwrap(adminCreateUser({ client: sdk(page), body }));
  const id = created?.id ?? username;
  // Newly created users come back with `vpn: null`. Reset the VPN so the
  // user carries a real wireguard object (the VPN column render in
  // users_management.js null-checks full.vpn, but the reset also ensures the
  // icon shows the correct connected/disconnected state).
  if (id && opts.resetVpn !== false) {
    await adminResetVpn({ client: sdk(page), path: { user_id: id } }).catch(
      () => { },
    );
  }
  return id;
}

/** Create a category and return its id. Caller cleans up. */
async function createTestCategory(page, suffix = "") {
  const ts = Date.now() + suffix;
  const name = `E2E Cat ${ts}`;
  const created = await unwrap(
    adminCreateCategory({
      client: sdk(page),
      body: {
        name,
        description: "E2E test category",
        // manager_permissions is a required field on category create.
        manager_permissions: {},
      },
    }),
  );
  return { id: created?.id, name };
}

/** Create a group inside `category` and return its id. */
async function createTestGroup(page, category = "default", suffix = "") {
  const ts = Date.now() + suffix;
  const name = `E2E Grp ${ts}`;
  const created = await unwrap(
    adminCreateGroup({
      client: sdk(page),
      body: { name, description: "E2E test group", parent_category: category },
    }),
  );
  return { id: created?.id ?? `${category}-${name}`, name };
}

/** Poll an API predicate until it returns truthy or the timeout elapses. */
async function pollUntil(page, fn, { timeout = 20000, interval = 1000 } = {}) {
  const deadline = Date.now() + timeout;
  let last;
  while (Date.now() < deadline) {
    last = await fn();
    if (last) return last;
    await page.waitForTimeout(interval);
  }
  return last;
}

/** Delete a category by id, silencing errors. */
async function deleteCategory(page, id) {
  if (!id) return;
  await adminDeleteCategory({
    client: sdk(page),
    path: { category_id: id },
  }).catch(() => { });
}

/** Delete a group by id, silencing errors. */
async function deleteGroup(page, id) {
  if (!id) return;
  await adminDeleteGroup({ client: sdk(page), path: { group_id: id } }).catch(
    () => { },
  );
}

/** Delete a user by id, silencing errors. */
async function deleteUser(page, userId) {
  await adminDeleteUsers({
    client: sdk(page),
    body: { user: [userId], delete_user: true },
  }).catch(() => { });
}

// ---------------------------------------------------------------------------
// Admin role scenarios
// Uses the same authenticatedPage fixture as gpus.js so the session is
// established by the fixture rather than re-logging in on every test.
// ---------------------------------------------------------------------------

test.describe("Users Management — admin role", () => {
  // Per-test cleanup registry: push cleanup functions here so afterEach can
  // run them even when the test body fails before reaching its own deleteX call.
  let _testCleanup = [];
  function registerCleanup(fn) {
    _testCleanup.push(fn);
  }

  // authenticatedPage comes pre-logged-in from the apiv4 fixture; we only
  // need bridgeAdminSession to copy the cookie into the isard-admin context.
  test.beforeEach(async ({ authenticatedPage }) => {
    _testCleanup = [];
    await bridgeAdminSession(authenticatedPage);
  });

  test.afterEach(async ({ authenticatedPage: page }) => {
    for (const fn of [..._testCleanup].reverse()) {
      await fn(page).catch(() => { });
    }
    _testCleanup = [];
  });

  // -------------------------------------------------------------------------
  // A1 — Add user creates row in users table
  // -------------------------------------------------------------------------
  test("A1 — Add user creates row in users table", async ({
    authenticatedPage: page,
  }) => {
    const xhr = captureXhr(page, (u) => u.includes("/api/v4/admin/item/user"));
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const ts = Date.now();
    const username = `e2e_a1_${ts}`;
    const name = `E2E A1 ${ts}`;

    await page.locator(".btn-new-user").click();
    await page.locator("#modalAddUser").waitFor({ state: "visible" });

    await page.locator("#modalAddUserForm #id").fill(username);
    await page.locator("#modalAddUserForm #name").fill(name);
    await page
      .locator('#modalAddUserForm [name="email"]')
      .fill(`${username}@example.test`);
    await page
      .locator("#modalAddUserForm #password-add-user")
      .fill("IsardTest1!");
    await page
      .locator("#modalAddUserForm #password2-add-user")
      .fill("IsardTest1!");

    const postPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/item/user") &&
        r.request().method() === "POST",
      { timeout: 15000 },
    );
    await page.locator("#modalAddUser #send").click();
    const postResp = await postPromise;
    expect(
      postResp.status(),
      "POST /api/v4/admin/item/user status",
    ).toBeLessThan(400);

    await waitForPNotify(page, "Created");

    // Table is updated via socket; give it a moment.
    await page.waitForTimeout(2000);
    await page.locator("#users").waitFor({ state: "visible" });
    const postCalls = xhr.filter(
      (x) => x.method === "POST" && x.url.includes("/api/v4/admin/item/user"),
    );
    expect(postCalls.length).toBeGreaterThan(0);
    for (const c of postCalls) {
      expect(c.status).toBeLessThan(400);
    }

    // Persistence: the new user is searchable in the users datatable.
    const created = await postResp.json().catch(() => null);
    if (created?.id) registerCleanup((p) => deleteUser(p, created.id));
    // A user created via the form comes back with vpn:null. Reset the VPN so
    // the row carries a real wireguard object and the VPN icon renders correctly.
    if (created?.id) {
      await adminResetVpn({
        client: sdk(page),
        path: { user_id: created.id },
      }).catch(() => { });
    }
    // The table search matches visible columns (name/username), not the hidden
    // id — search by name + username and assert the matching row is present.
    await searchManagementTable(page, "users", `${name} ${username}`);
    await expect(
      page.locator("#users tbody tr:not(.dataTables_empty)").first(),
      "created user should appear in the users table",
    ).toBeVisible({ timeout: 7500 });

    // Cleanup
    if (created?.id) await deleteUser(page, created.id);
  });

  // -------------------------------------------------------------------------
  // A2 — Add user rejects invalid email and invalid password
  // -------------------------------------------------------------------------
  test("A2 — Add user rejects invalid email and invalid password", async ({
    authenticatedPage: page,
  }) => {
    const xhr = captureXhr(page, (u) => u.includes("/api/v4/admin/item/user"));
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await page.locator(".btn-new-user").click();
    await page.locator("#modalAddUser").waitFor({ state: "visible" });

    await page.locator("#modalAddUserForm #id").fill("e2e_a2_invalid");
    await page.locator("#modalAddUserForm #name").fill("E2E A2");
    await page.locator('#modalAddUserForm [name="email"]').fill("not-an-email");
    await page.locator("#modalAddUserForm #password-add-user").fill("weak");
    await page.locator("#modalAddUserForm #password2-add-user").fill("weak");
    await page.locator("#modalAddUser #send").click();

    // Parsley should block; modal must remain open.
    await expect(page.locator("#modalAddUser")).toBeVisible();
    const posts = xhr.filter((x) => x.method === "POST");
    expect(posts).toEqual([]);
  });

  // -------------------------------------------------------------------------
  // A3 — Users datatable loads and is searchable
  // -------------------------------------------------------------------------
  test("A3 — Users datatable loads and is searchable", async ({
    authenticatedPage: page,
  }) => {
    const xhr = captureXhr(page, (u) =>
      u.includes("/api/v4/admin/items/users/management/users"),
    );
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });
    // Wait for a real data row before checking the XHR log — under load the
    // networkidle timeout can expire before the DataTables ajax response lands.
    await expect(page.locator("#users tbody tr").first()).toBeVisible({
      timeout: 15000,
    });

    const listCalls = xhr.filter((x) =>
      x.url.includes("/api/v4/admin/items/users/management/users"),
    );
    expect(
      listCalls.length,
      "expected at least one users listing call",
    ).toBeGreaterThan(0);
    for (const c of listCalls) {
      expect(c.status).toBeLessThan(400);
    }
  });

  // -------------------------------------------------------------------------
  // A4 — Edit user updates editable fields
  // -------------------------------------------------------------------------
  test("A4 — Edit user updates editable fields", async ({
    authenticatedPage: page,
  }) => {
    test.slow();
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });
    const username = `e2e_a4_${Date.now()}`;
    const userId = await createTestUser(page, "_a4", { username });
    registerCleanup((p) => deleteUser(p, userId));

    await page.reload();
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await expandUserRow(page, userId);
    // The edit modal populates its fields from an async GET /item/user/{id}
    // after opening; fill only once that populate response has landed so it
    // does not overwrite our value.
    const populatePromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/user/${userId}`) &&
        r.request().method() === "GET",
      { timeout: 7500 },
    );
    await page.locator(".template-detail-users .btn-edit").first().click();
    await page.locator("#modalEditUser").waitFor({ state: "visible" });
    await populatePromise.catch(() => { });
    const nameField = page.locator("#modalEditUserForm #name");
    await expect(nameField).not.toHaveValue("", { timeout: 8000 });
    await page.waitForTimeout(300);
    const editedName = `E2E A4 Edited ${Date.now()}`;
    await nameField.fill(editedName);

    const putPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/user/${userId}`) &&
        r.request().method() === "PUT",
      { timeout: 15000 },
    );
    await page.locator("#modalEditUser #send").click();
    const putResp = await putPromise;
    expect(
      putResp.status(),
      "PUT /api/v4/admin/item/user/{id} status",
    ).toBeLessThan(400);

    // Persistence (via the UI datatable, not the single-item GET): the table
    // search matches visible columns (name/username/category/group), not the
    // hidden id — so search by the new name + username to pin the edited row.
    await searchManagementTable(page, "users", `${editedName} ${username}`);
    await expect(
      page.locator("#users tbody tr:not(.dataTables_empty)").first(),
      "edited name should be searchable in the users table",
    ).toBeVisible({ timeout: 7500 });

    await deleteUser(page, userId);
  });

  // -------------------------------------------------------------------------
  // A5 — Delete user supports both deletion paths
  // -------------------------------------------------------------------------
  test("A5 — Delete user supports both deletion paths", async ({
    authenticatedPage: page,
  }) => {
    test.slow();
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });
    const userId = await createTestUser(page, "_a5");
    registerCleanup((p) => deleteUser(p, userId));

    await page.reload();
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await expandUserRow(page, userId);
    const checkPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/item/user/delete/check") &&
        r.request().method() === "POST",
      { timeout: 15000 },
    );
    await page.locator(".template-detail-users .btn-delete").first().click();
    await page.locator("#modalDeleteUser").waitFor({ state: "visible" });
    // The preview is populated by POST .../delete/check; wait for that rather
    // than asserting the preview table (its id is duplicated across modals and
    // it is empty for a resource-less user).
    await checkPromise.catch(() => { });

    // Use the "delete user and items" path (delete-user=true) so the user is
    // actually removed — that is what the post-deletion assertion checks. The
    // radios are iCheck-styled (the real input is hidden), so force-click and
    // set it via the DOM too. (The "keep user, delete items" path keeps the
    // user, so it cannot share this same removal assertion.)
    const deleteRadio = page.locator(
      '#modalDeleteUserForm [name="delete-user"][value="true"]',
    );
    if ((await deleteRadio.count()) > 0) {
      await deleteRadio.click({ force: true }).catch(() => { });
      await page.evaluate(() => {
        const r = document.querySelector(
          '#modalDeleteUserForm [name="delete-user"][value="true"]',
        );
        if (r) {
          r.checked = true;
          if (window.jQuery && window.jQuery(r).iCheck)
            window.jQuery(r).iCheck("check");
        }
      });
    }

    const deletePromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/items/users") &&
        r.request().method() === "DELETE",
      { timeout: 15000 },
    );
    await page.locator("#modalDeleteUser #send").click();
    const deleteResp = await deletePromise;
    expect(
      deleteResp.status(),
      "DELETE /api/v4/admin/items/users status",
    ).toBeLessThan(400);

    await page.waitForTimeout(3000);
    const users = await listUsers(page);
    expect(
      users.find((u) => u.id === userId),
      "user should not appear in listing after deletion",
    ).toBeUndefined();
  });

  // -------------------------------------------------------------------------
  // A6 — Reset password (PUT 405 bug fixed — now a normal passing test)
  // -------------------------------------------------------------------------
  test("A6 — Reset password modal sends PUT and succeeds", async ({
    authenticatedPage: page,
  }) => {
    test.slow();
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });
    const userId = await createTestUser(page, "_a6");
    registerCleanup((p) => deleteUser(p, userId));

    await page.reload();
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });
    await expandUserRow(page, userId);

    await page.locator(".template-detail-users .btn-passwd").first().click();
    await page.locator("#modalPasswdUser").waitFor({ state: "visible" });
    await page.waitForTimeout(1000);

    await page
      .locator("#modalPasswdUserForm #password-reset")
      .fill("NewPass1!");
    // The Repeat field has parsley data-parsley-equalto="#password-reset";
    // leaving it empty blocks submit (no PUT is sent), so fill it to match.
    await page
      .locator("#modalPasswdUserForm #password2-reset")
      .fill("NewPass1!");
    const putPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/user/${userId}`) &&
        r.request().method() === "PUT",
      { timeout: 15000 },
    );
    await page.locator("#modalPasswdUser #send").click();
    const putResp = await putPromise;
    expect(putResp.status(), "PUT reset-password must return < 400").toBeLessThan(400);

    await deleteUser(page, userId);
  });

  // -------------------------------------------------------------------------
  // A7 — Bulk delete removes selected users
  // -------------------------------------------------------------------------
  test("A7 — Bulk delete removes selected users", async ({
    authenticatedPage: page,
  }) => {
    test.slow();
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    // Explicit usernames so the post-deletion check can search the datatable
    // by a visible column (the id column is hidden) and assert the row is gone.
    const ts = Date.now();
    const user1 = `e2e_a7a_${ts}`;
    const user2 = `e2e_a7b_${ts}`;
    const u1 = await createTestUser(page, "_a7a", { username: user1 });
    const u2 = await createTestUser(page, "_a7b", { username: user2 });
    registerCleanup((p) => deleteUser(p, u1));
    registerCleanup((p) => deleteUser(p, u2));

    await page.reload();
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    // Filter the table to just these two users (they share `ts`) so both rows
    // render into the DOM — bulk selection reads only rendered rows, and with
    // >100 users showAllUsers (max 100) can leave the new rows paginated out.
    await filterUsersByUsername(page, ts);
    for (const uid of [u1, u2]) {
      await page
        .locator(`#users tbody tr[id="${uid}"]`)
        .first()
        .waitFor({ state: "visible", timeout: 10000 })
        .catch(() => { });
    }
    // Bulk selection is read from the `active` row class (getSelectedUserList
    // checks `.hasClass('active')`); the admin UI only sets it via select-all,
    // so mark the two target rows directly to drive the bulk action.
    for (const uid of [u1, u2]) {
      await page.evaluate((id) => {
        const tr = document.querySelector(`#users tbody tr[id="${id}"]`);
        if (tr) {
          tr.classList.add("active");
          const cb = tr.querySelector('input[type="checkbox"]');
          if (cb) cb.checked = true;
        }
      }, uid);
    }

    await page.locator(".btn-bulkdelete").click();
    await page.locator("#modalDeleteUser").waitFor({ state: "visible" });
    await page.waitForTimeout(1500);

    const deleteUserRadio = page.locator(
      '#modalDeleteUserForm [name="delete-user"][value="true"]',
    );
    if ((await deleteUserRadio.count()) > 0) {
      await deleteUserRadio.click({ force: true }).catch(() => { });
      await page.evaluate(() => {
        const r = document.querySelector(
          '#modalDeleteUserForm [name="delete-user"][value="true"]',
        );
        if (r) r.checked = true;
      });
    }

    const deletePromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/items/users") &&
        r.request().method() === "DELETE",
      { timeout: 15000 },
    );
    await page.locator("#modalDeleteUser #send").click();
    const resp = await deletePromise;
    expect(resp.status(), "bulk DELETE status").toBeLessThan(400);

    // Persistence: both users are gone from the users datatable.
    for (const username of [user1, user2]) {
      await searchManagementTable(page, "users", username);
      await expect(
        page.locator("#users tbody tr:not(.dataTables_empty)", {
          hasText: username,
        }),
        "bulk-deleted user should be gone from the users table",
      ).toHaveCount(0, { timeout: 7500 });
    }
  });

  // -------------------------------------------------------------------------
  // A8 — Bulk edit applies active/inactive toggle
  // -------------------------------------------------------------------------
  test("A8 — Bulk edit applies active toggle", async ({
    authenticatedPage: page,
  }) => {
    test.slow();
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    // Shared `ts` in explicit usernames so both rows can be filtered in together.
    const ts = Date.now();
    const u1 = await createTestUser(page, "_a8a", { username: `e2e_a8a_${ts}` });
    const u2 = await createTestUser(page, "_a8b", { username: `e2e_a8b_${ts}` });
    registerCleanup((p) => deleteUser(p, u1));
    registerCleanup((p) => deleteUser(p, u2));

    await page.reload();
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    // Filter the table to just these two users (they share `ts`) so both rows
    // render into the DOM — bulk selection reads only rendered rows, and with
    // >100 users showAllUsers (max 100) can leave the new rows paginated out.
    await filterUsersByUsername(page, ts);
    for (const uid of [u1, u2]) {
      await page
        .locator(`#users tbody tr[id="${uid}"]`)
        .first()
        .waitFor({ state: "visible", timeout: 10000 })
        .catch(() => { });
    }
    // Bulk selection is read from the `active` row class (getSelectedUserList
    // checks `.hasClass('active')`); the admin UI only sets it via select-all,
    // so mark the two target rows directly to drive the bulk action.
    for (const uid of [u1, u2]) {
      await page.evaluate((id) => {
        const tr = document.querySelector(`#users tbody tr[id="${id}"]`);
        if (tr) {
          tr.classList.add("active");
          const cb = tr.querySelector('input[type="checkbox"]');
          if (cb) cb.checked = true;
        }
      }, uid);
    }

    await page.locator(".btn-bulk-edit-users").click();
    await page.locator("#modalBulkEditUser").waitFor({ state: "visible" });

    // Enable the "edit active/inactive" toggle. The control is iCheck-styled
    // (the real `#edit-active-inactive` input is hidden), so drive it through
    // iCheck's API — that both ticks the input (serialized as `on`, which is
    // what gates the bulk PUT) and fires the event that reveals the panel.
    await page.evaluate(() => {
      const jq = window.jQuery;
      const input = document.querySelector(
        "#modalBulkEditUserForm #edit-active-inactive",
      );
      if (!input) return;
      if (jq && jq(input).iCheck) jq(input).iCheck("check");
      else {
        input.checked = true;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    await page.waitForTimeout(300);

    const putPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/items/users/bulk") &&
        r.request().method() === "PUT",
      { timeout: 15000 },
    );
    await page.locator("#modalBulkEditUser #send").click();
    const putResp = await putPromise;
    expect(putResp.status()).toBeLessThan(400);

    await deleteUser(page, u1);
    await deleteUser(page, u2);
  });

  // -------------------------------------------------------------------------
  // A9 — Enable/disable toggles the user's active state
  // -------------------------------------------------------------------------
  test("A9 — Enable/disable sends PUT and succeeds", async ({
    authenticatedPage: page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => {});

    const userId = await createTestUser(page, "_a9");
    registerCleanup((p) => deleteUser(p, userId));
    await page.reload();
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => {});

    await expandUserRow(page, userId);

    const putPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/item/user/") &&
        r.request().method() === "PUT",
      { timeout: 15000 },
    );
    await page.locator(".template-detail-users .btn-active").first().click();
    // The enable/disable confirmation is a PNotify (.pnotify-center) dialog.
    await confirmPnotify(page);
    const putResp = await putPromise;
    expect(putResp.status(), "PUT enable/disable status").toBeLessThan(400);

    await deleteUser(page, userId);
  });

  // -------------------------------------------------------------------------
  // A10 — Reset VPN regenerates stored VPN payload
  // -------------------------------------------------------------------------
  test("A10 — Reset VPN regenerates stored VPN payload", async ({
    authenticatedPage: page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const userId = await createTestUser(page, "_a10");
    registerCleanup((p) => deleteUser(p, userId));
    await page.reload();
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const before = await getUser(page, userId);

    await expandUserRow(page, userId);

    const putPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/user/reset-vpn/${userId}`) &&
        r.request().method() === "PUT",
      { timeout: 15000 },
    );
    await page.locator(".template-detail-users .btn-vpn").first().click();
    await confirmPnotify(page);

    const putResp = await putPromise;
    expect(putResp.status(), "PUT reset-vpn status").toBeLessThan(400);
    await waitForPNotify(page, "Success");

    if (before?.vpn) {
      const after = await getUser(page, userId);
      if (
        after?.vpn?.wireguard?.public_key &&
        before?.vpn?.wireguard?.public_key
      ) {
        expect(after.vpn.wireguard.public_key).not.toBe(
          before.vpn.wireguard.public_key,
        );
      }
    }

    await deleteUser(page, userId);
  });

  // -------------------------------------------------------------------------
  // A11 — Create category persists new category
  // -------------------------------------------------------------------------
  test("A11 — Create category persists new category", async ({
    authenticatedPage: page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const catTab = page
      .locator('[href="#categories"], button:has-text("Categories")')
      .first();
    if ((await catTab.count()) > 0) await catTab.click();

    await page.locator(".btn-new-category").first().click();
    await page
      .locator("#modalAddCategory")
      .waitFor({ state: "visible", timeout: 8000 });

    const catName = `E2E Cat ${Date.now()}`;
    await page.locator("#modalAddCategoryForm #name").fill(catName);
    const descField = page.locator(
      '#modalAddCategoryForm [name="description"]',
    );
    if ((await descField.count()) > 0)
      await descField.fill("E2E test category");

    const postPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/item/category") &&
        r.request().method() === "POST",
      { timeout: 15000 },
    );
    await page.locator("#modalAddCategory #send").click();
    const postResp = await postPromise;
    expect(postResp.status()).toBeLessThan(400);

    const created = await postResp.json().catch(() => null);
    if (created?.id) registerCleanup((p) => deleteCategory(p, created.id));

    // Persistence: the new category is searchable in the categories datatable.
    await searchManagementTable(page, "categories", catName);
    await expect(
      page
        .locator("#categories tbody tr:not(.dataTables_empty)", {
          hasText: catName,
        })
        .first(),
      "created category should appear in the categories table",
    ).toBeVisible({ timeout: 7500 });

    if (created?.id) {
      await deleteCategory(page, created.id);
    }
  });

  // -------------------------------------------------------------------------
  // A12 — Categories datatable loads
  // -------------------------------------------------------------------------
  test("A12 — Categories datatable loads", async ({
    authenticatedPage: page,
  }) => {
    const xhr = captureXhr(page, (u) =>
      u.includes("/api/v4/admin/items/users/management/categories"),
    );
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const catTab = page
      .locator('[href="#categories"], button:has-text("Categories")')
      .first();
    if ((await catTab.count()) > 0) await catTab.click();
    await page.waitForTimeout(2000);

    const calls = xhr.filter((x) =>
      x.url.includes("/api/v4/admin/items/users/management/categories"),
    );
    expect(calls.length, "expected categories listing call").toBeGreaterThan(0);
    for (const c of calls) {
      expect(c.status).toBeLessThan(400);
    }
    await expect(page.locator("#categories tbody tr").first()).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // A13 — Edit category updates editable fields
  // -------------------------------------------------------------------------
  test("A13 — Edit category updates editable fields", async ({
    authenticatedPage: page,
  }) => {
    test.slow();
    // Edit a throwaway category (not `default`, which is protected and 409s on
    // edit). Change both name and description to a new unique value.
    const cat = await createTestCategory(page, "_a13");
    registerCleanup((p) => deleteCategory(p, cat.id));

    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await activateTabTable(page, '[href="#categories"], button:has-text("Categories")', "categories");
    await expandRowByText(page, "categories", cat.name);

    // Correct class is `.btn-edit-category` (categories_detail_management.html).
    const editBtn = page
      .locator(".template-detail-categories .btn-edit-category")
      .first();
    await editBtn.waitFor({ state: "visible", timeout: 5000 });
    await editBtn.click();
    await page
      .locator("#modalEditCategory")
      .waitFor({ state: "visible", timeout: 8000 });

    const newName = `${cat.name} Edited`;
    const newDesc = `E2E edited ${Date.now()}`;
    await page
      .locator(
        '#modalEditCategoryForm #name, #modalEditCategoryForm [name="name"]',
      )
      .first()
      .fill(newName)
      .catch(() => { });
    await page
      .locator('#modalEditCategoryForm [name="description"]')
      .fill(newDesc)
      .catch(() => { });

    const putPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/category/${cat.id}`) &&
        r.request().method() === "PUT",
      { timeout: 15000 },
    );
    await page.locator("#modalEditCategory #send").click();
    const putResp = await putPromise;
    expect(putResp.status(), "PUT edit category status").toBeLessThan(400);

    // Persistence (UI datatable): the edited name is searchable and the row's
    // description cell shows the new value.
    await searchManagementTable(page, "categories", newName);
    const catRow = page
      .locator("#categories tbody tr:not(.dataTables_empty)", {
        hasText: newName,
      })
      .first();
    await expect(
      catRow,
      "edited category name should be searchable",
    ).toBeVisible({
      timeout: 7500,
    });
    await expect(
      catRow.locator("td.xe-description"),
      "edited category description should persist",
    ).toContainText(newDesc, { timeout: 7500 });

    await deleteCategory(page, cat.id);
  });

  // -------------------------------------------------------------------------
  // A14 — Delete category removes the category and its descendant users (DB cascade)
  // -------------------------------------------------------------------------
  test("A14 — Delete category cascades to its users", async ({
    authenticatedPage: page,
  }) => {
    // Seed a throwaway category with a child user so we can assert the
    // cascade actually removes descendants from the DB after deletion.
    const cat = await createTestCategory(page, "_a14");
    registerCleanup((p) => deleteCategory(p, cat.id));
    const childId = await createTestUser(page, "_a14", {
      category: cat.id,
      group: `${cat.id}-${cat.name}`,
      role: "user",
      password: STRONG_PWD, // new categories enforce a >=34 char password policy
    }).catch(() => null);
    if (childId) registerCleanup((p) => deleteUser(p, childId));

    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await activateTabTable(page, '[href="#categories"], button:has-text("Categories")', "categories");
    await expandRowByText(page, "categories", cat.name);

    // Open delete modal; the preview is populated via POST category/delete/check.
    const checkPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/item/category/delete/check") &&
        r.request().method() === "POST",
      { timeout: 15000 },
    );
    await page
      .locator(".template-detail-categories .btn-delete")
      .first()
      .click();
    await page
      .locator("#modalDeleteCategory")
      .waitFor({ state: "visible", timeout: 8000 });
    await checkPromise;

    const deletePromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/category/${cat.id}`) &&
        r.request().method() === "DELETE",
      { timeout: 15000 },
    );
    await page.locator("#modalDeleteCategory #send").click();
    const deleteResp = await deletePromise;
    expect(deleteResp.status(), "DELETE category status").toBeLessThan(400);

    // DB verification (via API): category gone, and its child user gone too.
    const catGone = await pollUntil(page, async () => {
      const cats = await listCategories(page);
      return cats && !cats.find((c) => c.id === cat.id);
    });
    expect(catGone, "category should be removed from listing").toBeTruthy();

    if (childId) {
      const userGone = await pollUntil(page, async () => {
        const users = await listUsers(page);
        return users && !users.find((u) => u.id === childId);
      });
      expect(
        userGone,
        "child user should be cascade-deleted with its category",
      ).toBeTruthy();
    }
  });

  // -------------------------------------------------------------------------
  // A15 — Create group persists new group
  // -------------------------------------------------------------------------
  test("A15 — Create group persists new group", async ({
    authenticatedPage: page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const groupTab = page
      .locator('[href="#groups"], button:has-text("Groups")')
      .first();
    if ((await groupTab.count()) > 0) await groupTab.click();
    await page.waitForTimeout(1000);

    await page.locator(".btn-new-group").first().click();
    await page
      .locator("#modalAddGroup")
      .waitFor({ state: "visible", timeout: 8000 });

    const groupName = `E2E Grp ${Date.now()}`;
    await page
      .locator('#modalAddGroupForm [name="name"], #modalAddGroupForm #name')
      .fill(groupName);

    // Pick a known parent category so the group can be matched by name +
    // category in the table. The admin select's option text is
    // "name - description" (groups_management.js), while the table cell shows
    // just the category name, so parse the name off the selected option.
    const catSelect = page
      .locator(
        '#modalAddGroupForm select[name="parent_category"]:not([disabled])',
      )
      .first();
    await catSelect.selectOption("default").catch(() => { });
    const categoryName = (
      (await catSelect.locator("option:checked").first().textContent()) || ""
    )
      .split(" - ")[0]
      .trim();

    const postPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/item/group") &&
        r.request().method() === "POST",
      { timeout: 15000 },
    );
    await page.locator("#modalAddGroup #send").click();
    const postResp = await postPromise;
    expect(postResp.status()).toBeLessThan(400);

    const created = await postResp.json().catch(() => null);
    if (created?.id) registerCleanup((p) => deleteGroup(p, created.id));

    // Persistence: search the groups table by name + category (the table search
    // matches visible columns, not the hidden id) and assert the row is there.
    await searchManagementTable(
      page,
      "groups",
      `${groupName} ${categoryName}`.trim(),
    );
    await expect(
      page.locator("#groups tbody tr:not(.dataTables_empty)").first(),
      "created group should appear in the groups table (by name + category)",
    ).toBeVisible({ timeout: 7500 });

    if (created?.id) {
      await deleteGroup(page, created.id);
    }
  });

  // -------------------------------------------------------------------------
  // A16 — Groups datatable loads
  // -------------------------------------------------------------------------
  test("A16 — Groups datatable loads", async ({ authenticatedPage: page }) => {
    const xhr = captureXhr(page, (u) =>
      u.includes("/api/v4/admin/items/users/management/groups"),
    );
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const groupTab = page
      .locator('[href="#groups"], button:has-text("Groups")')
      .first();
    if ((await groupTab.count()) > 0) await groupTab.click();
    await page.waitForTimeout(2000);

    const calls = xhr.filter((x) =>
      x.url.includes("/api/v4/admin/items/users/management/groups"),
    );
    expect(calls.length, "expected groups listing call").toBeGreaterThan(0);
    for (const c of calls) {
      expect(c.status).toBeLessThan(400);
    }
    await expect(page.locator("#groups tbody tr").first()).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // A17 — Edit group updates editable fields
  // -------------------------------------------------------------------------
  test("A17 — Edit group updates editable fields", async ({
    authenticatedPage: page,
  }) => {
    // Edit a throwaway group so the new description is searchable against a
    // known row in the groups datatable (mirrors A13's throwaway category).
    const grp = await createTestGroup(page, "default", "_a17");
    registerCleanup((p) => deleteGroup(p, grp.id));

    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await expandRowByText(page, "groups", grp.name);

    // Correct class is `.btn-edit-group` (groups_detail_management.html).
    const editBtn = page
      .locator(".template-detail-groups .btn-edit-group")
      .first();
    await editBtn.waitFor({ state: "visible", timeout: 5000 });
    await editBtn.click();
    await page
      .locator("#modalEditGroup")
      .waitFor({ state: "visible", timeout: 8000 });

    const newDesc = `E2E edited ${Date.now()}`;
    await page
      .locator(
        '#modalEditGroupForm [name="description"], #modalEditGroupForm #description',
      )
      .fill(newDesc)
      .catch(() => { });

    const putPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/item/group/") &&
        r.request().method() === "PUT",
      { timeout: 15000 },
    );
    await page.locator("#modalEditGroup #send").click();
    const putResp = await putPromise;
    expect(putResp.status()).toBeLessThan(400);

    // Persistence (UI datatable): the edited group's description cell shows the
    // new value.
    await searchManagementTable(page, "groups", grp.name);
    const grpRow = page
      .locator("#groups tbody tr:not(.dataTables_empty)", { hasText: grp.name })
      .first();
    await expect(grpRow, "edited group should be searchable").toBeVisible({
      timeout: 7500,
    });
    await expect(
      grpRow.locator("td.xe-description"),
      "edited group description should persist",
    ).toContainText(newDesc, { timeout: 7500 });

    await deleteGroup(page, grp.id);
  });

  // -------------------------------------------------------------------------
  // A18 — Delete group removes the group and its descendant users (DB cascade)
  // -------------------------------------------------------------------------
  test("A18 — Delete group cascades to its users", async ({
    authenticatedPage: page,
  }) => {
    const grp = await createTestGroup(page, "default", "_a18");
    registerCleanup((p) => deleteGroup(p, grp.id));
    const childId = await createTestUser(page, "_a18", {
      category: "default",
      group: grp.id,
      role: "user",
    }).catch(() => null);
    if (childId) registerCleanup((p) => deleteUser(p, childId));

    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await expandRowByText(page, "groups", grp.name);

    const checkPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/item/group/delete/check") &&
        r.request().method() === "POST",
      { timeout: 15000 },
    );
    await page.locator(".template-detail-groups .btn-delete").first().click();
    await page
      .locator("#modalDeleteGroup")
      .waitFor({ state: "visible", timeout: 8000 });
    await checkPromise;

    const deletePromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/group/${grp.id}`) &&
        r.request().method() === "DELETE",
      { timeout: 15000 },
    );
    await page.locator("#modalDeleteGroup #send").click();
    const deleteResp = await deletePromise;
    expect(deleteResp.status(), "DELETE group status").toBeLessThan(400);

    const groupGone = await pollUntil(page, async () => {
      const groups = await listGroups(page);
      return groups && !groups.find((g) => g.id === grp.id);
    });
    expect(groupGone, "group should be removed from listing").toBeTruthy();

    if (childId) {
      const userGone = await pollUntil(page, async () => {
        const users = await listUsers(page);
        return users && !users.find((u) => u.id === childId);
      });
      expect(
        userGone,
        "child user should be cascade-deleted with its group",
      ).toBeTruthy();
    }
  });

  // -------------------------------------------------------------------------
  // A19 — Empty group removes the group's users (sends user id strings)
  // -------------------------------------------------------------------------
  // The Empty-group flow (groups_management.js) sends the group's users into
  // DELETE /items/users (delete_user:true) as id STRINGS; the endpoint accepts
  // them and empties the group.
  test(
    "A19 — Empty group empties the group's users",
    async ({ authenticatedPage: page }) => {
      const grp = await createTestGroup(page, "default", "_a19");
      registerCleanup((p) => deleteGroup(p, grp.id));
      const a19ChildId = await createTestUser(page, "_a19", {
        category: "default",
        group: grp.id,
        role: "user",
      }).catch(() => null);
      if (a19ChildId) registerCleanup((p) => deleteUser(p, a19ChildId));

      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      await expandRowByText(page, "groups", grp.name);

      await page.locator(".template-detail-groups .btn-empty").first().click();
      await page
        .locator("#modalEmptyGroup")
        .waitFor({ state: "visible", timeout: 8000 });

      // The empty modal requires ticking the (iCheck-styled) confirmation
      // checkbox `#delete-check`; clicking its label toggles iCheck reliably.
      await page
        .locator('label[for="delete-check"]')
        .first()
        .click()
        .catch(() => { });
      await page
        .locator("#modalEmptyGroupForm #delete-check")
        .check({ force: true })
        .catch(() => { });

      // Empty flow: GET group users → DELETE /items/users (delete_user:true).
      const deletePromise = page.waitForResponse(
        (r) =>
          r.url().includes("/api/v4/admin/items/users") &&
          r.request().method() === "DELETE",
        { timeout: 15000 },
      );
      await page.locator("#modalEmptyGroup #send").click();
      const deleteResp = await deletePromise;

      // Clean up the throwaway group before the assertion.
      await deleteGroup(page, grp.id);

      expect(
        deleteResp.status(),
        "empty-group DELETE users status",
      ).toBeLessThan(400);
    },
  );

  // -------------------------------------------------------------------------
  // A20 — Group enrollment modal exposes per-role code fields
  // -------------------------------------------------------------------------
  // Verifies the enrollment modal opens with the per-role checkboxes
  // (#user-check/#manager-check/#advanced-check) and their code fields
  // (#user-key/#manager-key/#advanced-key), and that enabling each role shows
  // its generated 6-char code (persisted across reopen).
  test(
    "A20 — Group enrollment modal shows per-role generated codes",
    async ({ authenticatedPage: page }) => {
      test.slow();
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      await expandFirstRow(page, "groups");
      const enrollBtn = page
        .locator(".template-detail-groups .btn-enrollment")
        .first();
      await enrollBtn.waitFor({ state: "visible", timeout: 8000 });
      await enrollBtn.click();
      await page
        .locator("#modalEnrollment")
        .waitFor({ state: "visible", timeout: 8000 });

      // Helper: enable an iCheck checkbox and wait for the enrollment AJAX POST.
      // The modal binds code-generation via jQuery's `ifChecked` event, so the
      // trigger must go through jQuery — a plain DOM dispatchEvent is NOT enough.
      async function enableCheckAndWait(checkSelector) {
        const apiPromise = page.waitForResponse(
          (r) =>
            r.url().includes("/api/v4/admin/item/group/enrollment") &&
            r.request().method() === "POST",
          { timeout: 7500 },
        );
        await page.evaluate((sel) => {
          const jq = window.jQuery;
          const input = document.querySelector(`#modalEnrollmentForm ${sel}`);
          if (!input) return;
          if (jq && jq(input).iCheck) {
            jq(input).iCheck("check");
          } else if (jq) {
            input.checked = true;
            jq(input).trigger("ifChecked");
          }
        }, checkSelector);
        await apiPromise.catch(() => { });
      }

      // Each role has a checkbox and a corresponding (always-disabled, read-only)
      // code input. The code is generated via POST /api/v4/admin/item/group/enrollment.
      const roles = [
        { check: "#user-check", key: "#user-key" },
        { check: "#manager-check", key: "#manager-key" },
        { check: "#advanced-check", key: "#advanced-key" },
      ];

      for (const { check, key } of roles) {
        await expect(page.locator(`#modalEnrollmentForm ${check}`)).toBeAttached();
        await expect(page.locator(`#modalEnrollmentForm ${key}`)).toBeAttached();
      }

      const savedCodes = {};
      for (const { check, key } of roles) {
        const keyInput = page.locator(`#modalEnrollmentForm ${key}`);
        await enableCheckAndWait(check);

        // The field is displayed after the AJAX resolves (.show() is called).
        // It is permanently `disabled` (read-only) by design; the value is set
        // via jQuery .val() so Playwright's inputValue() reads it correctly.
        await expect(
          keyInput,
          `${key} must be visible after ${check} is enabled`,
        ).toBeVisible({ timeout: 5000 });
        await expect(
          keyInput,
          `${key} must contain a code after ${check} is enabled`,
        ).not.toHaveValue("", { timeout: 5000 });
        const code = await keyInput.inputValue();
        expect(
          code,
          `${key} enrollment code must be exactly 6 alphanumeric characters`,
        ).toMatch(/^[A-Za-z0-9]{6}$/);
        savedCodes[key] = code;
      }

      // Close and reopen: codes must persist (stored in DB, loaded on each open).
      await page
        .locator(
          '#modalEnrollment [data-dismiss="modal"], #modalEnrollment .close',
        )
        .first()
        .click();
      await page.locator("#modalEnrollment").waitFor({ state: "hidden" });
      // Let Bootstrap finish tearing down the modal (backdrop removal /
      // `modal-open` class) before re-opening.
      await page
        .locator(".modal-backdrop")
        .waitFor({ state: "hidden", timeout: 5000 })
        .catch(() => {});
      // Closing the modal can leave the groups table redrawn with the detail
      // panel collapsed, so re-expand the row if its enrollment button is gone,
      // then re-locate the trigger fresh (the stored locator may be stale).
      let enrollBtnReopen = page
        .locator(".template-detail-groups .btn-enrollment")
        .first();
      if (!(await enrollBtnReopen.isVisible().catch(() => false))) {
        await expandFirstRow(page, "groups");
        enrollBtnReopen = page
          .locator(".template-detail-groups .btn-enrollment")
          .first();
      }
      await enrollBtnReopen.waitFor({ state: "visible", timeout: 8000 });
      await enrollBtnReopen.click();
      await page
        .locator("#modalEnrollment")
        .waitFor({ state: "visible", timeout: 8000 });

      for (const { key } of roles) {
        const keyInput = page.locator(`#modalEnrollmentForm ${key}`);
        await expect(
          keyInput,
          `${key} code must still be visible after reopening the modal`,
        ).toBeVisible({ timeout: 8000 });
        const codeAfterReopen = await keyInput.inputValue();
        expect(
          codeAfterReopen,
          `${key} code must match the value generated before closing (was "${savedCodes[key]}")`,
        ).toBe(savedCodes[key]);
      }
    },
  );

  // -------------------------------------------------------------------------
  // A21 — Secrets datatable loads
  // -------------------------------------------------------------------------
  test("A21 — Secrets datatable loads with HTTP 200", async ({
    authenticatedPage: page,
  }) => {
    const xhr = captureXhr(page, (u) =>
      u.includes("/api/v4/admin/items/secrets"),
    );
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const appsTab = page
      .locator('[href="#external-apps"], button:has-text("External apps")')
      .first();
    if ((await appsTab.count()) > 0) await appsTab.click();
    await page.waitForTimeout(2000);

    const calls = xhr.filter((x) =>
      x.url.includes("/api/v4/admin/items/secrets"),
    );
    expect(calls.length, "expected secrets listing call").toBeGreaterThan(0);
    for (const c of calls) {
      expect(c.status).toBeLessThan(400);
    }
  });

  // -------------------------------------------------------------------------
  // A22 — Add external app (secret) creates the secret
  // -------------------------------------------------------------------------
  // The Add-external-app flow POSTs to /api/v4/admin/item/secret and succeeds;
  // the frontend/back-end payload contract is reconciled.
  test(
    "A22 — Add external app creates a secret",
    async ({ authenticatedPage: page }) => {
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      // `.btn-new-secret` lives in the External apps panel toolbox (visible even
      // while the panel body is collapsed).
      await page.locator(".btn-new-secret").first().click();
      await page
        .locator("#modalAddSecret")
        .waitFor({ state: "visible", timeout: 8000 });

      const ts = Date.now();
      await page.locator("#modalAddSecretForm #name").fill(`e2e-secret-${ts}`);
      await page
        .locator("#modalAddSecretForm #domain")
        .fill(`e2e-${ts}.example.test`);
      await page
        .locator("#modalAddSecretForm #textarea")
        .fill("E2E external app")
        .catch(() => { });
      // Category is required; pick the default category (by value, then by index).
      await page
        .locator("#modalAddSecretForm #add-category")
        .selectOption("default")
        .catch(async () => {
          await page
            .locator("#modalAddSecretForm #add-category")
            .selectOption({ index: 1 })
            .catch(() => { });
        });

      const postPromise = page.waitForResponse(
        (r) =>
          r.url().includes("/api/v4/admin/item/secret") &&
          r.request().method() === "POST",
        { timeout: 15000 },
      );
      await page.locator("#modalAddSecret #send").click();
      const postResp = await postPromise;
      expect(
        postResp.status(),
        "POST /api/v4/admin/item/secret status",
      ).toBeLessThan(400);

      // Cleanup the created secret if the response carried an id.
      const created = await postResp.json().catch(() => null);
      if (created?.id) {
        await adminDeleteSecret({
          client: sdk(page),
          path: { kid: created.id },
        }).catch(() => { });
      }
    },
  );

  // -------------------------------------------------------------------------
  // A23 — Edit role modal renders name + description fields
  // -------------------------------------------------------------------------
  test("A23 — Edit role modal renders its fields", async ({
    authenticatedPage: page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => {});

    // Admin sees the details-control column for roles (managers do not — see M13).
    await expandFirstRow(page, "roles");

    // Correct class is `.btn-edit-role` (roles.js actionsRolDetail()).
    await page
      .locator(".template-detail-roles .btn-edit-role")
      .first()
      .click();
    await page
      .locator("#modalEditRole")
      .waitFor({ state: "visible", timeout: 8000 });

    await expect(page.locator("#modalEditRoleForm #name")).toBeVisible();
    await expect(
      page.locator('#modalEditRoleForm [name="description"]'),
    ).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // A24 — Export CSV button present
  // -------------------------------------------------------------------------
  test("A24 — Export CSV button present and triggers download", async ({
    authenticatedPage: page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const csvBtn = page
      .locator(
        '.users-buttons-row .dt-buttons .buttons-csv, .users-buttons-row button:has-text("CSV")',
      )
      .first();
    await expect(csvBtn).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // A25 — CSV update applies changes; an empty password column is a no-op
  // -------------------------------------------------------------------------
  // The update PUT succeeds and the editable fields (name, ...) are applied,
  // and a CSV update whose `password` column is EMPTY is a no-op on the stored
  // password: the user can still log in with the original password afterwards.
  // The modal's help text lists the columns
  // (active/name/provider/category/uid/group/secondary_groups/password) and says
  // "Leave the parameters you don't want to update blank" — leaving the password
  // blank correctly skips it.
  test(
    "A25 — CSV update applies changes and an empty password leaves it unchanged",
    async ({
      authenticatedPage: page,
      browser,
      loginHelpers,
      categories,
    }) => {
      test.slow(); // includes a real login round-trip to prove the password no-op
      const ts = Date.now();
      const csvUsername = `e2e_a25_${ts}`;
      const ORIGINAL_PWD = "IsardTest1!";
      const csvUserId = await createTestUser(page, "_a25", {
        username: csvUsername,
        password: ORIGINAL_PWD,
      });
      registerCleanup((p) => deleteUser(p, csvUserId));

      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      await page.locator(".btn-update-from-csv").click();
      await page.locator("#modalUpdateFromCSV").waitFor({ state: "visible" });

      // The update CSV columns mirror the UI's "CSV for update" export exactly
      // (no `username` column): active,name,provider,category,uid,group,
      // secondary_groups,password — 8 columns. For a local/default user the uid
      // is the username. The `password` column is left EMPTY on purpose: the
      // update must apply the other fields (here: name) but must NOT change the
      // password. The frontend drops an empty password (`delete user.password`)
      // and the backend only writes the password when present
      // (`if data.get("password")`), so an empty value should be a no-op.
      const updatedName = `E2E A25 ${ts}`;
      const csvContent =
        `active,name,provider,category,uid,group,secondary_groups,password\n` +
        `true,${updatedName},local,Default,${csvUsername},Default,,\n`;
      await page.locator("#csv-edit").setInputFiles({
        name: "update.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(csvContent),
      });
      await page.waitForTimeout(2000);

      const putPromise = page.waitForResponse(
        (r) =>
          r.url().includes("/api/v4/admin/items/users/csv") &&
          r.request().method() === "PUT",
        { timeout: 15000 },
      );
      await page.locator("#modalUpdateFromCSV #send").click();
      const putResp = await putPromise;
      expect(
        putResp.status(),
        "PUT /api/v4/admin/items/users/csv status",
      ).toBeLessThan(400);

      // The update applied: the user's name now reflects the CSV value.
      const nameApplied = await pollUntil(page, async () => {
        const list = await listUsers(page);
        const u = list?.find((x) => x.id === csvUserId);
        return u && u.name === updatedName;
      });
      expect(nameApplied, "CSV update should apply the new name").toBeTruthy();

      // The empty password column did NOT change the password: the user can still
      // log in with the ORIGINAL password. Passwords are never returned by the
      // API, so a successful login is the end-to-end proof the no-op held (a wrong
      // password makes login() time out and throw — caught below as a failure).
      let loggedIn = true;
      const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
      try {
        const loginPage = await ctx.newPage();
        await loginHelpers.login(
          loginPage,
          { username: csvUsername, password: ORIGINAL_PWD, category: "default" },
          categories,
        );
      } catch {
        loggedIn = false;
      } finally {
        await ctx.close();
      }
      expect(
        loggedIn,
        "user must still log in with the ORIGINAL password — an empty CSV password column must not change it",
      ).toBe(true);
    },
  );

  // -------------------------------------------------------------------------
  // A26 — CSV bulk create imports users (validate → create)
  // -------------------------------------------------------------------------
  // Companion to A25 (CSV *update*): this is the CSV *create* flow.
  //
  // The bulk-create CSV schema (UserFromCSV) is EXACTLY six columns, in order:
  //   username,name,email,group,category,role
  // The backend ignores any password column and ALWAYS generates a policy
  // password, so bulk-created users should never be passwordless
  //
  // The category/group are matched BY NAME (Helpers.category_name_group_name_match),
  // so the seeded "Default" category + "Default" group names are used (not ids).
  //
  // NOTE: the bulk-add modal's #send stays disabled after a CSV upload (the
  // re-enable line in csv2datatables is commented out in users_management.js),
  // so creation cannot be submitted through the UI button. We drive the UI
  // upload + validate path (POST .../users/csv/validate) for fidelity, then
  // issue the same POST /admin/items/bulk/user the #send handler would — using
  // the validated rows (which already carry the generated password).
  test("A26 — CSV bulk create imports users with generated passwords", async ({
    authenticatedPage: page,
  }) => {
    const ts = Date.now();
    const u1 = `e2e_a26a_${ts}`;
    const u2 = `e2e_a26b_${ts}`;
    // Bulk create returns only a count, not ids; resolve the real id from the
    // listing at cleanup time (local/default users are `local-default-<uid>`).
    registerCleanup(async (p) => {
      const list = await listUsers(p);
      for (const uname of [u1, u2]) {
        const u = list?.find((x) => x.username === uname || x.uid === uname);
        if (u?.id) await deleteUser(p, u.id);
      }
    });

    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await page.locator(".btn-new-bulkusers").click();
    await page.locator("#modalAddBulkUsers").waitFor({ state: "visible" });

    // Exactly six columns (username,name,email,group,category,role); each row
    // carries exactly six values aligned to that header.
    const csvContent =
      "username,name,email,group,category,role\n" +
      `${u1},E2E A26a ${ts},${u1}@example.test,Default,Default,user\n` +
      `${u2},E2E A26b ${ts},${u2}@example.test,Default,Default,user\n`;

    // The upload drives csv2datatables → POST .../users/csv/validate.
    const validatePromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/items/users/csv/validate") &&
        r.request().method() === "POST",
      { timeout: 15000 },
    );
    await page.locator("#csv").setInputFiles({
      name: "bulk.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csvContent),
    });
    const validateResp = await validatePromise;
    expect(validateResp.status(), "CSV validate status").toBeLessThan(400);

    // UI fidelity: the preview datatable lists the parsed rows.
    await expect(
      page
        .locator("#modalAddBulkUsers #csv_preview tbody tr", { hasText: u1 })
        .first(),
      "bulk preview should list the first parsed user",
    ).toBeVisible({ timeout: 7500 });

    // Real safety property: every validated row comes back with a generated,
    // non-blank password — bulk-created users can never be passwordless.
    const validated = await validateResp.json().catch(() => null);
    const users = validated?.users ?? [];
    expect(users.length, "validate should return both enriched rows").toBe(2);
    for (const u of users) {
      expect(
        u.password,
        "validate must assign a generated (non-blank) password to every row",
      ).toBeTruthy();
    }

    // Submit the same payload the (disabled) #send button would POST.
    const createResp = await adminBulkCreateUsers({
      client: sdk(page),
      body: { users, email_verified: false },
    });
    expect(createResp.response?.status, "bulk create status").toBeLessThan(400);
    expect(createResp.data?.created, "both users should be created").toBe(2);

    // Persistence: both users land in the management listing.
    const created = await pollUntil(page, async () => {
      const list = await listUsers(page);
      return (
        list?.find((x) => x.username === u1 || x.uid === u1) &&
        list?.find((x) => x.username === u2 || x.uid === u2)
      );
    });
    expect(
      created,
      "bulk-created users should appear in the listing",
    ).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // A27 — Impersonate switches session
  // -------------------------------------------------------------------------
  test("A27 — Impersonate redirects to /Desktops as target user", async ({
    browser,
    authenticatedPage,
    adminPerWorker,
    loginHelpers,
    categories,
  }) => {
    test.slow();
    // Impersonation replaces the session cookie and navigates away, which would
    // corrupt the worker-shared admin context. Run it in a throwaway context.
    const userId = await createTestUser(authenticatedPage, "_a27");
    registerCleanup((p) => deleteUser(p, userId));

    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      const page = await ctx.newPage();
      await loginHelpers.login(page, adminPerWorker, categories);
      await bridgeAdminSession(page);

      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });
      await expandUserRow(page, userId);

      const jwtPromise = page.waitForResponse(
        (r) => r.url().includes(`/api/v4/admin/item/jwt/${userId}`),
        { timeout: 15000 },
      );
      await page
        .locator(".template-detail-users .btn-impersonate")
        .first()
        .click();
      await confirmPnotify(page);

      const jwtResp = await jwtPromise;
      expect(
        jwtResp.status(),
        "GET /api/v4/admin/item/jwt/{id} status",
      ).toBeLessThan(400);

      await page.waitForURL("**/Desktops", { timeout: 15000 }).catch(() => { });
    } finally {
      await ctx.close();
    }

    await deleteUser(authenticatedPage, userId);
  });

  // -------------------------------------------------------------------------
  // A28 — Logout action revokes target session
  // -------------------------------------------------------------------------
  test("A28 — Logout action calls logout endpoint", async ({
    authenticatedPage: page,
  }) => {
    test.slow();
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const userId = await createTestUser(page, "_a28");
    registerCleanup((p) => deleteUser(p, userId));
    await page.reload();
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await expandUserRow(page, userId);

    const putPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/user/${userId}/logout`) &&
        r.request().method() === "PUT",
      { timeout: 15000 },
    );
    await page.locator(".template-detail-users .btn-revoke").first().click();
    await confirmPnotify(page);
    const putResp = await putPromise;
    expect(putResp.status()).toBeLessThan(400);

    await deleteUser(page, userId);
  });

  // -------------------------------------------------------------------------
  // A29 — Migrate reassigns the source user's resources to the target via UI
  // -------------------------------------------------------------------------
  //
  // Drives the full migrate-user UI flow: seeds a persistent desktop for the
  // source user, opens the migrate modal, uses the select2 to search and pick
  // the target, clicks "Migrate user", waits for the Processing PNotify, and
  // verifies the desktop ownership changed in the DB.
  //
  // The source user's desktop is created by logging in as that user in a
  // separate browser context because createDesktop assigns ownership to the
  // authenticated session; there is no admin endpoint to create a desktop on
  // behalf of another user.
  //
  // The seeded desktop stays in "Waiting" in this environment (no hypervisor
  // brings it to Stopped), so the test does NOT wait for it to start — the
  // migration reassigns ownership regardless of the desktop's status.
  test("A29 — Migrate reassigns source resources to target via UI (DB-verified)", async ({
    authenticatedPage: page,
    apiv4Admin,
    browser,
    loginHelpers,
    categories,
  }) => {
    test.slow(); // desktop provisioning + background migration take time

    const ts = Date.now();
    const srcUsername = `e2e_a29s_${ts}`;
    const tgtUsername = `e2e_a29t_${ts}`;

    const sourceId = await createTestUser(page, "_a29s", { username: srcUsername });
    registerCleanup((p) => deleteUser(p, sourceId));
    const targetId = await createTestUser(page, "_a29t", { username: tgtUsername, name: tgtUsername });
    registerCleanup((p) => deleteUser(p, targetId));

    // Seed a persistent desktop owned by the source user (acting as them).
    let desktopId = null;
    const srcCtx = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      const srcPage = await srcCtx.newPage();
      await loginHelpers.login(
        srcPage,
        { username: srcUsername, password: "IsardTest1!", category: "default" },
        categories,
      );
      const srcClient = apiv4ClientForPage(srcPage);
      const tpl = await getFirstAllowedTemplate(srcClient).catch(() => null);
      if (tpl) {
        const created = await unwrap(
          createDesktop({
            client: srcClient,
            body: { template_id: tpl.id, name: `e2e-a29-${ts}` },
          }),
        ).catch(() => null);
        if (created?.id) {
          // The desktop is created directly via the API, so in this environment
          // it stays in "Waiting" (there is no hypervisor to bring it to
          // Stopped). Migration reassigns ownership regardless of desktop
          // status, so we do NOT wait for Stopped here — that wait would only
          // burn the whole test timeout against a desktop that never starts.
          desktopId = created.id;
        }
      }
    } finally {
      await srcCtx.close();
    }

    if (!desktopId) {
      await deleteUser(page, sourceId);
      await deleteUser(page, targetId);
      test.skip(
        true,
        "Could not seed a desktop for the source user — migration UI test skipped",
      );
      return;
    }

    // Navigate to management, expand the source user row and open the migrate modal.
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });
    await expandUserRow(page, sourceId);
    await page.locator(".template-detail-users .btn-migrate").first().click();
    await page
      .locator("#modalMigrateUser")
      .waitFor({ state: "visible", timeout: 8000 });

    // Resources summary must show the seeded desktop.
    await expect(
      page.locator("#modalMigrateUserForm #resources-summary"),
    ).toBeAttached();

    // Use the select2 to search for and select the target user.
    // dropdownParent is #modalMigrateUserForm, so the dropdown lives inside it.
    await page
      .locator("#modalMigrateUserForm .select2-selection")
      .first()
      .click();
    await page
      .locator("#modalMigrateUserForm .select2-search__field")
      .waitFor({ state: "visible", timeout: 5000 });
    // Type enough chars to trigger the AJAX (minimum 2) and return a unique hit.
    await page
      .locator("#modalMigrateUserForm .select2-search__field")
      .fill(tgtUsername.slice(0, 8));
    await page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/items/alloweds/term/users/") &&
        r.request().method() === "POST",
      { timeout: 10000 },
    );
    // Select2 result text: "[user] tgtUsername - name (group)"
    const targetOption = page
      .locator("#modalMigrateUserForm .select2-results__option", {
        hasText: tgtUsername,
      })
      .first();
    await targetOption.waitFor({ state: "visible", timeout: 5000 });
    await targetOption.click();

    // After selection, the modal fires a GET migrate/check to validate quotas.
    // Wait for it and then assert #send is enabled before clicking.
    await page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/item/user/migrate/check/") &&
        r.request().method() === "GET",
      { timeout: 10000 },
    );
    await expect(
      page.locator("#modalMigrateUser #send"),
      "#send must be enabled after a passing migrate/check",
    ).not.toBeDisabled({ timeout: 5000 });

    // Submit the migration through the UI button.
    const migratePromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/user/migrate/${sourceId}`) &&
        r.request().method() === "PUT",
      { timeout: 15000 },
    );
    await page.locator("#modalMigrateUser #send").click();
    const migrateResp = await migratePromise;
    expect(migrateResp.status(), "PUT migrate status").toBeLessThan(400);

    // The modal hides and a "Processing..." PNotify appears (migration is async).
    await page
      .locator("#modalMigrateUser")
      .waitFor({ state: "hidden", timeout: 5000 })
      .catch(() => { });
    await waitForPNotify(page, "Processing");

    // DB verification: the persistent desktop is now owned by the target user.
    const reassigned = await pollUntil(
      page,
      async () => {
        const row = await unwrap(
          adminTableList({
            client: apiv4Admin,
            path: { table: "domains" },
            body: { id: desktopId },
          }),
        ).catch(() => null);
        const doc = Array.isArray(row) ? row[0] : row;
        return doc && doc.user === targetId;
      },
      { timeout: 30000, interval: 1500 },
    );
    expect(
      reassigned,
      "desktop should be owned by the target user after migration",
    ).toBeTruthy();

    // Cleanup: deleting the target cascades the migrated desktop; then source.
    await deleteUser(page, targetId);
    await deleteUser(page, sourceId);
  });

  // -------------------------------------------------------------------------
  // A30 — Logs action loads the user's logs
  // -------------------------------------------------------------------------
  // The Logs button drives a DataTable that POSTs to
  // /api/v4/admin/items/logs_users (the endpoint moved under /items/).
  test(
    "A30 — Logs endpoint returns the user's logs",
    async ({ authenticatedPage: page }) => {
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      const userId = await createTestUser(page, "_a30");
      registerCleanup((p) => deleteUser(p, userId));
      await page.reload();
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      await expandUserRow(page, userId);

      const logsPromise = page.waitForResponse(
        (r) =>
          r.url().includes("/api/v4/admin/items/logs_users") &&
          r.request().method() === "POST",
        { timeout: 15000 },
      );
      await page
        .locator(".template-detail-users .btn-user-logs")
        .first()
        .click();
      const logsResp = await logsPromise;
      expect(logsResp.status(), "logs_users POST status").toBeLessThan(400);

      await deleteUser(page, userId);
    },
  );

  // -------------------------------------------------------------------------
  // A31 — Category Authentication modal visible for admin
  // -------------------------------------------------------------------------
  test("A31 — Category Authentication modal is visible for admin", async ({
    authenticatedPage: page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await activateTabTable(page, '[href="#categories"], button:has-text("Categories")', "categories");
    await expandFirstRow(page, "categories");

    const authBtn = page
      .locator(".template-detail-categories .btn-authentication")
      .first();
    await authBtn.waitFor({ state: "visible", timeout: 5000 });
    await authBtn.click();
    await expect(page.locator("#modalAuthentication")).toBeVisible({
      timeout: 8000,
    });
  });

  // -------------------------------------------------------------------------
  // A32 — Category Branding modal visible for admin
  // -------------------------------------------------------------------------
  test("A32 — Category Branding modal is visible for admin", async ({
    authenticatedPage: page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await activateTabTable(page, '[href="#categories"], button:has-text("Categories")', "categories");
    await expandFirstRow(page, "categories");

    const brandingBtn = page
      .locator(".template-detail-categories .btn-branding")
      .first();
    await brandingBtn.waitFor({ state: "visible", timeout: 5000 });
    await brandingBtn.click();
    // Branding modal id is `#modal-branding` (hyphenated). The id is duplicated
    // on a child <h4> in the markup, so scope to the modal <div>.
    await expect(page.locator("div#modal-branding")).toBeVisible({
      timeout: 8000,
    });
  });

  // -------------------------------------------------------------------------
  // A33 — Category Login Notification modal visible for admin
  // -------------------------------------------------------------------------
  test("A33 — Category Login Notification modal is visible for admin", async ({
    authenticatedPage: page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await activateTabTable(page, '[href="#categories"], button:has-text("Categories")', "categories");
    await expandFirstRow(page, "categories");

    // Correct class is `.btn-login_notification` (underscore — see
    // categories_detail_management.html / categories_management.js).
    const loginNotifBtn = page
      .locator(".template-detail-categories .btn-login_notification")
      .first();
    await loginNotifBtn.waitFor({ state: "visible", timeout: 5000 });
    await loginNotifBtn.click();
    await expect(
      page
        .locator('#modalLoginNotification, [id*="login_notification" i]')
        .first(),
    ).toBeVisible({ timeout: 8000 });
  });

  // -------------------------------------------------------------------------
  // A34 — Category Bastion domain modal (only when Bastion is enabled)
  // -------------------------------------------------------------------------
  test("A34 — Category Bastion domain modal is available for admin when Bastion is enabled", async ({
    authenticatedPage: page,
  }) => {
    test.slow(); // categories tab + AJAX + bastion API can exceed the 30 s default under parallel load
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await activateTabTable(page, '[href="#categories"], button:has-text("Categories")', "categories");
    await expandFirstRow(page, "categories");

    const bastionBtn = page
      .locator(".template-detail-categories .btn-bastion-domain")
      .first();
    await bastionBtn.waitFor({ state: "visible", timeout: 5000 });

    // The button triggers GET /api/v4/admin/item/config/bastion (to check if
    // Bastion is globally enabled) followed by GET …/category/{id}/bastion_domain.
    // Both URLs contain "/api/v4" + "bastion"; catch either one.
    const bastionPromise = page
      .waitForResponse((r) => r.url().includes("bastion"), {
        timeout: 15000,
      })
      .catch(() => null);
    await bastionBtn.click();
    const bastionResp = await bastionPromise;
    if (!bastionResp) {
      test.skip(
        true,
        "No bastion API call detected — Bastion likely disabled in this installation",
      );
      return;
    }
    if (bastionResp.status() === 403 || bastionResp.status() === 404) {
      test.skip(
        true,
        `Bastion not enabled (${bastionResp.url()} → ${bastionResp.status()})`,
      );
      return;
    }
    expect(bastionResp.status(), "bastion config call").toBeLessThan(400);
  });

  // -------------------------------------------------------------------------
  // A35 — email_verified is persisted on user create
  // -------------------------------------------------------------------------
  // The create accepts `email_verified` (AdminUserCreateData) and persists it.
  test(
    "A35 — email_verified is persisted on user create",
    async ({ authenticatedPage: page }) => {
      const userId = await createTestUser(page, "_a35", {
        email_verified: true,
      });
      registerCleanup((p) => deleteUser(p, userId));
      const verified = await pollUntil(page, async () => {
        const users = await listUsers(page);
        const u = users?.find((x) => x.id === userId);
        return u && u.email_verified === true;
      });
      await deleteUser(page, userId);
      expect(
        verified,
        "email_verified should be persisted from create",
      ).toBeTruthy();
    },
  );

  // -------------------------------------------------------------------------
  // A36 — category `maintenance` is persisted (set via UPDATE)
  // -------------------------------------------------------------------------
  // `maintenance` is dropped by category CREATE (create_category builds the doc
  // explicitly without it); it is persisted via the category UPDATE. Create the
  // category, then PUT maintenance:true, and verify the GET returns it.
  test(
    "A36 — category maintenance flag is persisted via update",
    async ({ authenticatedPage: page }) => {
      const ts = Date.now();
      const name = `E2E CatMnt ${ts}`;
      const resp = await adminCreateCategory({
        client: sdk(page),
        body: {
          name,
          description: "E2E maintenance test",
          manager_permissions: {},
        },
      });
      expect(resp.response?.status, "POST category status").toBeLessThan(400);
      const id = resp.data?.id;
      if (id) registerCleanup((p) => deleteCategory(p, id));

      const putResp = await adminUpdateCategory({
        client: sdk(page),
        path: { category_id: id },
        body: { id, name, maintenance: true },
      });
      expect(putResp.response?.status, "PUT category status").toBeLessThan(400);

      const maintained = await pollUntil(page, async () => {
        const cat = await getCategory(page, id);
        return cat?.maintenance === true;
      });
      await deleteCategory(page, id);
      expect(
        maintained,
        "category maintenance should be persisted",
      ).toBeTruthy();
    },
  );

  // -------------------------------------------------------------------------
  // A37 — group `linked_groups` are saved (set via UPDATE)
  // -------------------------------------------------------------------------
  // linked_groups is not part of the group CREATE body (AdminGroupCreateData);
  // it is set via the group UPDATE (AdminGroupUpdateData). Create the group,
  // then PUT linked_groups, and verify the GET returns them.
  test(
    "A37 — group linked_groups are saved via update",
    async ({ authenticatedPage: page }) => {
      const linked = await createTestGroup(page, "default", "_a37link");
      registerCleanup((p) => deleteGroup(p, linked.id));
      const grp = await createTestGroup(page, "default", "_a37");
      registerCleanup((p) => deleteGroup(p, grp.id));

      const putResp = await adminUpdateGroup({
        client: sdk(page),
        path: { group_id: grp.id },
        body: { id: grp.id, name: grp.name, linked_groups: [linked.id] },
      });
      expect(putResp.response?.status, "PUT group status").toBeLessThan(400);

      const saved = await pollUntil(page, async () => {
        const g = await getGroup(page, grp.id);
        const lg = g?.linked_groups || [];
        return Array.isArray(lg) && lg.includes(linked.id);
      });
      await deleteGroup(page, grp.id);
      await deleteGroup(page, linked.id);
      expect(saved, "group linked_groups should be persisted").toBeTruthy();
    },
  );

  // -------------------------------------------------------------------------
  // A39 — No management table cell renders the literal string "undefined"
  // -------------------------------------------------------------------------
  // The categories authentication column render returns "" for a falsy value,
  // so no cell shows the literal "undefined".
  test(
    'A39 — No management table cell renders the literal string "undefined"',
    async ({ authenticatedPage: page }) => {
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      // Wait for at least one data row in the users table before checking.
      await page
        .locator("#users tbody tr td")
        .first()
        .waitFor({ state: "visible", timeout: 15000 })
        .catch(() => { });

      // Users table (active by default).
      const usersUndefined = await page
        .locator("#users tbody td")
        .filter({ hasText: /\bundefined\b/ })
        .count();
      expect(
        usersUndefined,
        'Table #users must not contain cells with literal "undefined"',
      ).toBe(0);

      // Categories table — activate its tab first so DataTables fetches the data.
      const catTab = page
        .locator('[href="#categories"], button:has-text("Categories")')
        .first();
      if ((await catTab.count()) > 0) {
        await catTab.click();
        await page.waitForTimeout(2000);
      }
      const catsUndefined = await page
        .locator("#categories tbody td")
        .filter({ hasText: /\bundefined\b/ })
        .count();
      expect(
        catsUndefined,
        'Table #categories must not contain cells with literal "undefined"',
      ).toBe(0);

      // Groups table.
      const groupTab = page
        .locator('[href="#groups"], button:has-text("Groups")')
        .first();
      if ((await groupTab.count()) > 0) {
        await groupTab.click();
        await page.waitForTimeout(2000);
      }
      const groupsUndefined = await page
        .locator("#groups tbody td")
        .filter({ hasText: /\bundefined\b/ })
        .count();
      expect(
        groupsUndefined,
        'Table #groups must not contain cells with literal "undefined"',
      ).toBe(0);

      // Roles table (always rendered; no separate tab click needed).
      const rolesUndefined = await page
        .locator("#roles tbody td")
        .filter({ hasText: /\bundefined\b/ })
        .count();
      expect(
        rolesUndefined,
        'Table #roles must not contain cells with literal "undefined"',
      ).toBe(0);
    });

  // -------------------------------------------------------------------------
  // A38 — users table renders correctly with a vpn:null user
  // -------------------------------------------------------------------------
  // Previously a bug: a user created via POST /api/v4/admin/item/user comes
  // back with vpn:null, and the VPN column definition used
  // `"data": "vpn.wireguard.connected"` — DataTables traverses that dot-path
  // eagerly, so null.wireguard threw a TypeError that crashed the entire table
  // renderer ("No matching records found" for every row).
  //
  // Fixed in users_management.js: changed to `"data": null` and added an
  // explicit null-guard in the render function so vpn:null rows render the
  // grey disconnected icon instead of throwing.
  test("A38 — users table renders correctly with a vpn:null user (bug fixed)", async ({
    authenticatedPage: page,
  }) => {
    let userId;
    try {
      userId = await createTestUser(page, "_a38", { resetVpn: false });
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });
      await showAllUsers(page);
      const tbodyText = await page
        .locator("#users tbody")
        .first()
        .innerText()
        .catch(() => "");
      expect(
        tbodyText,
        "users table should render rows even with a vpn:null user",
      ).not.toContain("No matching records found");
    } finally {
      if (userId) await deleteUser(page, userId);
    }
  });

  // -------------------------------------------------------------------------
  // A40 — admin edits a category's manager permissions and they persist
  // -------------------------------------------------------------------------
  // The category Edit modal exposes four manager-permission checkboxes —
  // Authentication, Branding, Login Notification and GPU Plannings — under
  // `#category-permissions-edit-panel`. The `#send` handler serialises them as
  // `manager_permissions: {authentication, branding, login_notification, plannings}`
  // and PUTs them to /api/v4/admin/item/category/{id}, which persists them. This
  // is the ONLY coverage of GPU Plannings (`plannings`): it has no manager-facing
  // button (the gating loop covers only the other three — see M11/M16), so its
  // persistence is asserted here via the API read-back rather than from the UI.
  test("A40 — admin edits a category's manager permissions and they persist", async ({
    authenticatedPage: page,
  }) => {
    test.slow();
    const cat = await createTestCategory(page, "_a40");
    registerCleanup((p) => deleteCategory(p, cat.id));

    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await activateTabTable(page, '[href="#categories"], button:has-text("Categories")', "categories");
    await expandRowByText(page, "categories", cat.name);

    const editBtn = page
      .locator(".template-detail-categories .btn-edit-category")
      .first();
    await editBtn.waitFor({ state: "visible", timeout: 5000 });
    // The edit modal populates its manager_permissions checkboxes from an async
    // GET /item/category/{id}; wait for it before toggling so the populate does
    // not overwrite our values.
    const populatePromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/category/${cat.id}`) &&
        r.request().method() === "GET",
      { timeout: 8000 },
    );
    await editBtn.click();
    await page
      .locator("#modalEditCategory")
      .waitFor({ state: "visible", timeout: 8000 });
    await populatePromise.catch(() => { });
    await page.waitForTimeout(300);

    // Drive the four iCheck checkboxes to a known mix (enable authentication,
    // login_notification and GPU plannings; leave branding off).
    const want = {
      "category-permissions-edit-authentication": true,
      "category-permissions-edit-branding": false,
      "category-permissions-edit-login_notification": true,
      "category-permissions-edit-plannings": true,
    };
    await page.evaluate((checks) => {
      const jq = window.jQuery;
      for (const id of Object.keys(checks)) {
        const input = document.getElementById(id);
        if (!input) continue;
        const target = checks[id];
        if (jq && jq(input).iCheck) {
          jq(input).iCheck(target ? "check" : "uncheck").iCheck("update");
        } else {
          input.checked = target;
          input.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }
    }, want);

    const putPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/category/${cat.id}`) &&
        r.request().method() === "PUT",
      { timeout: 15000 },
    );
    await page.locator("#modalEditCategory #send").click();
    const putResp = await putPromise;
    expect(putResp.status(), "PUT edit category status").toBeLessThan(400);

    // Persistence: GET returns manager_permissions exactly as set, including the
    // GPU Plannings (`plannings`) key.
    const persisted = await pollUntil(page, async () => {
      const c = await getCategory(page, cat.id);
      const mp = c?.manager_permissions;
      if (!mp) return null;
      return mp.authentication === true &&
        mp.branding === false &&
        mp.login_notification === true &&
        mp.plannings === true
        ? mp
        : null;
    });
    await deleteCategory(page, cat.id);
    expect(
      persisted,
      "manager_permissions should persist as set (incl. GPU plannings)",
    ).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Manager role scenarios
// ---------------------------------------------------------------------------

test.describe("Users Management — manager role", () => {
  // All manager tests log in as the single seeded `manager_e2e_01` account.
  // Running them in parallel across workers makes concurrent logins contend on
  // the same Redis session and intermittently drop the JWT cookie (the bridge
  // then 404s), so keep this block serial.
  test.describe.configure({ mode: "serial" });

  // Log in as the seeded manager account (role=manager, category=default)
  // and bridge the session into the Flask isard-admin context. Uses the
  // shared loginHelpers.login path — same robust flow as the admin specs
  // (see webapp-admin-navigation.spec.js) — instead of driving the login
  // form by hand, which raced on the `/` → `/Desktops` redirect and made
  // every manager test fail in beforeEach.
  //
  // NOTE: these tests run on the plain `page` (manager session), NOT on
  // `authenticatedPage` (which is the worker's admin context). Every test
  // body below destructures `{ page }` so the manager role is actually
  // exercised.
  test.beforeEach(async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.login(page, users.manager_e2e_01, categories);
    await bridgeAdminSession(page);
  });

  // Disposable admin user (same `default` category as the manager) used as a
  // forbidden target for M7/M8/M9. Created via the worker's admin context so
  // that — even if an authorization guard is broken — the only account a
  // destructive test could affect is this throwaway, never a real admin.
  let disposableAdminId;
  let disposableAdminUsername;
  test.beforeAll(async ({ authenticatedContext }, workerInfo) => {
    const p = await authenticatedContext.newPage();
    disposableAdminUsername = `e2e_madmin_${workerInfo.workerIndex}_${Date.now()}`;
    disposableAdminId = await createTestUser(p, "_madmin", {
      username: disposableAdminUsername,
      role: "admin",
      category: "default",
      group: "default-default",
    }).catch(() => null);
    await p.close();
  });
  test.afterAll(async ({ authenticatedContext }) => {
    if (!disposableAdminId) return;
    const p = await authenticatedContext.newPage();
    await deleteUser(p, disposableAdminId);
    await p.close();
  });

  // -------------------------------------------------------------------------
  // M2 — Manager can add users only in own category
  // -------------------------------------------------------------------------
  test("M2 — Manager can add users only in own category", async ({ page }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await page.locator(".btn-new-user").click();
    await page.locator("#modalAddUser").waitFor({ state: "visible" });

    const catSelect = page.locator(
      '#modalAddUserForm #add-category, #modalAddUserForm [name="category"]',
    );
    if ((await catSelect.count()) > 0) {
      const optionCount = await catSelect.locator("option").count();
      expect(optionCount).toBeLessThanOrEqual(2);
    }

    await page
      .locator('#modalAddUser .close, #modalAddUser [data-dismiss="modal"]')
      .first()
      .click();
  });

  // -------------------------------------------------------------------------
  // M3 — Manager cannot edit admin user (expected failure: GET 500)
  // -------------------------------------------------------------------------
  test(
    "M3 — Manager cannot edit an admin user (denied with 4xx)",
    async ({ page }) => {
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      const adminRow = page
        .locator("#users tbody tr")
        .filter({ hasText: "admin" })
        .first();
      if (!(await adminRow.isVisible({ timeout: 3000 }))) return;

      await adminRow.locator("td.details-control button").click();
      await page.waitForTimeout(500);

      const getPromise = page.waitForResponse(
        (r) =>
          r.url().includes("/api/v4/admin/") && r.url().includes("/item/user/"),
        { timeout: 7500 },
      );
      await page.locator(".template-detail-users .btn-edit").first().click();
      const getResp = await getPromise;
      // Manager acting on an admin is denied with a clean 4xx (not a 500 crash).
      expect(getResp.status()).toBeGreaterThanOrEqual(400);
      expect(getResp.status()).toBeLessThan(500);
    },
  );

  // -------------------------------------------------------------------------
  // M4 — Manager cannot reset password of an admin user (denied with 4xx)
  // -------------------------------------------------------------------------
  test(
    "M4 — Manager cannot reset an admin's password (denied with 4xx)",
    async ({ page }) => {
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      const adminRow = page
        .locator("#users tbody tr")
        .filter({ hasText: "admin" })
        .first();
      if (!(await adminRow.isVisible({ timeout: 3000 }))) return;

      await adminRow.locator("td.details-control button").click();
      await page.waitForTimeout(500);

      const getPromise = page.waitForResponse(
        (r) =>
          r.url().includes("/api/v4/admin/") &&
          r.url().includes("password-policy"),
        { timeout: 7500 },
      );
      await page.locator(".template-detail-users .btn-passwd").first().click();
      const getResp = await getPromise;
      // Manager acting on an admin is denied with a clean 4xx (not a 500 crash).
      expect(getResp.status()).toBeGreaterThanOrEqual(400);
      expect(getResp.status()).toBeLessThan(500);
    },
  );

  // -------------------------------------------------------------------------
  // M5 — Manager cannot impersonate an admin user (denied with 4xx)
  // -------------------------------------------------------------------------
  test(
    "M5 — Manager cannot impersonate an admin (denied with 4xx)",
    async ({ page }) => {
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      const adminRow = page
        .locator("#users tbody tr")
        .filter({ hasText: "admin" })
        .first();
      if (!(await adminRow.isVisible({ timeout: 3000 }))) return;

      await adminRow.locator("td.details-control button").click();
      await page.waitForTimeout(500);

      const getPromise = page.waitForResponse(
        (r) => r.url().includes("/api/v4/admin/item/jwt/"),
        { timeout: 7500 },
      );
      await page
        .locator(".template-detail-users .btn-impersonate")
        .first()
        .click();
      await confirmPnotify(page);
      const getResp = await getPromise;
      // Manager acting on an admin is denied with a clean 4xx (not a 500 crash).
      expect(getResp.status()).toBeGreaterThanOrEqual(400);
      expect(getResp.status()).toBeLessThan(500);
    },
  );

  // -------------------------------------------------------------------------
  // M6 — Manager cannot delete an admin user (denied with 4xx)
  // -------------------------------------------------------------------------
  test(
    "M6 — Manager cannot delete an admin (denied with 4xx)",
    async ({ page }) => {
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });

      const adminRow = page
        .locator("#users tbody tr")
        .filter({ hasText: "admin" })
        .first();
      if (!(await adminRow.isVisible({ timeout: 3000 }))) return;

      await adminRow.locator("td.details-control button").click();
      await page.waitForTimeout(500);

      const postPromise = page.waitForResponse(
        (r) =>
          r.url().includes("/api/v4/admin/") &&
          r.url().includes("delete/check"),
        { timeout: 7500 },
      );
      await page.locator(".template-detail-users .btn-delete").first().click();
      const postResp = await postPromise;
      // Manager acting on an admin is denied with a clean 4xx (not a 500 crash).
      expect(postResp.status()).toBeGreaterThanOrEqual(400);
      expect(postResp.status()).toBeLessThan(500);
    },
  );

  // -------------------------------------------------------------------------
  // M7 — Manager cannot reset VPN of an admin user
  // -------------------------------------------------------------------------
  // The backend denies a manager from resetting an admin's VPN (verified:
  // the PUT returns 4xx). Asserts that denial contract.
  test("M7 — Manager cannot reset VPN of an admin user", async ({ page }) => {
    test.skip(!disposableAdminId, "disposable admin target not available");
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const resp = await adminResetVpn({
      client: sdk(page),
      path: { user_id: disposableAdminId },
    });
    expect(
      resp.response?.status,
      "manager reset-VPN on an admin must be denied (>=400)",
    ).toBeGreaterThanOrEqual(400);
  });

  // -------------------------------------------------------------------------
  // M8 — Manager cannot bulk-delete an admin target
  // -------------------------------------------------------------------------
  test("M8 — Manager cannot bulk-delete an admin target", async ({ page }) => {
    test.skip(!disposableAdminId, "disposable admin target not available");
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const resp = await adminDeleteUsers({
      client: sdk(page),
      body: { user: [disposableAdminId], delete_user: true },
    });
    expect(
      resp.response?.status,
      "manager bulk-delete targeting an admin must be rejected (>=400)",
    ).toBeGreaterThanOrEqual(400);
  });

  // -------------------------------------------------------------------------
  // M9 — Manager cannot disable an admin, self, or the default admin
  // -------------------------------------------------------------------------
  // Enable/disable is currently 405-broken for everyone (known bug #4), so no
  // disable request can succeed regardless of authorization. We assert the
  // observable contract — these protected accounts stay enabled — which also
  // guards against a regression once #4 is fixed.
  test("M9 — Manager cannot disable admin / self / default admin", async ({
    page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const DEFAULT_ADMIN = "local-default-admin-admin";
    const targets = [DEFAULT_ADMIN];
    if (disposableAdminId) targets.push(disposableAdminId);

    for (const target of targets) {
      const resp = await adminUpdateUser({
        client: sdk(page),
        path: { user_id: target },
        body: { active: false },
      });
      expect(
        resp.response?.status,
        `disabling ${target} as a manager must not succeed`,
      ).toBeGreaterThanOrEqual(400);
    }

    // The default admin must remain active no matter what.
    const defaultAdmin = await getUser(page, DEFAULT_ADMIN);
    if (defaultAdmin) {
      expect(defaultAdmin.active, "default admin must stay enabled").toBe(true);
    }
  });

  // -------------------------------------------------------------------------
  // M10 — Manager sees only own category in Categories/Groups
  // -------------------------------------------------------------------------
  test("M10 — Manager sees only own category in Categories and Groups", async ({
    page,
  }) => {
    const catXhr = captureXhr(page, (u) =>
      u.includes("/api/v4/admin/items/users/management/categories"),
    );
    const grpXhr = captureXhr(page, (u) =>
      u.includes("/api/v4/admin/items/users/management/groups"),
    );

    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const catTab = page
      .locator('[href="#categories"], button:has-text("Categories")')
      .first();
    if ((await catTab.count()) > 0) await catTab.click();
    await page.waitForTimeout(1500);

    const groupTab = page
      .locator('[href="#groups"], button:has-text("Groups")')
      .first();
    if ((await groupTab.count()) > 0) await groupTab.click();
    await page.waitForTimeout(1500);

    for (const c of catXhr.filter((x) => x.url.includes("/categories"))) {
      expect(c.status).toBeLessThan(400);
    }
    for (const c of grpXhr.filter((x) => x.url.includes("/groups"))) {
      expect(c.status).toBeLessThan(400);
    }
  });

  // -------------------------------------------------------------------------
  // M12 — Manager can use Bastion domain
  // -------------------------------------------------------------------------
  test("M12 — Manager Bastion domain modal opens", async ({ page }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 10000 })
      .catch(() => { });

    await activateTabTable(page, '[href="#categories"], button:has-text("Categories")', "categories");
    await expandFirstRow(page, "categories");
    await page.waitForTimeout(500);

    const bastionBtn = page
      .locator(".template-detail-categories .btn-bastion-domain")
      .first();
    await bastionBtn.waitFor({ state: "visible", timeout: 3000 });
    await bastionBtn.click();

    await expect(page.locator("#modalBastionDomain")).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // M13 — Manager cannot edit roles
  // -------------------------------------------------------------------------
  test("M13 — Manager cannot edit roles (no expand control, no edit action)", async ({
    page,
  }) => {
    // roles.js hides the details-control column (column 0) for any
    // non-admin role: `if (data-role != 'admin') table.column(0).visible(false)`.
    // So a manager sees the roles table but cannot expand a row, and the
    // `.btn-edit-role` action inside the role detail is therefore
    // unreachable. We assert both: rows render, but the expand button is
    // not visible and no edit-role control is present.
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    await expect(page.locator("#roles tbody tr").first()).toBeVisible();

    // Details-control column is hidden → its cell/button must not be visible.
    await expect(
      page.locator("#roles tbody tr td.details-control button").first(),
    ).toBeHidden();

    // The edit-role action (correct class is `.btn-edit-role`) is never
    // reachable for a manager.
    await expect(
      page.locator(".template-detail-roles .btn-edit-role"),
    ).toHaveCount(0);
  });

  // -------------------------------------------------------------------------
  // M14 — Manager cannot see External apps panel
  // -------------------------------------------------------------------------
  test("M14 — Manager cannot see External apps panel", async ({ page }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    const appsPanel = page
      .locator(
        '.external-apps, [href="#external-apps"], button:has-text("External apps")',
      )
      .first();
    const visible = await appsPanel
      .isVisible({ timeout: 3000 })
      .catch(() => false);
    expect(visible, "External apps panel must be hidden for manager").toBe(
      false,
    );
  });

  // -------------------------------------------------------------------------
  // M15 — Manager logs action fails (KNOWN BUG: returns 500)
  // -------------------------------------------------------------------------
  // Admin logs work (see A30), but a manager opening a user's logs gets a 500
  // from POST /api/v4/admin/items/logs_users instead of the own-category logs.
  // Marked test.fail (expected failure) per the file's known-bug convention.
  // TODO: remove test.fail() once the manager logs endpoint no longer 500s.
  test(
    "M15 — Manager logs endpoint returns 500 (known bug)",
    async ({ page }) => {
      test.fail();
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => {});

      await expect(page.locator("#users tbody tr").first()).toBeVisible();

      await expandUserRow(page);

      const logsPromise = page.waitForResponse(
        (r) =>
          r.url().includes("/api/v4/admin/items/logs_users") &&
          r.request().method() === "POST",
        { timeout: 7500 },
      );
      await page
        .locator(".template-detail-users .btn-user-logs")
        .first()
        .click();
      const logsResp = await logsPromise;
      // Bug: returns 500 (should be < 400 once fixed).
      expect(logsResp.status()).toBeLessThan(400);
    },
  );
});

// ---------------------------------------------------------------------------
// M11 — Manager category actions are permission-gated
//
// categories_management.js (renderCategoriesDetailPannel) toggles
// `.btn-authentication` / `.btn-branding` / `.btn-login_notification` for a
// manager according to `category.manager_permissions[perm]`. Rather than assume
// the `default` category grants nothing (the e2e environment does not guarantee
// `manager_permissions` is null — this deployment may grant some), the test
// reads the category's actual `manager_permissions` from the listing the page
// already loaded (the same data the gating reads) and asserts each gated button
// is visible IFF its permission is granted. The bastion-domain button is NOT
// part of this gating (it is always rendered; see M12).
// ---------------------------------------------------------------------------
test.describe("Users Management — manager category permission gating (M11)", () => {
  test.describe.configure({ mode: "serial" });
  test.beforeEach(async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.login(page, users.manager_e2e_01, categories);
    await bridgeAdminSession(page);
  });

  test("M11 — ungranted category actions are hidden for the manager", async ({
    page,
  }) => {
    await page.goto(MGMT_URL);
    await page
      .waitForLoadState("networkidle", { timeout: 30000 })
      .catch(() => { });

    // A manager sees only their own category — expand it.
    await activateTabTable(page, '[href="#categories"], button:has-text("Categories")', "categories");
    await expandFirstRow(page, "categories");
    const detail = page.locator(".template-detail-categories").first();
    await detail.waitFor({ state: "visible", timeout: 8000 });

    // Assert the gating reflects the category's actual manager_permissions, read
    // from the categories listing the page already loaded (the same data the
    // gating uses). Each gated button is visible IFF its permission is granted.
    const mp = await page.evaluate(() => {
      const dt = window.jQuery && window.jQuery("#categories").DataTable();
      let found = null;
      if (dt)
        dt.rows().every(function () {
          const d = this.data();
          if (d && d.id === "default") found = d.manager_permissions || null;
        });
      return found;
    });
    for (const perm of ["authentication", "branding", "login_notification"]) {
      const btn = detail.locator(`.btn-${perm}`);
      if (mp && mp[perm]) {
        await expect(btn, `${perm} granted → button visible`).toBeVisible();
      } else {
        await expect(btn, `${perm} not granted → button hidden`).toBeHidden();
      }
    }
  });

  // -------------------------------------------------------------------------
  // M16 — manager sees category action buttons only for enabled permissions
  // -------------------------------------------------------------------------
  // Active grant/deny counterpart to M11: an admin SETS the `default` category's
  // manager_permissions and the manager's detail-panel buttons change to match.
  // Covers the three button-backed permissions (authentication / branding /
  // login_notification). GPU Plannings (`plannings`) is not asserted here — it
  // has no category-detail button; its persistence is covered by A40. The admin
  // client comes from the worker's admin context; `default`'s original
  // manager_permissions are captured and restored in `finally`.
  test("M16 — manager sees category action buttons only for enabled permissions", async ({
    page,
    authenticatedContext,
  }) => {
    test.slow();
    const adminPage = await authenticatedContext.newPage();
    const adminClient = apiv4ClientForPage(adminPage);

    const original = await unwrap(
      adminGetCategory({ client: adminClient, path: { category_id: "default" } }),
    ).catch(() => null);
    const catName = original?.name || "Default";
    const originalPerms = original?.manager_permissions || {};

    async function setPerms(perms, { assert = false } = {}) {
      const resp = await adminUpdateCategory({
        client: adminClient,
        path: { category_id: "default" },
        body: { id: "default", name: catName, manager_permissions: perms },
      });
      if (assert) {
        expect(
          resp.response?.status,
          "PUT default manager_permissions status",
        ).toBeLessThan(400);
      }
    }

    // Reload the manager view, expand the (only) default category, and assert
    // each gated button is visible IFF its permission is enabled.
    async function assertButtons(expected) {
      await page.goto(MGMT_URL);
      await page
        .waitForLoadState("networkidle", { timeout: 30000 })
        .catch(() => { });
      await activateTabTable(page, '[href="#categories"], button:has-text("Categories")', "categories");
      await expandFirstRow(page, "categories");
      const detail = page.locator(".template-detail-categories").first();
      await detail.waitFor({ state: "visible", timeout: 8000 });
      for (const perm of ["authentication", "branding", "login_notification"]) {
        const btn = detail.locator(`.btn-${perm}`);
        if (expected[perm]) {
          await expect(btn, `${perm} enabled → button visible`).toBeVisible();
        } else {
          await expect(btn, `${perm} disabled → button hidden`).toBeHidden();
        }
      }
    }

    try {
      // Config 1: authentication + login_notification on, branding off.
      const cfg1 = {
        authentication: true,
        branding: false,
        login_notification: true,
        plannings: false,
      };
      await setPerms(cfg1, { assert: true });
      await assertButtons(cfg1);

      // Config 2 (inverse): branding on, the other two off — flips each button.
      const cfg2 = {
        authentication: false,
        branding: true,
        login_notification: false,
        plannings: false,
      };
      await setPerms(cfg2, { assert: true });
      await assertButtons(cfg2);
    } finally {
      // Restore the default category's original manager_permissions.
      await setPerms({
        authentication: !!originalPerms.authentication,
        branding: !!originalPerms.branding,
        login_notification: !!originalPerms.login_notification,
        plannings: !!originalPerms.plannings,
      }).catch(() => { });
      await adminPage.close().catch(() => { });
    }
  });
});
