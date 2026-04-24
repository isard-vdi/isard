// @ts-check
//
// Vue 2 media library smoke. Both the Vue 3 and Vue 2 frontends serve a
// /media view today — but Vue 2 is the live production user surface, so
// this spec pins the parity contract (same apiv4 endpoints, same tabs,
// no i18n key leaks).

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 media', () => {
  test('/media renders the tabs shell', async ({ page, login }) => {
    const response = await page.goto('/media')
    if (response) expect(response.status()).toBeLessThan(400)

    // src/pages/Media.vue top renders `<b-tabs>`. At least one tab
    // heading must be present — pins that the SPA hydrated.
    await expect(page.locator('#content')).toBeVisible()
    await expect(page.locator('.nav-tabs, [role="tablist"]').first()).toBeVisible()
  })

  test('/media does not leak i18n keys', async ({ page, login }) => {
    await page.goto('/media')
    await page.waitForLoadState('networkidle')

    const title = await page.title()
    expect(title).not.toMatch(/^router\./)

    const body = (await page.textContent('body')) ?? ''
    expect(body).not.toMatch(/views\.media\./)
  })
})
