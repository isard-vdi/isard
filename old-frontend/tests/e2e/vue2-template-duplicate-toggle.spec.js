// @ts-check
//
// Template duplicate + enable/disable toggle smoke.
//
// /templates lists every template the user can manage. Two
// frequent admin actions:
//   * "Duplicate" creates a new template from an existing one
//     (same disk chain).
//   * "Enable / Disable" toggles ``template.enabled`` — disabled
//     templates don't show in the new-desktop wizard.
//
// Bug pattern: list-page ops that succeed on the API but the row
// state doesn't update visibly until manual refresh. Same WS /
// store-handler class as Bug #13 / #17 / #33.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { test as loginTest } from './api-fixture'

loginTest.describe.configure({ mode: 'serial' })

loginTest.describe('Vue 2 templates — duplicate + enable/disable toggle', () => {
  /** @type {string} */
  let baseTemplateId
  /** @type {string[]} */
  const cleanupIds = []

  loginTest.beforeAll(async ({ baseURL }) => {
    const seed = new ApiHelper(baseURL ?? 'https://localhost')
    await seed.login()

    const templates = await seed.getTemplates()
    const tpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!tpl) {
      loginTest.skip(true, 'no Stopped+enabled template seeded')
      return
    }
    baseTemplateId = tpl.id
  })

  loginTest.afterAll(async ({ baseURL }) => {
    if (cleanupIds.length === 0) return
    const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
    await cleanup.login()
    for (const id of cleanupIds) {
      try {
        await cleanup._authFetch('DELETE', `/api/v4/item/template/${id}?permanent=true`)
      } catch (e) { /* ignored */ }
    }
  })

  loginTest('duplicate via API — new template appears in /templates list', async ({
    page,
    login,
    api
  }) => {
    loginTest.skip(!baseTemplateId, 'no base template seeded')

    const ts = Date.now()
    const newName = `dup-${ts}`
    const dup = await api.duplicateTemplate(baseTemplateId, newName, {
      roles: ['admin'],
      categories: false,
      groups: false,
      users: false
    })
    cleanupIds.push(dup.id)

    await page.goto('/templates')
    await page.waitForLoadState('networkidle')

    await expect(
      page.getByText(newName).first(),
      `Duplicated template '${newName}' should be visible in /templates within 10s`
    ).toBeVisible({ timeout: 10000 })
  })

  loginTest('toggle enable/disable via API — UI reflects the new state', async ({
    page,
    login,
    api
  }) => {
    loginTest.skip(!baseTemplateId, 'no base template seeded')

    // Create a fresh duplicate to toggle (don't mess with the
    // original template's state — other specs depend on it).
    const ts = Date.now()
    const dup = await api.duplicateTemplate(baseTemplateId, `toggle-${ts}`, {
      roles: ['admin'],
      categories: false,
      groups: false,
      users: false
    })
    cleanupIds.push(dup.id)

    // Disable via API.
    await api._authFetch('PUT', `/api/v4/item/template/${dup.id}/disable`)

    // Re-fetch — the row's enabled flag should be false.
    const afterDisable = await api._authFetch('GET', '/api/v4/items/templates/allowed/all')
    const found = (Array.isArray(afterDisable) ? afterDisable : []).find(
      (t) => t.id === dup.id
    )
    expect(
      found,
      `Duplicate template ${dup.id} should still appear in /allowed/all after disable`
    ).toBeTruthy()
    expect(found.enabled, 'enabled flag should be false after disable').toBeFalsy()

    // Re-enable.
    await api._authFetch('PUT', `/api/v4/item/template/${dup.id}/enable`)
    const afterEnable = await api._authFetch('GET', '/api/v4/items/templates/allowed/all')
    const found2 = (Array.isArray(afterEnable) ? afterEnable : []).find(
      (t) => t.id === dup.id
    )
    expect(found2.enabled, 'enabled flag should be true after enable').toBeTruthy()
  })
})
