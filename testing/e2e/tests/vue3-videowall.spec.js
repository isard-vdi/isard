import { test, expect } from '../fixtures/login.js'
import { commonHelpers } from '../fixtures/common.js'

// Smoke + chrome-controls coverage for the Vue 3
// /frontend/deployments/:deploymentId/videowall route.
//
// Targets the seeded "deployment-test-001" deployment from
// /opt/isard/src/testing/db/data/deployments.json so the page actually
// resolves with data instead of redirecting on a missing-deployment
// fetch error.
//
// What we pin (single-page level — does NOT cover the noVNC stream):
//   1. The route resolves (no router.titles fallback in <title>)
//   2. Filter input + only-started checkbox + grid/single buttons
//      + back-to-deployment button render
//   3. The GPU-warning info banner is visible (regression guard for
//      a future i18n-key drop or layout change that hides it)
//
// noVNC viewer testing is intentionally skipped — it requires a live
// hypervisor + spice/vnc backend which the e2e stack doesn't provide.

const DEPLOYMENT_ID = 'deployment-test-001'
const VIDEOWALL_URL = `/frontend/deployments/${DEPLOYMENT_ID}/videowall`

test.describe('Vue 3 Deployment Videowall view', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories, VIDEOWALL_URL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    expect(page.url()).toContain(VIDEOWALL_URL)
  })

  test('loads without router errors and stays on the page', async ({ page }) => {
    await commonHelpers.checkNoRouterErrors(page)
    expect(page.url()).toContain(VIDEOWALL_URL)
    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)
  })

  test('chrome controls render: filter, only-started toggle, view switchers, back', async ({
    page,
  }) => {
    // Filter input (placeholder is i18n-driven so we match by role).
    const filter = page.getByRole('textbox').first()
    await expect(filter).toBeVisible({ timeout: 10000 })

    // Only-started checkbox (Checkbox component renders role="checkbox").
    const onlyStarted = page.getByRole('checkbox').first()
    await expect(onlyStarted).toBeVisible({ timeout: 5000 })

    // Grid + single view-mode buttons (icon-only, identified by aria-label).
    // The i18n keys `views.deployment-videowall.view.grid` /
    // `views.deployment-videowall.view.single` resolve to "Grid view"
    // and "Full view" in en-US — match by the actual rendered words,
    // not the i18n key suffix.
    const gridBtn = page.locator('button[aria-label*="grid" i]').first()
    const singleBtn = page.locator('button[aria-label*="full" i]').first()
    await expect(gridBtn).toBeVisible({ timeout: 5000 })
    await expect(singleBtn).toBeVisible({ timeout: 5000 })

    // Back-to-deployment button — pin so a future header refactor that
    // drops the back-link doesn't strand admins on the videowall.
    const backBtn = page
      .getByRole('button', { name: /back|tornar|atrás/i })
      .first()
    await expect(backBtn).toBeVisible({ timeout: 5000 })
  })

  test('GPU warning info banner is visible', async ({ page }) => {
    // The banner uses an Info icon + i18n text. Match by the banner's
    // distinctive blue background classes since the icon is decorative.
    const banner = page
      .locator('div.bg-blue-50, [role="alert"]:has(svg)')
      .first()
    await expect(banner).toBeVisible({ timeout: 5000 })
  })

  test('grid view is the default view mode', async ({ page }) => {
    // The grid button is `disabled` when grid mode is active (per
    // DeploymentVideowallView.vue). Pin the default landing mode so a
    // future change to default=single is intentional.
    const gridBtn = page.locator('button[aria-label*="grid" i]').first()
    await expect(gridBtn).toBeDisabled({ timeout: 5000 })
  })

  test('back-to-deployment navigates to the deployment view', async ({
    page,
  }) => {
    const backBtn = page
      .getByRole('button', { name: /back|tornar|atrás/i })
      .first()
    await backBtn.click()
    await page.waitForURL(`**/deployments/${DEPLOYMENT_ID}`, {
      timeout: 10000,
    })
    expect(page.url()).toContain(`/deployments/${DEPLOYMENT_ID}`)
    expect(page.url()).not.toContain('/videowall')
  })
})
