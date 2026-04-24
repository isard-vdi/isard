import { test, expect } from '../fixtures/login.js'
import { commonHelpers } from '../fixtures/common.js'

const profileURL = '/frontend/profile'

test.describe('Vue 3 Profile view', () => {
  test.beforeEach(async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.login(page, users.admin, categories, profileURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    expect(page.url()).toContain(profileURL)
  })

  test('renders user details section without errors', async ({ page }) => {
    await commonHelpers.checkNoRouterErrors(page)
    // Avatar, user name, role, and category should be present
    await expect(page.locator('img, [role="img"]').first()).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(/admin/i).first()).toBeVisible({ timeout: 10000 })
  })

  test('change-password button opens the password modal', async ({ page }) => {
    const btn = page.getByRole('button', { name: /password|change password/i }).first()
    await btn.waitFor({ state: 'visible', timeout: 10000 })
    await btn.click()

    const modal = page.getByRole('dialog').filter({ hasText: /password/i }).first()
    await expect(modal).toBeVisible({ timeout: 5000 })

    // At least one password input must render inside the modal
    const pwInputs = modal.locator('input[type="password"]')
    await expect(pwInputs.first()).toBeVisible({ timeout: 5000 })
  })

  test('api-key section is accessible for admin', async ({ page }) => {
    // The profile view has an API keys section — we don't mutate, just confirm
    // an action button is reachable.
    const apiKeyBtn = page.getByRole('button', { name: /api[- ]?key/i }).first()
    await expect(apiKeyBtn).toBeVisible({ timeout: 10000 })
  })

  test('no fatal console errors on load', async ({ page }) => {
    const errors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
    })
    await page.reload()
    await page.waitForLoadState('networkidle', { timeout: 15000 })

    const fatal = errors.filter(
      (e) =>
        !e.includes('Failed to load resource') &&
        !e.includes('favicon') &&
        !e.includes('socket.io') &&
        !e.includes('net::ERR_FAILED'),
    )
    expect(fatal, `Unexpected errors:\n${fatal.join('\n')}`).toHaveLength(0)
  })
})
