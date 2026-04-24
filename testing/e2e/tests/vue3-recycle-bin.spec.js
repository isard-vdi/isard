import { test, expect } from '../fixtures/login.js'
import { commonHelpers } from '../fixtures/common.js'

const recycleBinURL = '/frontend/recycle-bin'

test.describe('Vue 3 Recycle Bin view', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories, recycleBinURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    expect(page.url()).toContain(recycleBinURL)
  })

  test('loads without router errors and keeps the user on the page', async ({ page }) => {
    await commonHelpers.checkNoRouterErrors(page)
    expect(page.url()).toContain(recycleBinURL)
    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)
  })

  test('empty state or table is rendered', async ({ page }) => {
    // Either a table is present (has entries) or an empty-state message shows.
    // Both keep the page valid — guard against a blank page.
    const hasTable = await page
      .locator('table, [role="table"], [role="grid"]')
      .first()
      .isVisible({ timeout: 5000 })
      .catch(() => false)
    const hasEmpty = await page
      .getByText(/empty|no items|no entries|nothing/i)
      .first()
      .isVisible({ timeout: 2000 })
      .catch(() => false)

    expect(hasTable || hasEmpty, 'Expected either a table or an empty-state message').toBe(true)
  })
})
