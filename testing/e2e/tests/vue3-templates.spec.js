import { test, expect } from '../fixtures/login.js'
import { commonHelpers } from '../fixtures/common.js'

const templatesURL = '/frontend/templates'
const newTemplateURL = '/frontend/templates/new'

test.describe('Vue 3 Templates view', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories, templatesURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    expect(page.url()).toContain(templatesURL)
  })

  test('list page loads without router errors', async ({ page }) => {
    await commonHelpers.checkNoRouterErrors(page)
    // Page heading should match i18n key — router title is "Templates"
    const title = await page.title()
    expect(title).not.toContain('router.titles')
  })

  test('renders the user / shared tab toggle', async ({ page }) => {
    // The templates view has a tab/toggle between user-owned and shared.
    // One of these tabs must be visible (i18n-localized text varies).
    const tabs = page.getByRole('tab').or(page.locator('button[role="tab"]'))
    await expect(tabs.first()).toBeVisible({ timeout: 10000 })
  })

  test('navigates to new-template via direct URL', async ({ page }) => {
    await page.goto(newTemplateURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    expect(page.url()).toContain(newTemplateURL)
    await commonHelpers.checkNoRouterErrors(page)
  })
})
