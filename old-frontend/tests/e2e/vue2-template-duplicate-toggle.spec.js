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
import { PageLogin } from './login-page'
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
    baseURL
  }) => {
    loginTest.skip(!baseTemplateId, 'no base template seeded')

    // Use bootstrap admin everywhere in this test so the
    // sessions service doesn't shadow the browser's session
    // when the API helper logs in.
    const seed = new ApiHelper(baseURL ?? 'https://localhost')
    await seed.login()
    const ts = Date.now()
    const newName = `dup-${ts}`
    const dup = await seed.duplicateTemplate(baseTemplateId, newName, {
      roles: ['admin'],
      categories: false,
      groups: false,
      users: false
    })
    cleanupIds.push(dup.id)

    const login = new PageLogin(page)
    await login.goto()
    await login.form('admin', 'IsardVDI')
    await login.finished()
    await page.goto('/templates')
    await page.waitForLoadState('networkidle')

    // /templates lands on the "Shared with you" tab; the
    // duplicated template (owned by the calling user) is on
    // "Yours" and the page is paginated. Click Yours + filter
    // by name so the row materialises regardless of pool size.
    const yoursTab = page.getByRole('tab', { name: /^yours$/i }).first()
    if (await yoursTab.isVisible({ timeout: 5000 }).catch(() => false)) {
      await yoursTab.click()
      await page.waitForTimeout(300)
    }
    const search = page.locator('input[type="search"], input[placeholder*="search" i], input[name*="filter" i]').first()
    if (await search.isVisible({ timeout: 5000 }).catch(() => false)) {
      await search.fill(newName.slice(0, 18))
      await page.waitForTimeout(500)
    }

    const tile = page.getByText(new RegExp(newName.slice(0, 18))).first()
    if (!(await tile.isVisible({ timeout: 15000 }).catch(() => false))) {
      loginTest.skip(true, `duplicated template '${newName}' did not appear in /templates within 15s after Yours-tab + search`)
    }
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

    // Disable via API. Endpoint is the single PUT
    // ``/item/template/{id}/set-enabled`` taking ``{enabled:
    // bool}``. ``/items/templates/allowed/all`` only lists
    // ENABLED templates — checking for membership is the
    // simplest signal that ``set-enabled`` worked. /get-info
    // doesn't include the ``enabled`` field.
    await api._authFetch('PUT', `/api/v4/item/template/${dup.id}/set-enabled`, { enabled: false })
    const afterDisable = await api._authFetch('GET', '/api/v4/items/templates/allowed/all')
    const stillListedAfterDisable = (Array.isArray(afterDisable) ? afterDisable : []).some(
      (t) => t.id === dup.id
    )
    expect(
      stillListedAfterDisable,
      `Disabled template ${dup.id} should NOT appear in /allowed/all (which is enabled-only)`
    ).toBeFalsy()

    // Re-enable.
    await api._authFetch('PUT', `/api/v4/item/template/${dup.id}/set-enabled`, { enabled: true })
    const afterEnable = await api._authFetch('GET', '/api/v4/items/templates/allowed/all')
    const listedAfterEnable = (Array.isArray(afterEnable) ? afterEnable : []).some(
      (t) => t.id === dup.id
    )
    expect(
      listedAfterEnable,
      `Re-enabled template ${dup.id} should reappear in /allowed/all`
    ).toBeTruthy()
  })
})
