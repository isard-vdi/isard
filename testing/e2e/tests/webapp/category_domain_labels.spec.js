// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The category admin now distinguishes the web portal domain from the bastion
// domain and tells the truth about what each serves. Asserts the renamed
// labels and the DNS clarifications in the bastion and branding modals, for
// admin and manager (manager has the branding permission; the bastion domain
// is editable by any manager). The verificationRequired and dead-selector
// fixes (P9/P12) are pinned by the webapp-js unit test on this branch.

import { test, expect } from "../../fixtures/login.js";

const MGMT_URL = "/isard-admin/admin/users/Management";

async function expandDefaultCategory(page) {
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
    .locator("#categories tbody tr", { hasText: "Default" })
    .first()
    .locator("td.details-show button");
  await expandBtn.waitFor({ state: "visible", timeout: 15000 });
  await expandBtn.click();
}

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
  test("admin sees portal/bastion labels and the DNS clarifications", async ({
    authenticatedPage: page,
  }) => {
    await expandDefaultCategory(page);
    await assertBastionModal(page, "admin-bastion-labels.png");
    await expandDefaultCategory(page);
    await assertBrandingModal(page, "admin-branding-labels.png");
  });

  test("manager sees portal/bastion labels and the DNS clarifications", async ({
    managerE2EPage: page,
  }) => {
    await expandDefaultCategory(page);
    await assertBastionModal(page, "manager-bastion-labels.png");
    await expandDefaultCategory(page);
    await assertBrandingModal(page, "manager-branding-labels.png");
  });
});
