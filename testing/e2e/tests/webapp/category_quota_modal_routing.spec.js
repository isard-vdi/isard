// SPDX-License-Identifier: AGPL-3.0-or-later
//
// On the quotas/limits page expanding a category or a group row rebinds
// #modalEditQuota #send, so the last-expanded row's handler used to win: with a
// category row open, expanding a group then saving the category quota went to
// PUT /admin/item/quota/group/<category id>. The save must route by the row
// that opened the modal. Admin creates an isolated category + group and cleans
// them up afterEach.

import { test, expect } from "../../fixtures/login.js";
import {
  provisionCategoryWithGroup,
  cleanupManagerCategory,
} from "../../fixtures/category_provision.js";

const QUOTAS_URL = "/isard-admin/admin/users/QuotasLimits";

// DataTables paginates at 10 by default, so a freshly created row may render on
// a later page; bump the length to All (or the largest option) before matching.
async function showAll(page, tableId) {
  const sel = page.locator(`#${tableId}_length select`).first();
  if ((await sel.count()) === 0) return;
  const values = await sel
    .locator("option")
    .evaluateAll((os) => os.map((o) => o.value));
  const pick = values.includes("-1")
    ? "-1"
    : values.filter((v) => !Number.isNaN(+v)).sort((a, b) => +b - +a)[0];
  if (pick) await sel.selectOption(pick).catch(() => {});
  await page.waitForTimeout(500);
}

async function expandRow(page, tableId, name) {
  await page
    .locator(`#${tableId} tbody tr`)
    .first()
    .waitFor({ state: "visible", timeout: 15000 })
    .catch(() => {});
  await showAll(page, tableId);
  const row = page
    .locator(`#${tableId} tbody tr`, { hasText: name })
    .first();
  await row.waitFor({ state: "visible", timeout: 15000 });
  await row.locator("td.details-show button").click();
}

test.describe("category quota modal routing", () => {
  let cleanups;
  test.beforeEach(() => {
    cleanups = [];
  });
  test.afterEach(async () => {
    for (const fn of cleanups.reverse()) await fn().catch(() => {});
  });

  test("admin: saving a category quota after opening a group routes to the category", async ({
    authenticatedPage: page,
  }, testInfo) => {
    const h = await provisionCategoryWithGroup(page.request, {
      suffix: `w${testInfo.workerIndex}`,
    });
    cleanups.push(() => cleanupManagerCategory(page.request, h));

    const before = await (
      await page.request.get(`/api/v4/admin/item/category/${h.catId}`)
    ).json();
    expect(before.quota, "new category starts with unlimited quota").toBe(false);

    await page.goto(QUOTAS_URL);
    // Expand the category row (binds the category save handler), then the group
    // row (rebinds it to the group one) while the category row stays expanded —
    // the state in which the category-quota save used to be misrouted.
    await expandRow(page, "categories", h.catName);
    await expandRow(page, "groups", h.groupName);

    // Edit the still-open category's quota and save a (limited) quota.
    await page.locator(".btn-edit-category-quotas").first().click();
    await page
      .locator("#modalEditQuota")
      .waitFor({ state: "visible", timeout: 8000 });
    await page.waitForTimeout(500);
    await page.evaluate(() =>
      window.$("#modalEditQuota #unlimited").iCheck("uncheck"),
    );

    const putResp = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v4/admin/item/quota/") &&
        r.request().method() === "PUT",
      { timeout: 20000 },
    );
    await page.locator("#modalEditQuota #send").click();
    const resp = await putResp;
    await page
      .screenshot({
        path: testInfo.outputPath("admin-category-quota-save.png"),
        fullPage: true,
      })
      .catch(() => {});

    expect(
      resp.url(),
      "the save must go to the category quota route, not the group one",
    ).toContain(`/api/v4/admin/item/quota/category/${h.catId}`);
    expect(resp.ok(), "category quota save succeeds").toBeTruthy();

    const after = await (
      await page.request.get(`/api/v4/admin/item/category/${h.catId}`)
    ).json();
    expect(
      after.quota,
      "a limited quota is now stored on the category",
    ).not.toBe(false);
  });
});
