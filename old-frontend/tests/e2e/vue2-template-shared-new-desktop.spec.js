// @ts-check
//
// Regression for round-2 Bug #37 — owns_domain_id grants template
// access via shared alloweds.
//
// Old-frontend's new-desktop form calls
// ``GET /api/v4/item/desktop/{template_id}/get-info`` to render the
// template preview (the URL says "desktop" but the same handler
// serves both kinds — Vue 2 store gates on ``response.kind !==
// 'template'``). Before commit 1b18cfd05, ``Helpers.owns_domain_id``
// only walked desktop-ownership semantics; templates shared with the
// user via the alloweds mechanism were rejected with
// ``forbidden / not_enough_rights_desktop`` even though the
// template was explicitly shared with them.
//
// The fix added a final branch:
//   if domain.kind == 'template' and Alloweds.is_allowed(payload, domain, 'domains'):
//       return True
//
// Spec:
//   1. Admin (via API) creates a fresh advanced-role user.
//   2. Admin creates a desktop, stops it, builds a template from
//      it, shares the template with the user via ``allowed.users``.
//   3. UI logs in as the user.
//   4. Hits ``GET /item/desktop/{template_id}/get-info`` directly
//      with the user's token; asserts 200 (was 403 before fix).
//   5. afterAll deletes template + user.

import { test, expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { PageLogin } from './login-page'

test.describe.configure({ mode: 'serial' })

test.describe('Bug #37 — owns_domain_id template alloweds branch', () => {
  /** @type {ApiHelper} */
  let api
  /** @type {string} */
  let userId
  /** @type {string} */
  let userUsername
  const userPassword = 'shared1234'
  /** @type {string} */
  let templateId
  /** @type {string} */
  let dskTempId

  test.beforeAll(async ({ baseURL }) => {
    api = new ApiHelper(baseURL ?? 'https://localhost')
    await api.login()

    // Find a stock template to derive from. We need to make a
    // *new* template (via createDesktop + createTemplate) so we
    // control its ``allowed`` field — direct duplication of an
    // upstream template doesn't carry over the allowed list cleanly.
    const templates = await api.getTemplates()
    const baseTpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!baseTpl) {
      test.skip(true, 'no Stopped+enabled base template seeded')
      return
    }

    const ts = Date.now()
    userUsername = `bug37_${ts}`
    const userResp = await api.createUser(
      userUsername,
      'default',
      'default-default',
      'advanced',
      userPassword
    )
    userId = userResp.id

    // Create a Stopped desktop, then a template FROM it with the
    // ``allowed`` block scoped to the new user.
    const dsk = await api.createDesktop(`bug37-dsk-${ts}`, baseTpl.id)
    dskTempId = dsk.id
    try {
      await api.waitForDomainStatus(dsk.id, 'Stopped', 60000)
    } catch (e) {
      console.warn(`desktop ${dsk.id} did not reach Stopped within 60s: ${e.message}`)
    }

    const tplResp = await api.createTemplate(
      `bug37-tpl-${ts}`,
      dsk.id,
      {
        roles: false,
        categories: false,
        groups: false,
        users: [userId]
      }
    )
    templateId = tplResp.id
  })

  test.afterAll(async () => {
    if (templateId) {
      try {
        await api._authFetch('DELETE', `/api/v4/item/template/${templateId}?permanent=true`)
      } catch (e) {
        console.warn(`afterAll: deleteTemplate failed: ${e.message}`)
      }
    }
    if (dskTempId) {
      try {
        await api._authFetch('DELETE', `/api/v4/item/desktop/${dskTempId}?permanent=true`)
      } catch (e) {
        // Likely already gone — createTemplate consumed it.
      }
    }
    if (userId) {
      try {
        await api.deleteUser(userId)
      } catch (e) {
        console.warn(`afterAll: deleteUser failed: ${e.message}`)
      }
    }
  })

  test('shared template /item/desktop/{template_id}/get-info returns 200 for advanced user', async ({
    page
  }) => {
    test.skip(!templateId, 'beforeAll did not seed a template')

    // Login UI as the advanced user — needed because the get-info
    // call uses the user's session token.
    const login = new PageLogin(page)
    await login.goto()
    await login.form(userUsername, userPassword)
    await login.finished()

    // Pull the JWT cookie set by the login flow. The Vue 3 login
    // sets a cookie named ``authorization``; the helper-style fetch
    // here uses that cookie to authenticate the API call.
    const cookies = await page.context().cookies()
    const auth = cookies.find((c) => /authorization/i.test(c.name))
    expect(auth, 'login should have set an auth cookie').toBeTruthy()
    const token = decodeURIComponent(auth.value).replace(/^Bearer\s+/i, '')

    // Direct API call: the regression assertion. Before commit
    // 1b18cfd05 this returned 403 ``not_enough_rights_desktop``
    // because owns_domain_id only walked desktop-ownership rules
    // and didn't fall back to ``Alloweds.is_allowed`` for templates.
    const baseURL = test.info().project.use?.baseURL ?? 'https://localhost'
    const res = await fetch(
      `${baseURL}/api/v4/item/desktop/${templateId}/get-info`,
      { headers: { Authorization: `Bearer ${token}` } }
    )

    expect(
      res.status,
      'Bug #37 regression: GET /item/desktop/{template_id}/get-info as ' +
        `advanced user with the template in allowed.users returned ${res.status}. ` +
        'Expected 200 — owns_domain_id should fall back to Alloweds.is_allowed when ' +
        'domain.kind == \'template\'.'
    ).toBe(200)

    // Sanity: response should be a template, not a desktop.
    const body = await res.json()
    expect(body.kind).toBe('template')
    expect(body.id).toBe(templateId)
  })
})
