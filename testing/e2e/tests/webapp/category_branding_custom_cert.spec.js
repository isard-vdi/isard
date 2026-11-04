// SPDX-License-Identifier: AGPL-3.0-or-later
//
// A branding web-portal domain saved with a custom certificate source and no
// certificate file is rejected (400) with a persistent notice. Admin drives
// `default` (the rejected save persists nothing); the manager needs an isolated
// category (the branding permission is category-level and racy to grant on
// shared `default`), torn down afterEach.

import { test, expect } from "../../fixtures/login.js";
import { bridgeAdminSession } from "../../fixtures/common.js";
import {
  provisionManagerCategory,
  cleanupManagerCategory,
  loginProvisionedManager,
  expandCategoryRow,
} from "../../fixtures/category_provision.js";

async function saveBrandingCustomNoCertExpectRejection(page, shot) {
  await page.locator(".btn-branding").first().click();
  const modal = page.locator("div#modal-branding");
  await modal.waitFor({ state: "visible", timeout: 8000 });
  await page.waitForTimeout(500); // branding GET populates + handlers bind
  // iCheck-styled checkbox (real input opacity:0); its API also fires the
  // ifChanged that reveals the domain settings section.
  await page.evaluate(() =>
    window
      .$("#modal-branding #category-branding-domain-enabled")
      .iCheck("check"),
  );
  const nameField = modal.locator("#category-branding-domain-name");
  await nameField.waitFor({ state: "visible", timeout: 8000 });
  await nameField.fill("branding.example.com");
  await modal
    .locator("#category-branding-domain-certificate_source")
    .selectOption("custom");
  // No certificate file chosen — this is the combination the backend refuses.
  await modal.locator("#send").click();

  const errorNotice = page
    .locator(".ui-pnotify", { hasText: /certificate file/i })
    .first();
  await errorNotice.waitFor({ state: "visible", timeout: 15000 });
  await page
    .screenshot({ path: test.info().outputPath(shot), fullPage: true })
    .catch(() => {});
  // P6 UI: the error notice is sticky — still there after the old 5s auto-hide.
  await page.waitForTimeout(6000);
  await expect(errorNotice).toBeVisible();
}

test.describe("branding custom certificate rejection + persistent notice (P7/P6)", () => {
  let cleanups;
  test.beforeEach(() => {
    cleanups = [];
  });
  test.afterEach(async () => {
    for (const fn of cleanups.reverse()) await fn().catch(() => {});
  });

  test("admin: custom certificate source without a file is rejected and persists", async ({
    authenticatedPage: page,
  }) => {
    // The save is refused (400), so the shared `default` category is never
    // mutated — nothing to set up or tear down.
    await expandCategoryRow(page, "Default");
    await saveBrandingCustomNoCertExpectRejection(
      page,
      "admin-branding-custom-nocert.png",
    );
  });

  test("manager: same rejection via the branding modal", async ({
    browser,
    authenticatedPage,
    loginHelpers,
  }, testInfo) => {
    const handles = await provisionManagerCategory(authenticatedPage.request, {
      suffix: `w${testInfo.workerIndex}`,
      managerPermissions: { branding: true },
    });
    cleanups.push(() =>
      cleanupManagerCategory(authenticatedPage.request, handles),
    );
    const { context, page } = await loginProvisionedManager(
      browser,
      loginHelpers,
      bridgeAdminSession,
      handles,
    );
    cleanups.push(() => context.close());

    await expandCategoryRow(page, handles.catName);
    await saveBrandingCustomNoCertExpectRejection(
      page,
      "manager-branding-custom-nocert.png",
    );
  });
});
