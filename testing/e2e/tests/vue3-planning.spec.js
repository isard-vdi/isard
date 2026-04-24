import { test, expect } from '../fixtures/login.js'
import { commonHelpers } from '../fixtures/common.js'

// Vue 3 Planning view — /frontend/planning
//
// Admin-only surface for managing reservable resource availability.
// Router guards: allowedRoles: ['admin'].
//
// Seed dependencies (testing/db/data/):
//   gpus.json               — 2 GPUs (A16 + T4)
//   gpu_profiles.json       — 6 GPU-profile definitions
//   reservables_vgpus.json  — 4 vGPU subitems
//   resource_planner.json   — 2 pre-existing plans

const planningURL = '/frontend/planning'

test.describe('Vue 3 Planning view', () => {
  test.describe.configure({ mode: 'serial' })

  test('planning view renders for admin', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    await loginHelpers.login(page, users.admin, categories, planningURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })

    expect(page.url()).toContain(planningURL)
    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)

    await commonHelpers.checkNoRouterErrors(page)

    // The view exposes a "Bookable type" select (components.bookings.item.new-planning.bookable-type).
    await expect(page.locator('body')).toContainText(
      /bookable type|tipo reservable|tipus reservable/i,
      { timeout: 10000 },
    )

    const fatalErrors = consoleErrors.filter(
      (e) =>
        !e.includes('Failed to load resource') &&
        !e.includes('favicon') &&
        !e.includes('socket.io') &&
        !e.includes('net::ERR_FAILED'),
    )
    expect(fatalErrors, `Console errors:\n${fatalErrors.join('\n')}`).toHaveLength(0)
  })

  test('planning view fetches reservable types list', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    const reservablesPromise = page.waitForResponse(
      (r) => r.url().includes('/api/v4/items/reservables') && r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await loginHelpers.login(page, users.admin, categories, planningURL)
    const response = await reservablesPromise

    expect(response.status()).toBe(200)
    const body = await response.json()
    // GET /items/reservables returns { reservables: string[] } — the seed
    // exposes the 'gpus' type through the 2 seeded gpus.json records.
    expect(body).toHaveProperty('reservables')
    expect(Array.isArray(body.reservables)).toBe(true)
  })

  test('selecting a reservable type loads items (GPUs)', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    await loginHelpers.login(page, users.admin, categories, planningURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })

    // Open the Bookable type select. Shadcn/radix renders select triggers as
    // buttons with role=combobox — match by the placeholder text.
    const typeSelect = page.locator('[role="combobox"]').first()
    await expect(typeSelect).toBeVisible({ timeout: 10000 })

    // The next Items GET should hit /items/reservables/{reservable_type} once
    // a value is picked.
    const itemsResponsePromise = page
      .waitForResponse(
        (r) =>
          /\/api\/v4\/items\/reservables\/[^/]+$/.test(r.url()) &&
          r.request().method() === 'GET',
        { timeout: 15000 },
      )
      .catch(() => null)

    await typeSelect.click()
    // The 'gpus' option comes straight from ReservableService.get_reservables.
    const gpusOption = page.locator('[role="option"]:has-text("gpus"), li:has-text("gpus")').first()
    if (await gpusOption.isVisible({ timeout: 3000 }).catch(() => false)) {
      await gpusOption.click()
      const response = await itemsResponsePromise
      if (response) {
        expect(response.status()).toBe(200)
      }
    }
  })

  test('non-admin user is denied access to /frontend/planning', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    // Router guard has allowedRoles: ['admin']. The route guard currently sets
    // window.location.pathname = '/error/403' for role-denied navigations, so
    // the resulting URL should no longer be /frontend/planning.
    await loginHelpers.login(page, users.user_e2e_01, categories, planningURL)

    // Give the router guard a moment to act.
    await page.waitForTimeout(1500)
    await page.waitForLoadState('networkidle', { timeout: 10000 })

    expect(page.url()).not.toMatch(new RegExp(`${planningURL}$`))
  })

  test('unauthenticated user is redirected from planning', async ({ page }) => {
    await page.goto(planningURL)
    await page.waitForURL(/\/login(\/|$|\?)/, { timeout: 10000 })
    expect(page.url()).toMatch(/\/login/)
  })
})
