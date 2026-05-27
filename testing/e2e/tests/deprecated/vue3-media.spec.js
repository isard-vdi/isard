import { test, expect } from '../../fixtures/login.js'
import { commonHelpers } from '../../fixtures/common.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')

const mediaURL = '/frontend/media'

test.describe('Vue 3 Media view', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories, mediaURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    expect(page.url()).toContain(mediaURL)
  })

  test('loads without router errors', async ({ page }) => {
    await commonHelpers.checkNoRouterErrors(page)
  })

  test('user / shared tabs are visible', async ({ page }) => {
    const tabs = page.getByRole('tab').or(page.locator('button[role="tab"]'))
    await expect(tabs.first()).toBeVisible({ timeout: 10000 })
  })

  test('new-media control is reachable for admin', async ({ page }) => {
    // Admins can add media — a "new" / "add" / "download" button should show.
    const newBtn = page
      .getByRole('button', { name: /new|add|download|\+/i })
      .first()
    await expect(newBtn).toBeVisible({ timeout: 10000 })
  })
})
