// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Opening a category's Edit modal and saving without touching anything must
// not change its ephemeral-desktops setting or flip gpu_use_global_pool. On
// the unfixed backend the category detail GET omitted both fields, so the
// modal read them as absent and the no-touch save persisted the defaults
// (ephemeral off, use-global-pool on). Admin-only: the Edit button is not
// shown to managers.
//
// Route: PUT /api/v4/admin/item/category/{id}

import { test, expect } from "../../fixtures/login.js";

const MGMT_URL = "/isard-admin/admin/users/Management";
const CAT = "default";
const API = `/api/v4/admin/item/category/${CAT}`;
const EPHEMERAL = { minutes: 30, action: "Stopping" };

test.describe("category edit keeps unsent fields (P2)", () => {
  test("admin no-touch Edit save preserves ephemeral and GPU pool", async ({
    authenticatedPage: page,
  }) => {
    // Establish a non-default state the modal must round-trip: ephemeral
    // desktops enabled and the per-category (non-global) GPU pool.
    const setup = await page.request.put(API, {
      data: {
        id: CAT,
        name: "Default",
        ephimeral: EPHEMERAL,
        gpu_use_global_pool: false,
      },
    });
    expect(setup.ok(), `setup PUT status ${setup.status()}`).toBeTruthy();

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
    // Wait for the categories DataTable to render its rows before locating one.
    await page
      .locator("#categories tbody tr")
      .first()
      .waitFor({ state: "visible", timeout: 15000 })
      .catch(() => {});
    const expandBtn = page
      .locator("#categories tbody tr", { hasText: "Default" })
      .first()
      .locator("td.details-show button");
    await expandBtn.waitFor({ state: "visible", timeout: 15000 });
    await expandBtn.click();
    const editBtn = page.locator(".btn-edit-category").first();
    await editBtn.waitFor({ state: "visible", timeout: 10000 });
    await editBtn.click();
    await page
      .locator("#modalEditCategory")
      .waitFor({ state: "visible", timeout: 8000 });
    // Let the detail GET populate the form before saving.
    await page.waitForTimeout(1000);
    await page
      .screenshot({ path: test.info().outputPath("admin-edit-modal.png"), fullPage: true })
      .catch(() => {});

    const put = page.waitForResponse(
      (r) =>
        r.url().includes(`/admin/item/category/${CAT}`) &&
        r.request().method() === "PUT",
      { timeout: 20000 },
    );
    await page.locator("#modalEditCategory #send").click();
    await put;

    // The detail GET still returns the stored values; on the unfixed backend
    // it omits both (and the save had defaulted them), so this fails there.
    const got = await (await page.request.get(API)).json();
    expect(got.gpu_use_global_pool).toBe(false);
    expect(got.ephimeral).toEqual(EPHEMERAL);
  });
});
