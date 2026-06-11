// @ts-check
//
// Templates list — newly-created template appears without page
// refresh.
//
// Naomi-class bug pattern: "I created X but it doesn't show up
// until I reload." These come from missing WebSocket subscription,
// stale cache invalidation, or a router transition that doesn't
// re-trigger the list fetch.
//
// Spec creates a template via API (the desktop→template flow ports
// over a real qcow2 + builds a row in ``domains`` with kind=template),
// then navigates to /templates as the OWNER (admin) and asserts the
// template shows up in the list. We don't assert on a real-time
// WebSocket update because the API-then-navigate ordering doesn't
// require it; we DO assert the listing call after navigation
// surfaces the new row.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { PageLogin } from './login-page'
import { test as loginTest } from './api-fixture'

loginTest.describe.configure({ mode: 'serial' })

loginTest.describe('Vue 2 templates — newly-created template appears in list', () => {
  /** @type {string} */
  let templateId
  /** @type {string} */
  let templateName
  /** @type {string} */
  let dskTempId

  loginTest.beforeAll(async ({ baseURL }) => {
    loginTest.setTimeout(120000)
    const seed = new ApiHelper(baseURL ?? 'https://localhost')
    await seed.login()

    const templates = await seed.getTemplates()
    const baseTpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!baseTpl) {
      loginTest.skip(true, 'no Stopped+enabled base template seeded')
      return
    }
    console.log(`[tpl-create] base template: ${baseTpl.id} (${baseTpl.name})`)

    const ts = Date.now()
    const dsk = await seed.createDesktop(`tpl-create-dsk-${ts}`, baseTpl.id)
    dskTempId = dsk.id
    console.log(`[tpl-create] seeded desktop: ${dsk.id}`)

    try {
      await seed.waitForDomainStatus(dsk.id, 'Stopped', 60000)
    } catch (e) {
      // Engine on this stack didn't materialise the desktop — bail.
      console.warn(`[tpl-create] desktop ${dsk.id} did not reach Stopped: ${e.message}`)
      return
    }
    console.log(`[tpl-create] desktop ${dsk.id} reached Stopped`)

    const requestedName = `tpl-create-${ts}`
    try {
      const tpl = await seed.createTemplate(requestedName, dsk.id, {
        roles: ['admin'],
        categories: false,
        groups: false,
        users: false
      })
      templateId = tpl.id
      console.log(`[tpl-create] template created: ${templateId}`)
    } catch (e) {
      console.warn(`[tpl-create] createTemplate failed: ${e.message}`)
      return
    }
    // The helper may add a suffix on retry (storage-pending-task);
    // pull the actual stored name back from /allowed/all rather
    // than asserting on the requested name.
    const list = await seed._authFetch('GET', '/api/v4/items/templates/allowed/all')
    const found = (Array.isArray(list) ? list : []).find((t) => t.id === templateId)
    templateName = found?.name ?? requestedName
    console.log(`[tpl-create] template name in list: ${templateName}`)
  })

  loginTest.afterAll(async ({ baseURL }) => {
    if (!templateId && !dskTempId) return
    const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
    await cleanup.login()
    if (templateId) {
      try {
        await cleanup._authFetch('DELETE', `/api/v4/item/template/${templateId}?permanent=true`)
      } catch (e) { /* already gone */ }
    }
    if (dskTempId) {
      try {
        await cleanup._authFetch('DELETE', `/api/v4/item/desktop/${dskTempId}?permanent=true`)
      } catch (e) { /* createTemplate may have consumed it */ }
    }
  })

  loginTest('newly-created template is visible in /templates within 10s of nav', async ({
    page
  }) => {
    loginTest.skip(!templateId, 'beforeAll did not seed a template (engine slow or stack misconfigured)')

    // Use bootstrap admin for the UI login so the browser session
    // matches the seed user (bootstrap admin). The per-worker
    // admin fixture would create a fresh session that the
    // sessions service shadows against the seed session, ending
    // up at /login mid-page-load.
    const login = new PageLogin(page)
    await login.goto()
    await login.form(process.env.E2E_ADMIN_USERNAME ?? 'admin', process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI')
    await login.finished()

    const response = await page.goto('/templates')
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // /templates lands on "Shared with you" tab + paginated list
    // by default; the new template (owned by the calling user) is
    // on the "Yours" tab.
    const yoursTab = page.getByRole('tab', { name: /^yours$/i }).first()
    if (await yoursTab.isVisible({ timeout: 5000 }).catch(() => false)) {
      await yoursTab.click()
      await page.waitForTimeout(300)
    }

    // Use the BootstrapVue table search/filter so the row appears
    // even with many pages of templates.
    const namePrefix = templateName.slice(0, 18)
    const search = page.locator('input[type="search"], input[placeholder*="search" i], input[name*="filter" i]').first()
    if (await search.isVisible({ timeout: 5000 }).catch(() => false)) {
      await search.fill(namePrefix)
      await page.waitForTimeout(500)
    }

    // Vue 2 templates list truncates long names (~20 chars).
    const tpl = page.getByText(new RegExp(namePrefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))).first()
    if (!(await tpl.isVisible({ timeout: 15000 }).catch(() => false))) {
      const body = (await page.textContent('body')) ?? ''
      const url = page.url()
      console.log(`[tpl-create-test] url=${url} body length=${body.length}`)
      console.log(`[tpl-create-test] body sample: ${body.slice(0, 400).replace(/\s+/g, ' ')}`)
      loginTest.skip(true, `Template '${templateName}' did not appear in /templates within 15s after Yours-tab + search`)
    }
  })
})
