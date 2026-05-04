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
import { test as loginTest } from './login-page'

loginTest.describe.configure({ mode: 'serial' })

loginTest.describe('Vue 2 templates — newly-created template appears in list', () => {
  /** @type {ApiHelper} */
  let api
  /** @type {string} */
  let templateId
  /** @type {string} */
  let templateName
  /** @type {string} */
  let dskTempId

  loginTest.beforeAll(async ({ baseURL }) => {
    api = new ApiHelper(baseURL ?? 'https://localhost')
    await api.login()

    const templates = await api.getTemplates()
    const baseTpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!baseTpl) {
      loginTest.skip(true, 'no Stopped+enabled base template seeded')
      return
    }

    const ts = Date.now()
    const dsk = await api.createDesktop(`tpl-create-dsk-${ts}`, baseTpl.id)
    dskTempId = dsk.id

    try {
      await api.waitForDomainStatus(dsk.id, 'Stopped', 60000)
    } catch (e) {
      console.warn(`desktop ${dsk.id} did not reach Stopped: ${e.message}`)
    }

    templateName = `tpl-create-${ts}`
    const tpl = await api.createTemplate(templateName, dsk.id, {
      roles: ['admin'],
      categories: false,
      groups: false,
      users: false
    })
    templateId = tpl.id
  })

  loginTest.afterAll(async () => {
    if (templateId) {
      try {
        await api._authFetch('DELETE', `/api/v4/item/template/${templateId}?permanent=true`)
      } catch (e) { /* already gone */ }
    }
    if (dskTempId) {
      try {
        await api._authFetch('DELETE', `/api/v4/item/desktop/${dskTempId}?permanent=true`)
      } catch (e) { /* createTemplate may have consumed it */ }
    }
  })

  loginTest('newly-created template is visible in /templates within 10s of nav', async ({
    page,
    login
  }) => {
    loginTest.skip(!templateId, 'beforeAll did not seed a template')

    const response = await page.goto('/templates')
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // The Templates page renders templates as cards or rows depending
    // on the view mode. Search by visible text — the template name
    // is the most reliable anchor.
    const tpl = page.getByText(templateName).first()
    await expect(
      tpl,
      `Template '${templateName}' was created via API ` +
      '(POST /item/template) but not visible in /templates list. ' +
      'Likely cause: stale cache, missing WS subscription, or list ' +
      'endpoint pluck dropped the field that maps to the row title.'
    ).toBeVisible({ timeout: 10000 })
  })
})
