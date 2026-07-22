// @ts-check
//
// Vue 2 user storage smoke. /userstorage is Vue-2-only — per-user quota
// + disk usage breakdown. Feeds off apiv4 `GET /item/users/{id}/desktops`
// + `GET /item/users/{id}/storages` via a thin Vuex module.

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 user storage', () => {
  test('/userstorage renders either the no-storage message or the table', async ({ page, login }) => {
    const response = await page.goto('/userstorage')
    if (response) expect(response.status()).toBeLessThan(400)

    // src/pages/Storage.vue renders one of two shapes depending on the
    // authenticated user's storage count. Either is valid.
    await expect(page.locator('#content')).toBeVisible()

    // Pin against an obvious i18n break: if the view rendered the
    // untranslated key, something upstream (locale init, store wiring)
    // is broken.
    const body = await page.textContent('body')
    expect(body ?? '').not.toMatch(/views\.storage\./)
  })

  test('/userstorage title does not leak the i18n key', async ({ page, login }) => {
    await page.goto('/userstorage')
    const title = await page.title()
    expect(title).not.toMatch(/^router\./)
  })
})
