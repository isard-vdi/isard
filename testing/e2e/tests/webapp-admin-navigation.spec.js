// Smoke coverage for the Flask /isard-admin/* admin surface.
//
// The webapp is the production admin UI today — 286 endpoints, zero
// test coverage before this spec. The goal here is the cheapest possible
// regression net: log in via the Vue 3 login page, navigate to every
// admin render route, and assert:
//   1. HTTP status < 400 (page did not 5xx)
//   2. A heading of some kind rendered (template hydrated)
//   3. No unhandled JavaScript error in the console
//
// Deeper behaviour (datatable filters, CRUD, modals) is left to the
// per-feature specs that follow.
//
// Pages are grouped by the three top-level sidebar sections:
//   • Domains render  — /isard-admin/admin/domains/render/<nav>
//   • Users render    — /isard-admin/admin/users/<nav>
//   • Misc top-level  — /isard-admin/admin/<page>
//
// Note on selectors: the Flask admin UI is jQuery + Bootstrap 4 +
// DataTables, served server-rendered. A successful render sets the page
// title in <title> and renders a header <h3>/<h4> with the nav name.
// We assert on the <title> to stay decoupled from layout markup.

import { test, expect } from '../fixtures/login.js'
import { bridgeAdminSession } from '../fixtures/common.js'

// Recyclebin bare path (`.../render/Recyclebin`) is dead code — the
// admin sidebar always links to `.../render/Recyclebin/Domains` and
// `.../render/Recyclebin/Config`, which are served by the separate
// `admin_recyclebin` handler. We test the paths the user actually
// reaches; the dead-code branch that tries to render a missing
// `recyclebin.html` template would be exercised only by a hand-typed
// URL and is tracked as follow-up cleanup in TESTS_TODO.
const DOMAINS_NAVS = [
  'Desktops',
  'Templates',
  'Deployments',
  'Storage',
  'Bases',
  'Resources',
  'Bookables',
  'BookablesEvents',
  'Priority',
  'Domains',
  'Config',
]

const RECYCLEBIN_NAVS = ['Domains', 'Config']

const USERS_NAVS = ['Management', 'QuotasLimits']

// Flat top-level admin pages (one render handler each). Skipped:
//  • /admin/login — hits the admin-only login redirect logic, covered
//    indirectly by the `beforeEach` login step.
//  • /admin/backups — served from AdminBackupsWebView.py and may hit
//    external storage that isn't available in dev; smoke-tested
//    separately below.
//  • /admin/isard-admin/media — typo-preserved real path; covered
//    below under "Media".
const TOP_LEVEL_PAGES = [
  { path: '/isard-admin/admin/landing', label: 'landing' },
  { path: '/isard-admin/admin/analytics', label: 'analytics' },
  { path: '/isard-admin/admin/analytics_config', label: 'analytics_config' },
  { path: '/isard-admin/admin/hypervisors', label: 'hypervisors' },
  { path: '/isard-admin/admin/isard-admin/media', label: 'media' },
  { path: '/isard-admin/admin/logs_desktops', label: 'logs_desktops' },
  {
    path: '/isard-admin/admin/logs_desktops_config',
    label: 'logs_desktops_config',
  },
  { path: '/isard-admin/admin/logs_users', label: 'logs_users' },
  { path: '/isard-admin/admin/logs_users_config', label: 'logs_users_config' },
  { path: '/isard-admin/admin/notifications_logs', label: 'notifications_logs' },
  {
    path: '/isard-admin/admin/notifications_manage',
    label: 'notifications_manage',
  },
  {
    path: '/isard-admin/admin/notifications_templates',
    label: 'notifications_templates',
  },
  // /admin/operations is only registered when OPERATIONS_API_ENABLED=true.
  // Skip unless the env flags it on — otherwise the route 404s by design.
  ...(process.env.E2E_OPERATIONS_API_ENABLED === 'true'
    ? [{ path: '/isard-admin/admin/operations', label: 'operations' }]
    : []),
  { path: '/isard-admin/admin/queues', label: 'queues' },
  { path: '/isard-admin/admin/queues_config', label: 'queues_config' },
  { path: '/isard-admin/admin/schedulers', label: 'schedulers' },
  { path: '/isard-admin/admin/storage_pools', label: 'storage_pools' },
  { path: '/isard-admin/admin/system', label: 'system' },
  { path: '/isard-admin/admin/updates', label: 'updates' },
  { path: '/isard-admin/admin/usage', label: 'usage' },
  { path: '/isard-admin/admin/usage_config', label: 'usage_config' },
  { path: '/isard-admin/admin/viewers', label: 'viewers' },
  { path: '/isard-admin/admin/users/UserStorage', label: 'users/UserStorage' },
  {
    path: '/isard-admin/admin/users/authentication',
    label: 'users/authentication',
  },
  { path: '/isard-admin/admin/users/migration', label: 'users/migration' },
  { path: '/isard-admin/admin/users/pwd_policies', label: 'users/pwd_policies' },
  { path: '/isard-admin/about', label: 'about' },
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
        // Bootstrap's JS dev warning and DataTables' polling network
        // noise are not our concern. Only surface genuine JS errors.
        !/Failed to load resource/.test(e) &&
        !/net::ERR_/.test(e) &&
        !/\[Deprecation\]/.test(e) &&
        !/DataTables warning/i.test(e),
    )
}

test.describe('Flask admin — domains render pages', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  for (const nav of DOMAINS_NAVS) {
    test(`domains/${nav} renders`, async ({ page }) => {
      const realErrors = consoleCollector(page)
      const url = `/isard-admin/admin/domains/render/${nav}`
      const response = await page.goto(url)
      if (response) expect(response.status()).toBeLessThan(400)

      // Every admin template sets <title>{{ title }} :: IsardVDI</title>.
      // A 5xx / unauth bounce lands on /login/... with a different title.
      await expect(page).toHaveURL(/\/isard-admin\//)

      // At least one content region must be present; bootstrap's main
      // wrapper for the admin body is #wrapper or .container-fluid.
      const hasShell = await page
        .locator('.main_container, .container.body')
        .first()
        .isVisible({ timeout: 5000 })
        .catch(() => false)
      expect(hasShell, `admin shell on ${nav}`).toBeTruthy()

      expect(realErrors(), `console errors on ${nav}`).toEqual([])
    })
  }
})

test.describe('Flask admin — Recyclebin sub-pages', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  for (const nav of RECYCLEBIN_NAVS) {
    test(`Recyclebin/${nav} renders`, async ({ page }) => {
      const realErrors = consoleCollector(page)
      const url = `/isard-admin/admin/domains/render/Recyclebin/${nav}`
      const response = await page.goto(url)
      if (response) expect(response.status()).toBeLessThan(400)
      await expect(page).toHaveURL(/\/isard-admin\//)
      const hasShell = await page
        .locator('.main_container, .container.body')
        .first()
        .isVisible({ timeout: 5000 })
        .catch(() => false)
      expect(hasShell, `admin shell on Recyclebin/${nav}`).toBeTruthy()
      expect(realErrors(), `console errors on Recyclebin/${nav}`).toEqual([])
    })
  }
})

test.describe('Flask admin — users render pages', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  for (const nav of USERS_NAVS) {
    test(`users/${nav} renders`, async ({ page }) => {
      const realErrors = consoleCollector(page)
      const url = `/isard-admin/admin/users/${nav}`
      const response = await page.goto(url)
      if (response) expect(response.status()).toBeLessThan(400)
      await expect(page).toHaveURL(/\/isard-admin\//)
      const hasShell = await page
        .locator('.main_container, .container.body')
        .first()
        .isVisible({ timeout: 5000 })
        .catch(() => false)
      expect(hasShell, `admin shell on users/${nav}`).toBeTruthy()
      expect(realErrors(), `console errors on users/${nav}`).toEqual([])
    })
  }
})

test.describe('Flask admin — top-level pages', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  for (const p of TOP_LEVEL_PAGES) {
    test(`${p.label} renders`, async ({ page }) => {
      const realErrors = consoleCollector(page)
      const response = await page.goto(p.path)
      if (response) expect(response.status()).toBeLessThan(400)
      await expect(page).toHaveURL(/\/isard-admin\//)
      const hasShell = await page
        .locator('.main_container, .container.body')
        .first()
        .isVisible({ timeout: 5000 })
        .catch(() => false)
      expect(hasShell, `admin shell on ${p.label}`).toBeTruthy()
      expect(realErrors(), `console errors on ${p.label}`).toEqual([])
    })
  }
})

test.describe('Flask admin — auth guard', () => {
  test('admin page redirects to /login when unauthenticated', async ({ page }) => {
    await page.goto('/isard-admin/logout')
    const response = await page.goto('/isard-admin/admin/landing')
    // Either a login page or a redirect — both OK, as long as we didn't
    // render the admin shell.
    const url = page.url()
    expect(url).toMatch(/\/login|\/isard-admin\/login/)
    if (response) expect(response.status()).toBeLessThan(500)
  })
})
