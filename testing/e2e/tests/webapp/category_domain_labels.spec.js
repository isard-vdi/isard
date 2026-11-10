// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The bastion and branding modals show the renamed portal/bastion labels and
// DNS clarifications, for admin (on `default`) and for a manager. The manager
// needs an isolated category (the branding button is permission-gated and racy
// to grant on shared `default`), created and torn down per test.

import { test, expect } from "../../fixtures/login.js";
import { bridgeAdminSession } from "../../fixtures/common.js";
import {
  provisionManagerCategory,
  cleanupManagerCategory,
  loginProvisionedManager,
  expandCategoryRow,
} from "../../fixtures/category_provision.js";

async function assertBastionModal(page, shot) {
  await page.locator(".btn-bastion-domain").first().click();
  const modal = page.locator("#modalBastionDomain");
  await modal.waitFor({ state: "visible", timeout: 8000 });
  await expect(modal.locator('label[for="bastion-domain"]')).toHaveText(
    "Bastion domain",
  );
  // The DNS alert text is in the DOM (hidden until a custom domain is chosen).
  await expect(modal).toContainText("only provides bastion access");
  await page
    .screenshot({ path: test.info().outputPath(shot), fullPage: true })
    .catch(() => {});
}

async function assertBrandingModal(page, shot) {
  await page.locator(".btn-branding").first().click();
  const modal = page.locator("div#modal-branding");
  await modal.waitFor({ state: "visible", timeout: 8000 });
  await expect(modal).toContainText("Web portal domain");
  await expect(modal).toContainText(
    "serves the web portal and its TLS certificate",
  );
  await page
    .screenshot({ path: test.info().outputPath(shot), fullPage: true })
    .catch(() => {});
}

test.describe("category domain labels and messages (P3/P4/P7)", () => {
  let cleanups;
  test.beforeEach(() => {
    cleanups = [];
  });
  test.afterEach(async () => {
    for (const fn of cleanups.reverse()) await fn().catch(() => {});
  });

  test("admin sees portal/bastion labels and the DNS clarifications", async ({
    authenticatedPage: page,
  }) => {
    await expandCategoryRow(page, "Default");
    await assertBastionModal(page, "admin-bastion-labels.png");
    await expandCategoryRow(page, "Default");
    await assertBrandingModal(page, "admin-branding-labels.png");
  });

  test("manager sees portal/bastion labels and the DNS clarifications", async ({
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
    await assertBastionModal(page, "manager-bastion-labels.png");
    await expandCategoryRow(page, handles.catName);
    await assertBrandingModal(page, "manager-branding-labels.png");
  });
});
