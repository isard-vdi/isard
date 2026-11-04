// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Isolated category + manager provisioning for the category-config manager e2e
// specs, so they neither mutate the shared `default` category (racy under
// fullyParallel) nor depend on hand-seeded state. Deleting the category
// cascades its group and user.

// New categories ship a strict default password policy (>= 34 chars).
const STRONG_PWD = "IsardVDI-E2E-LongPassword-0123456789!Aa";

export const MGMT_URL = "/isard-admin/admin/users/Management";

async function postJson(request, url, data) {
  const resp = await request.post(url, { data });
  if (!resp.ok()) {
    throw new Error(`POST ${url} -> ${resp.status()}: ${await resp.text()}`);
  }
  return resp.json().catch(() => ({}));
}

// As admin, create an isolated category (with `managerPermissions`), a group
// and a manager in it; `suffix` disambiguates parallel workers.
export async function provisionManagerCategory(
  adminRequest,
  { suffix = "", managerPermissions = {} } = {},
) {
  const uniq = `${Date.now()}${suffix}${Math.floor(Math.random() * 1e6)}`;
  const catName = `E2E Brand ${uniq}`;
  const customUrl = `e2ebrand${uniq}`;

  const cat = await postJson(adminRequest, "/api/v4/admin/item/category", {
    name: catName,
    description: "E2E category-config spec (isolated, self-cleaned)",
    frontend: false,
    custom_url_name: customUrl,
    manager_permissions: managerPermissions,
  });
  const catId = cat.id;

  const grp = await postJson(adminRequest, "/api/v4/admin/item/group", {
    name: `E2E Grp ${uniq}`,
    description: "E2E group",
    parent_category: catId,
  });
  const groupId = grp.id;

  const username = `e2e_brand_mgr_${uniq}`;
  await postJson(adminRequest, "/api/v4/admin/item/user", {
    username,
    name: `E2E Brand Mgr ${uniq}`,
    email: `${username}@example.test`,
    password: STRONG_PWD,
    provider: "local",
    bulk: false,
    role: "manager",
    category: catId,
    group: groupId,
  });

  return {
    catId,
    catName,
    manager: { username, password: STRONG_PWD, category: catId },
    categories: {
      [catId]: {
        id: catId,
        name: catName,
        url: customUrl,
        frontend: false,
        maintenance: false,
      },
    },
  };
}

export async function cleanupManagerCategory(adminRequest, handles) {
  if (!handles || !handles.catId) return;
  await adminRequest
    .delete(`/api/v4/admin/item/category/${handles.catId}`)
    .catch(() => {});
}

// Log the provisioned manager in on a fresh context and bridge the admin
// session so `/isard-admin` is reachable. Caller closes the context.
export async function loginProvisionedManager(
  browser,
  loginHelpers,
  bridgeAdminSession,
  handles,
) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await loginHelpers.login(page, handles.manager, handles.categories);
  await bridgeAdminSession(page);
  return { context, page };
}

export async function expandCategoryRow(page, categoryName) {
  await page.goto(MGMT_URL);
  await page
    .locator("#users tbody tr")
    .first()
    .waitFor({ state: "visible", timeout: 20000 })
    .catch(() => {});
  const catTab = page
    .locator('[href="#categories"], button:has-text("Categories")')
    .first();
  if ((await catTab.count()) > 0) await catTab.click();
  await page
    .locator("#categories tbody tr")
    .first()
    .waitFor({ state: "visible", timeout: 15000 })
    .catch(() => {});
  const expandBtn = page
    .locator("#categories tbody tr", { hasText: categoryName })
    .first()
    .locator("td.details-show button");
  await expandBtn.waitFor({ state: "visible", timeout: 15000 });
  await expandBtn.click();
}
