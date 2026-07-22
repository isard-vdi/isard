// Smoke coverage for Vue 2 (old-frontend) user-facing routes.
//
// The Vue 2 SPA still serves /desktops, /templates, /deployments,
// /booking, /planning, /profile, /domain, /media, /recyclebin and
// /userstorage at the apiv4-integration branch's current routing
// state. Vue 3 takes /login, /maintenance, /verify-email, /notifications
// and friends; Vue 2 owns everything else for the user-facing surface.
//
// We assert:
//   1. Page loads (200/3xx, never 5xx).
//   2. Vue 2 SPA boots (#app in the DOM and `/js/app.js` reachable).
//   3. The SPA didn't render an error overlay or stay blank — a known
//      indicator that the apiv4 endpoint behind the route is wrong is
//      a route that lands on /error/* or shows the empty-state with no
//      datatable mounted.
//   4. No unhandled JS error in the console (filtered for known noise).
//
// Deeper assertions — actual data rows, modals, edit flows — are
// covered by the per-feature specs (vue3-edit-flows for the migrated
// surface; backend smoke for what stays on Vue 2). This spec is the
// regression net for "did the route silently 5xx after a refactor".

import { test, expect } from '../../fixtures/login.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')

const ROUTES = [
  { path: '/desktops', label: 'desktops' },
  { path: '/templates', label: 'templates' },
  { path: '/deployments', label: 'deployments' },
  { path: '/booking', label: 'booking' },
  { path: '/booking/summary', label: 'booking-summary' },
  { path: '/planning', label: 'planning' },
  { path: '/profile', label: 'profile' },
  { path: '/media', label: 'media' },
  { path: '/userstorage', label: 'userstorage' },
  { path: '/recycleBins', label: 'recyclebin' },
]

function consoleCollector(page) {
  const errors = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
    if (msg.type() === 'warning' && /uncaught/i.test(msg.text())) {
      errors.push(msg.text())
    }
  })
  return () =>
    errors.filter(
      (e) =>
        // Ignore network noise + dev-server warnings + Bootstrap-Vue
        // deprecation chatter; these are not regression signals.
        !/Failed to load resource/.test(e) &&
        !/net::ERR_/.test(e) &&
        !/\[Vue warn\]/.test(e) &&
        !/\[BootstrapVue warn\]/.test(e) &&
        !/\[Deprecation\]/.test(e) &&
        // webpack-dev-server reconnect chatter in devel mode — only
        // informational; production has no /sockjs-node so this can't
        // mask a real issue.
        !/\[WDS\]/.test(e) &&
        !/sockjs-node/.test(e),
    )
}

function networkCollector(page) {
  const failed = []
  page.on('response', (resp) => {
    const url = resp.url()
    const status = resp.status()
    // Only flag failed requests to our own apiv4 / scheduler / engine.
    if (
      status >= 500 &&
      (url.includes('/api/v4/') ||
        url.includes('/scheduler/') ||
        url.includes('/engine/') ||
        url.includes('/authentication/'))
    ) {
      failed.push({ url, status })
    }
  })
  return () => failed
}

test.describe('Vue 2 — user-facing route smoke', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    // Log in as admin (per-worker isolation) and let the redirect land
    // on whichever SPA owns "/". Vue 2 owns "/" today.
    await loginHelpers.login(page, adminPerWorker, categories)
  })

  for (const route of ROUTES) {
    test(`${route.label} loads with no 5xx and no console errors`, async ({ page }) => {
      const realErrors = consoleCollector(page)
      const failed5xx = networkCollector(page)
      const response = await page.goto(route.path)
      // Either 2xx or a redirect — never 5xx, never the SPA error route.
      if (response) expect(response.status(), `${route.label} status`).toBeLessThan(500)
      // Wait briefly for the SPA to mount and any first-paint XHR to fire.
      await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {})
      // SPA mount point must exist.
      const app = page.locator('#app').first()
      await expect(app, `#app on ${route.label}`).toBeAttached({ timeout: 5000 })
      // The Vue 2 router has an /error/<code> sink — a 401/403/404
      // surfaced from any router guard or first XHR will land us there.
      // Treat that as a real failure, not a quirk.
      expect(page.url(), `${route.label} did not redirect to /error`).not.toMatch(/\/error\//)
      // No 5xx on any of our backends during the page load.
      expect(failed5xx(), `5xx on ${route.label} XHRs`).toEqual([])
      // No unhandled JS error.
      expect(realErrors(), `console errors on ${route.label}`).toEqual([])
    })
  }
})
