import { test, expect } from '../fixtures/login.js'
import { commonHelpers } from '../fixtures/common.js'

// Vue 3 per-item BookingView — /frontend/bookings/desktop/{id}
//
// The seeded booked desktop has id 7a9d3c12-1b23-4a56-8c9d-0e1f2a3b4c5d
// (testing/db/data/domains.json) with reservables.vgpus = ['NVIDIA-A16-2Q'].
// An active plan at testing/db/data/resource_planner.json covers the
// NVIDIA-A16-2Q subitem so the calendar renders availability.

const BOOKED_DESKTOP_ID = '7a9d3c12-1b23-4a56-8c9d-0e1f2a3b4c5d'
const bookingURL = `/frontend/bookings/desktop/${BOOKED_DESKTOP_ID}`

test.describe('Vue 3 Booking view', () => {
  test.describe.configure({ mode: 'serial' })

  test('booking view loads for admin on a reservable desktop', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    await loginHelpers.login(page, users.admin, categories, bookingURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })

    expect(page.url()).toContain(bookingURL)
    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)

    await commonHelpers.checkNoRouterErrors(page)

    // Status bar renders priority labels (locale keys
    // components.bookings.item.status-bar.{forbid-time,max-time,max-items}).
    await expect(page.locator('body')).toContainText(
      /advance time|maximum booking time|maximum bookings|tiempo de antelaci[oó]n|m[aà]xim/i,
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

  test('booking view fetches priority + item bookings', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    const priorityPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/items/bookings/get-priority-desktop/${BOOKED_DESKTOP_ID}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    const itemBookingsPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/booking/get-desktop/${BOOKED_DESKTOP_ID}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await loginHelpers.login(page, users.admin, categories, bookingURL)

    const [priority, itemBookings] = await Promise.all([priorityPromise, itemBookingsPromise])
    expect(priority.status()).toBe(200)
    expect(itemBookings.status()).toBe(200)
  })

  test('calendar container is rendered', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    await loginHelpers.login(page, users.admin, categories, bookingURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })

    // BookingCalendar.vue wraps vue-cal which adds a `.vuecal` root element.
    const calendar = page.locator('.vuecal').first()
    await expect(calendar).toBeVisible({ timeout: 15000 })
  })

  test('booking view with unknown desktop id shows error surface', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    // The apiv4 handlers return 404 or an ErrorResponse for unknown ids.
    // The view should not crash — it surfaces the error state without
    // leaking router.titles or redirecting to /login.
    const unknownURL = '/frontend/bookings/desktop/00000000-0000-0000-0000-000000000000'

    await loginHelpers.login(page, users.admin, categories, unknownURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })

    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)
    await commonHelpers.checkNoRouterErrors(page)
  })

  test('unauthenticated user is redirected from booking view', async ({ page }) => {
    await page.goto(bookingURL)
    await page.waitForURL(/\/login(\/|$|\?)/, { timeout: 10000 })
    expect(page.url()).toMatch(/\/login/)
  })
})
