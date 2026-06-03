import { test, expect } from '../../fixtures/login.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')

// Smoke coverage for the Vue 3 /maintenance route, served by
// MaintenanceView.vue.
//
// /maintenance is ``meta.public: true`` so anonymous visitors AND
// authenticated users alike can land on it. MaintenanceView.vue
// branches its queries on the JWT — anon path uses
// ``maintenanceStatusApiV4MaintenanceStatusGetOptions`` (no auth) plus
// the public maintenance-text endpoint; auth path additionally fetches
// the per-category maintenance config. When NEITHER status flag is
// true (the dev/CI default — maintenance mode OFF), the view does
// ``window.location.pathname = '/'`` so visitors are bounced off the
// "we're down" page. Both tests below pin that bounce-when-off
// contract: anon ends up at /login (since / requires auth), authed
// admin ends up at the home route.

const MAINTENANCE_URL = '/maintenance'

test.describe('Vue 3 Maintenance view', () => {
  test('anonymous visit is bounced off /maintenance when maintenance is off', async ({
    page,
  }) => {
    // The route is public so the global beforeEach guard does NOT
    // redirect to /login. The view itself decides whether to render
    // (maintenance ON) or self-redirect to / (maintenance OFF). In
    // the dev/CI stack maintenance is OFF, so the view redirects
    // and the anonymous visitor then gets bounced to /login by the
    // home route's auth guard. Either way, the URL must NOT stay on
    // /maintenance — that's the contract.
    await page.goto(MAINTENANCE_URL)
    await page.waitForURL((u) => !u.toString().includes('/maintenance'), {
      timeout: 15000,
    })
    expect(page.url()).not.toContain('/maintenance')
  })

  test('authenticated admin is bounced off /maintenance when maintenance is off', async ({
    page,
    adminPerWorker,
    categories,
    loginHelpers,
  }) => {
    // Same self-redirect mechanism (MaintenanceView.vue:120-128 does
    // ``window.location.pathname = '/'`` when isMaintenance is false).
    // Authed admin lands at /, which the SPA routes to the home view
    // (NOT /login since the admin has a valid session).
    await loginHelpers.login(page, adminPerWorker, categories)
    await page.goto(MAINTENANCE_URL)
    await page.waitForURL((u) => !u.toString().includes('/maintenance'), {
      timeout: 15000,
    })
    expect(page.url()).not.toContain('/maintenance')
    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)
  })
})
