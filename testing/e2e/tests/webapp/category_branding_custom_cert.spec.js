// SPDX-License-Identifier: AGPL-3.0-or-later
//
// A category whose web-portal branding uses a custom certificate source but
// has no certificate must not save: the backend rejects it (instead of
// silently falling through to ACME), and the webapp shows a persistent error
// notice (it no longer auto-dismisses after 5s). Admin and manager (the
// manager holds the branding permission).
//
// Precondition: the `default` category's branding is pre-set to
// {domain: {enabled: true, certificate_source: "custom"}} with NO certificate
// — a state the API itself refuses to create (that is the fix), so it is
// seeded out-of-band (DB fixture) for this spec.
//
// The ACME-failure rollback (P6) is covered by the apiv4 service tests; it
// cannot be driven from a browser (real acme.sh, up to 10 minutes).

import { test, expect } from "../../fixtures/login.js";

const MGMT_URL = "/isard-admin/admin/users/Management";

async function saveBrandingAndExpectRejection(page, shot) {
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
  await page.locator(".btn-branding").first().click();
  await page
    .locator("div#modal-branding")
    .waitFor({ state: "visible", timeout: 8000 });
  await page.waitForTimeout(800); // let the branding GET populate the form
  await page.locator("div#modal-branding #send").click();

  // The save is rejected and the error notice names the missing certificate.
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
  test("admin: custom certificate source without a file is rejected and persists", async ({
    authenticatedPage: page,
  }) => {
    await saveBrandingAndExpectRejection(page, "admin-branding-custom-nocert.png");
  });

  test("manager: same rejection via the branding modal", async ({
    managerE2EPage: page,
  }) => {
    await saveBrandingAndExpectRejection(
      page,
      "manager-branding-custom-nocert.png",
    );
  });
});
