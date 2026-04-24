// @ts-check
//
// Vue 2 deployments smoke. /deployments lists the admin/advanced
// user's deployments, /deployments/new is the stepper. Vue 3 also has
// these, but Vue 2 is the live production surface — pin it.

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 deployments', () => {
  test('/deployments list page loads without i18n leaks', async ({ page, login }) => {
    const response = await page.goto('/deployments')
    if (response) expect(response.status()).toBeLessThan(400)

    await expect(page.locator('#content')).toBeVisible()
    const body = (await page.textContent('body')) ?? ''
    expect(body).not.toMatch(/views\.deployments\./)
  })

  test('/deployments shows either the empty-state message or a table', async ({ page, login }) => {
    await page.goto('/deployments')
    await page.waitForLoadState('networkidle')

    const hasTable = await page
      .locator('table, [role="table"]')
      .first()
      .isVisible({ timeout: 5000 })
      .catch(() => false)
    const hasEmpty = await page
      .getByRole('heading')
      .filter({ hasText: /deployment/i })
      .first()
      .isVisible({ timeout: 2000 })
      .catch(() => false)
    expect(hasTable || hasEmpty).toBeTruthy()
  })

  test('/deployments/new loads the stepper shell', async ({ page, login }) => {
    const response = await page.goto('/deployments/new')
    if (response) expect(response.status()).toBeLessThan(400)
    // DeploymentNew.vue wraps in `.main-container`, not `#content`.
    await expect(page.locator('.main-container')).toBeVisible()
    await expect(page.getByRole('heading', { level: 4 }).first()).toBeVisible()
  })
})
