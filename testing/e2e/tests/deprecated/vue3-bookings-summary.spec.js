import { test, expect } from '../../fixtures/login.js'
import { commonHelpers } from '../../fixtures/common.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')

// Vue 3 bookings summary view — /frontend/bookings/summary
//
// Seed dependencies (testing/db/data/):
//   bookings.json            — 2 seeded bookings for local-default-admin-admin
//   bookings_priority.json   — 3 priority rules (default, default admins, test-low-forbid-time)
//   gpus.json                — 2 GPUs (A16 + T4)
//   reservables_vgpus.json   — 4 vGPU profiles
//   resource_planner.json    — 2 plans covering A16-2Q + T4-2Q
//   domains.json             — includes the booked desktop 7a9d...
//
// The admin user lands on the summary view and sees the seeded booking.

const summaryURL = '/frontend/bookings/summary'

test.describe('Vue 3 Bookings summary', () => {
  test.describe.configure({ mode: 'serial' })

  test('summary view renders without error for admin', async ({
    page,
    adminPerWorker,
    categories,
    loginHelpers,
  }) => {
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    await loginHelpers.login(page, adminPerWorker, categories, summaryURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })

    expect(page.url()).toContain(summaryURL)
    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)

    await commonHelpers.checkNoRouterErrors(page)

    // The view title is rendered from locale key components.bookings.summary.title
    // which resolves to "All your bookings" in en-US.
    await expect(page.locator('body')).toContainText(/all your bookings|todas tus reservas|totes les teves reserves/i, {
      timeout: 10000,
    })

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
    expect(fatalErrors, `Console errors:\n${fatalErrors.join('\n')}`).toHaveLength(0)
  })

  test('summary view hits /items/bookings and gets 200', async ({
    page,
    adminPerWorker,
    categories,
    loginHelpers,
  }) => {
    const bookingsResponsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/v4/items/bookings') && r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await loginHelpers.login(page, adminPerWorker, categories, summaryURL)
    const response = await bookingsResponsePromise

    expect(response.status()).toBe(200)
  })

  test('unauthenticated user is redirected from summary', async ({ page }) => {
    await page.goto(summaryURL)
    await page.waitForURL(/\/login(\/|$|\?)/, { timeout: 10000 })
    expect(page.url()).toMatch(/\/login/)
  })

  test('non-admin user can view their own bookings summary', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    // user_e2e_01 is a non-admin user with role=user; the summary endpoint
    // filters by token_payload user_id so they see their own (likely empty)
    // bookings without a 403.
    await loginHelpers.login(page, users.user_e2e_01, categories, summaryURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })

    expect(page.url()).toContain(summaryURL)
    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)
    await commonHelpers.checkNoRouterErrors(page)
  })
})
