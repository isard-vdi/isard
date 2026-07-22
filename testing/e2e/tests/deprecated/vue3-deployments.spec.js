import { test, expect } from '../../fixtures/login.js'
import { commonHelpers } from '../../fixtures/common.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')

const deploymentsURL = '/frontend/deployments'
const newDeploymentURL = '/frontend/deployments/new'

test.describe('Vue 3 Deployments view', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories, deploymentsURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    expect(page.url()).toContain(deploymentsURL)
  })

  test('list page loads without router errors', async ({ page }) => {
    await commonHelpers.checkNoRouterErrors(page)
    const title = await page.title()
    expect(title).not.toContain('router.titles')
  })

  test('direct navigation to /new renders the stepper form', async ({ page }) => {
    await page.goto(newDeploymentURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    expect(page.url()).toContain(newDeploymentURL)
    await commonHelpers.checkNoRouterErrors(page)

    // The NewDeploymentView uses a multi-step stepper — at least one input
    // or a "next" style button should be visible as the first step.
    const anyInput = page.locator('input, [role="combobox"], [role="textbox"]').first()
    await expect(anyInput).toBeVisible({ timeout: 10000 })
  })

  test('user role is required (admin reaches the page)', async ({ page }) => {
    // Admin should NOT be bounced to /error/403 or redirected to /login.
    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)
    expect(page.url()).not.toContain('/error/')
  })
})
