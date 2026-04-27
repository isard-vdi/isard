import { test, expect } from '../fixtures/login.js'
import { commonHelpers } from '../fixtures/common.js'

// Smoke coverage for the Vue 3 /maintenance route, served by
// MaintenanceView.vue.
//
// IMPORTANT: ``/maintenance`` is NOT marked ``meta.public: true`` in
// router/index.ts (line 312-317). The global beforeEach guard
// redirects anonymous users to /login, so the page is only reachable
// with an authenticated session. This spec pins the CURRENT behavior;
// if a future change marks the route public (likely the eventual
// intent for displaying global maintenance text on a logged-out
// landing), `test_public_route_redirects_anon_to_login` will start
// failing — flip it then to ``test_public_route_renders_for_anon``
// per the new contract.

const MAINTENANCE_URL = '/maintenance'

test.describe('Vue 3 Maintenance view', () => {
  test('anonymous visit is redirected to /login (current behavior)', async ({
    page,
  }) => {
    await page.goto(MAINTENANCE_URL)
    await page.waitForURL(/\/login(\/|$|\?)/, { timeout: 10000 })
    expect(page.url()).toMatch(/\/login/)
  })

  test('authenticated admin is redirected away when maintenance is off', async ({
    page,
    adminPerWorker,
    categories,
    loginHelpers,
  }) => {
    // MaintenanceView.vue (lines 120-128) does
    // ``window.location.pathname = '/'`` when neither
    // ``maintenanceStatus.enabled`` nor ``maintenance.enabled`` is
    // true — the page is meant to render only during a real
    // maintenance window. In the dev/CI stack maintenance is OFF, so
    // an authenticated admin landing on /maintenance must be bounced
    // to the home route. Pin the redirect-away contract so a future
    // refactor that drops the watcher (and strands admins on a
    // "we're down" page) fails loud.
    await loginHelpers.login(page, adminPerWorker, categories)
    await page.goto(MAINTENANCE_URL)
    await page.waitForURL((u) => !u.toString().includes('/maintenance'), {
      timeout: 15000,
    })
    expect(page.url()).not.toContain('/maintenance')
    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)
  })
})
