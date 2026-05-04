// @ts-check
//
// Playwright fixture that yields a freshly-logged-in ``ApiHelper``
// per test. Each test gets its own JWT, so 5-min token expiry never
// bites the long serial suite.
//
// Specs that need both UI login and API access compose with the
// ``loginTest`` fixture from ``./login-page``: import ``test`` from
// here for the ``api`` field, and pull in the UI fixture too. The
// fixtures are independent and stack via ``extend``.

import { test as base } from '@playwright/test'
import { fixture as loginFixture } from './login-page'
import { ApiHelper } from './helpers/api'

export const apiFixture = {
  api: async ({ baseURL }, use) => {
    const api = new ApiHelper(baseURL ?? 'https://localhost')
    await api.login()
    await use(api)
  }
}

export const test = base.extend({ ...apiFixture, ...loginFixture })
