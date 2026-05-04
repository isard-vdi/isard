// @ts-check
//
// Playwright fixture that yields a logged-in ``ApiHelper`` to each
// test. Each worker gets its own admin credentials from the
// pre-seeded pool created by ``global-setup.js``, so parallel
// workers don't fight over the same JWT (the sessions service
// shadows older logins when the same user authenticates twice in
// quick succession).
//
// Specs that need both UI login and API access compose with the
// ``loginTest`` fixture from ``./login-page``: import ``test`` from
// here for the ``api`` field, and pull in the UI fixture too. The
// fixtures are independent and stack via ``extend``.

import { test as base } from '@playwright/test'
import { fixture as loginFixture } from './login-page'
import { ApiHelper } from './helpers/api'

const POOL_PASSWORD = process.env.E2E_ADMIN_POOL_PASSWORD ?? 'e2e_admin_pw'

export const apiFixture = {
  api: [async ({ baseURL }, use, testInfo) => {
    const api = new ApiHelper(baseURL ?? 'https://localhost')
    // workerIndex is 0..N-1; map onto the pre-seeded admin pool.
    // Falls back to bootstrap admin if the pool wasn't created
    // (e.g. running specs without globalSetup via single-spec CLI).
    const username = `e2e_admin_${testInfo.workerIndex}`
    try {
      await api.login(username, POOL_PASSWORD, 'default')
    } catch (e) {
      await api.login()
    }
    await use(api)
  }, { scope: 'worker' }]
}

export const test = base.extend({ ...apiFixture, ...loginFixture })
