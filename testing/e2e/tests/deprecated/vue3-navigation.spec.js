import { test, expect } from '../../fixtures/login.js'
import { commonHelpers } from '../../fixtures/common.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')

// Navigation smoke for every authenticated Vue 3 view.
// Each test logs in once as admin, navigates to the route, and checks:
//   1. URL matches the expected path
//   2. No Vue Router title-key leak (router.titles.*)
//   3. No unexpected redirect back to /login
//   4. No uncaught console error during initial render
//
// Auth target: the `admin` user from fixtures/login.js. Credentials can be
// overridden via E2E_ADMIN_USERNAME / E2E_ADMIN_PASSWORD for local dev.

const authedRoutes = [
  { path: '/frontend/desktops', name: 'desktops', roles: ['admin', 'manager', 'advanced', 'user'] },
  { path: '/frontend/desktops/new', name: 'new-desktop', roles: ['admin', 'manager', 'advanced', 'user'] },
  { path: '/frontend/templates', name: 'templates', roles: ['admin', 'manager', 'advanced'] },
  { path: '/frontend/templates/new', name: 'new-template', roles: ['admin', 'manager', 'advanced'] },
  { path: '/frontend/recycle-bin', name: 'recycle-bin', roles: ['admin', 'manager', 'advanced', 'user'] },
  { path: '/frontend/profile', name: 'profile', roles: ['admin', 'manager', 'advanced', 'user'] },
  { path: '/frontend/media', name: 'media', roles: ['admin', 'manager', 'advanced'] },
  { path: '/frontend/deployments', name: 'deployments', roles: ['admin', 'manager', 'advanced'] },
  { path: '/frontend/deployments/new', name: 'new-deployment', roles: ['admin', 'manager', 'advanced'] },
  { path: '/frontend/bookings/summary', name: 'booking-summary', roles: ['admin', 'manager', 'advanced', 'user'] },
  { path: '/frontend/planning', name: 'planning', roles: ['admin'] },
]

test.describe('Vue 3 navigation smoke', () => {
  test.describe.configure({ mode: 'serial' })

  for (const route of authedRoutes) {
    test(`${route.name} loads without error`, async ({
      page,
      adminPerWorker,
      categories,
      loginHelpers,
    }) => {
      const consoleErrors = []
      page.on('console', (msg) => {
        if (msg.type() === 'error') consoleErrors.push(msg.text())
      })

      await loginHelpers.login(page, adminPerWorker, categories, route.path)

      await page.waitForLoadState('networkidle', { timeout: 15000 })

      expect(page.url()).toContain(route.path)
      expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)

      await commonHelpers.checkNoRouterErrors(page)

      const title = await page.title()
      expect(title).not.toMatch(/(?:^|\s)404(?:\s|$)/i)
      expect(title).not.toMatch(/error/i)

      const fatalErrors = consoleErrors.filter(
        (e) =>
          !e.includes('Failed to load resource') &&
          !e.includes('favicon') &&
          !e.includes('socket.io') &&
          !e.includes('net::ERR_FAILED') &&
          // [WDS] Disconnected! is webpack-dev-server HMR noise from the
          // co-served Vue 2 old-frontend; sockjs-node is the same dev-server's
          // CORS-blocked keepalive. Both unrelated to Vue 3 functionality.
          !e.includes('[WDS]') &&
          !e.includes('sockjs-node'),
      )
      expect(fatalErrors, `Console errors on ${route.name}:\n${fatalErrors.join('\n')}`).toHaveLength(0)
    })
  }
})

test.describe('Vue 3 route guards', () => {
  test('unauthenticated user is redirected from protected route to /login', async ({
    page,
  }) => {
    await page.goto('/frontend/desktops')
    await page.waitForURL(/\/login(\/|$|\?)/, { timeout: 10000 })
    expect(page.url()).toMatch(/\/login/)
  })

  test('unauthenticated user hitting /frontend root redirects to /login', async ({
    page,
  }) => {
    await page.goto('/frontend')
    await page.waitForURL(/\/login(\/|$|\?)/, { timeout: 10000 })
    expect(page.url()).toMatch(/\/login/)
  })
})
