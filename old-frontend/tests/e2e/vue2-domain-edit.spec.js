// @ts-check
//
// Vue 2 desktop-edit smoke. `/domain/edit` is Vue-2-only — the advanced
// edit form for hardware, interfaces, media, boot order, viewers,
// bastion, bookables. The Vue 3 frontend has no equivalent yet.
//
// Without a target desktop, the SPA redirects back to /desktops rather
// than rendering an empty edit form. Pin the redirect + status so a
// future refactor can't accidentally leave the user on a blank page.

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 domain edit', () => {
  test('/domain/edit without a domain param redirects back to /desktops', async ({ page, login }) => {
    const response = await page.goto('/domain/edit')
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/desktops$/)
  })

  test('/domain/edit does not surface a router-title i18n key leak', async ({ page, login }) => {
    await page.goto('/domain/edit')
    await page.waitForLoadState('networkidle')
    const title = await page.title()
    expect(title).not.toMatch(/^router\./)
  })
})
