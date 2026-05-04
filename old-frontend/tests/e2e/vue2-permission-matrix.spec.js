// @ts-check
//
// Permission-matrix smoke — non-admin role views.
//
// Every existing e2e spec logs in as ``admin`` and asserts admin-
// scoped behaviour. Role-leak / over-restriction bugs (e.g. Bug #37
// "advanced user can't access shared template") live in the cracks
// where roles aren't tested. This spec creates two synthetic users
// (advanced, user), logs in as each via the UI, and asserts the
// navbar items are scoped correctly:
//
//   user role     → no Templates / Media / Deployments / Administration
//                   in navbar (per NewNavBar.vue:42, 53, 64, 125)
//   advanced role → sees Templates / Media / Deployments BUT NOT
//                   Administration (the admin landing link)
//   admin role    → all of the above + Administration (covered by
//                   existing navbar.spec.js)
//
// Catches regressions where ``getUser.role_id`` resolution drifts
// or a v-if comparison breaks (e.g. typo'd role string).

import { test, expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { PageLogin } from './login-page'

test.describe.configure({ mode: 'serial' })

test.describe('Vue 2 permission matrix — non-admin role views', () => {
  /** @type {ApiHelper} */
  let api
  /** @type {string} */
  let advancedUserId
  /** @type {string} */
  let basicUserId
  const advancedUsername = `e2e_advanced_${Date.now()}`
  const basicUsername = `e2e_user_${Date.now()}`
  const password = 'rolematrix1234'

  test.beforeAll(async ({ baseURL }) => {
    api = new ApiHelper(baseURL ?? 'https://localhost')
    await api.login()

    const advResp = await api.createUser(
      advancedUsername, 'default', 'default-default', 'advanced', password
    )
    advancedUserId = advResp.id

    const userResp = await api.createUser(
      basicUsername, 'default', 'default-default', 'user', password
    )
    basicUserId = userResp.id
  })

  test.afterAll(async () => {
    if (advancedUserId) {
      try { await api.deleteUser(advancedUserId) } catch (e) { /* ignored */ }
    }
    if (basicUserId) {
      try { await api.deleteUser(basicUserId) } catch (e) { /* ignored */ }
    }
  })

  test('user role: navbar hides Templates / Media / Deployments / Administration', async ({
    page
  }) => {
    test.skip(!basicUserId, 'beforeAll did not seed a user')

    const login = new PageLogin(page)
    await login.goto()
    await login.form(basicUsername, password)
    await login.finished()

    // The nav-item for each section comes from
    // ``components.navbar.<section>`` i18n keys. Use English defaults
    // — if the test stack is configured for ES/CA we'd need a
    // locale-aware match.
    const expectations = [
      { name: /^templates$/i, hidden: true, label: 'Templates' },
      { name: /^media$/i, hidden: true, label: 'Media' },
      { name: /^deployments$/i, hidden: true, label: 'Deployments' },
      { name: /administration/i, hidden: true, label: 'Administration' },
      // Things that SHOULD be visible for users.
      { name: /^desktops$/i, hidden: false, label: 'Desktops' },
      { name: /storage|user.*storage/i, hidden: false, label: 'Storage' }
    ]

    for (const { name, hidden, label } of expectations) {
      const item = page.getByRole('link', { name }).or(page.getByRole('button', { name })).first()
      if (hidden) {
        await expect(
          item,
          `Permission leak: '${label}' nav item is visible to a 'user' role; ` +
          'should be hidden per NewNavBar.vue v-if guards on getUser.role_id !== \'user\'.'
        ).toHaveCount(0)
      } else {
        await expect(item, `nav item '${label}' should be visible to user`).toBeVisible({ timeout: 5000 })
      }
    }
  })

  test('advanced role: sees Templates/Media/Deployments but NOT Administration', async ({
    page
  }) => {
    test.skip(!advancedUserId, 'beforeAll did not seed advanced user')

    const login = new PageLogin(page)
    await login.goto()
    await login.form(advancedUsername, password)
    await login.finished()

    // Advanced sees the deployment-management surface but not
    // /isard-admin (administration is admin+manager only per
    // NewNavBar.vue:125: ``['admin','manager'].includes(role_id)``).
    await expect(
      page.getByRole('link', { name: /^templates$/i }).first(),
      'advanced user should see Templates'
    ).toBeVisible({ timeout: 5000 })
    await expect(
      page.getByRole('link', { name: /^media$/i }).first(),
      'advanced user should see Media'
    ).toBeVisible()
    await expect(
      page.getByRole('link', { name: /^deployments$/i }).first(),
      'advanced user should see Deployments'
    ).toBeVisible()

    // Administration link must be hidden.
    const admin = page.getByRole('link', { name: /administration/i }).first()
    await expect(
      admin,
      'Permission leak: \'Administration\' link visible to advanced role; ' +
      'should be admin/manager only.'
    ).toHaveCount(0)
  })
})
