// @ts-check
//
// Vue 2 resource-planner smoke. /planning is Vue-2-only today — admins
// manage GPU / reservables planning from the legacy frontend.

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 planning', () => {
  test('/planning renders the calendar shell', async ({ page, login }) => {
    const response = await page.goto('/planning')
    if (response) expect(response.status()).toBeLessThan(400)

    // The two mandatory selectors rendered by src/pages/Planning.vue top.
    // If the Vue-i18n store isn't ready, the <h5> labels show the key.
    const bookableType = page.getByRole('heading', { level: 5 }).first()
    await expect(bookableType).toBeVisible()
    await expect(bookableType).not.toHaveText(/components\./)
  })

  test('/planning title does not leak the i18n key', async ({ page, login }) => {
    await page.goto('/planning')
    const title = await page.title()
    expect(title).not.toMatch(/^router\./)
  })
})
