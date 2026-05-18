// Drives the Bookables → Events admin page. Mirrors
// testing/e2e/specs/webapp/bookables/events.md — each test(...) maps to
// a numbered scenario in that spec.
//
// Conventions:
//   - Plans created by tests use a worker-staggered start date in the
//     far future (year 2400+) to avoid overlapping with seed plans and
//     with other workers' plans. The plan id is tracked via
//     testInfo.annotations (type: "plan-id") so afterEach can delete it
//     on failure.
//   - Bookings created by tests target a shared reservable desktop
//     (`SHARED_RESERVABLE_DESKTOP`). Booking ownership is set to the
//     calling user (admin_e2e_NN per worker), so the per-worker DELETE
//     permission check inside /item/booking/event/{id} succeeds. The
//     booking id is tracked via testInfo.annotations (type:
//     "booking-id"). Worker time slots don't overlap, so concurrent
//     bookings on the same desktop don't race the quota check.

import { test, expect, apiv4ClientForPage, unwrap } from '../../../fixtures/apiv4/index.js'
import {
  createBookingEvent,
  createPlan,
  deleteBookingEvent,
  deletePlan,
  getAllBookings,
  getPlanBookings,
  listAllPlans,
} from '../../../src/gen/apiv4/sdk.gen'

const EVENTS_URL = '/isard-admin/admin/domains/render/BookablesEvents'

// Seed-known references used by read-only scenarios.
const SEED_PLAN_ID = '24ee2910-c0e5-44bd-9a2b-5603ddc65d57'
const SEED_PLAN_GPU_ID = 'e2e8b73f-b989-47b4-9864-9e0da97f7b21'
const SEED_PLAN_PROFILE = 'NVIDIA-A16-2Q'
const SEED_BOOKING_ID = '0a1b2c3d-4e5f-6789-abcd-ef0123456789'

// Any reservable desktop will do — the booking belongs to the caller,
// not the desktop owner. This seed desktop (Test desktop with GPU) has
// reservables.vgpus = ['NVIDIA-A16-2Q'] and is the one S6/S8/S9 book
// against. Worker-staggered booking windows keep parallel bookings
// non-overlapping.
const SHARED_RESERVABLE_DESKTOP = {
  id: '3c6b1eaa-2d4f-4f43-9f87-2b1ac2c3d4e5',
  subitem_id: 'NVIDIA-A16-2Q',
}

async function createPlanViaApi(client, data) {
  const body = await unwrap(createPlan({ client, body: data })).catch(() => ({}))
  if (body?.id) return body
  // Older apiv4 builds returned ``{}`` because the route used to drop
  // the str id. Locate the freshly inserted plan by exact
  // item/subitem/start signature.
  const list = (await unwrap(listAllPlans({ client })).catch(() => [])) || []
  const match = list.find(
    (p) =>
      p.item_id === data.item_id &&
      p.subitem_id === data.subitem_id &&
      p.item_type === data.item_type &&
      new Date(p.start).toISOString().slice(0, 10) ===
        new Date(data.start).toISOString().slice(0, 10),
  )
  if (!match) {
    throw new Error(
      `createPlanViaApi: empty body and no matching plan in /items/reservables-planner`,
    )
  }
  return match
}

async function deletePlanViaApi(client, planId) {
  await deletePlan({ client, path: { plan_id: planId } }).catch(() => {})
}

async function trackPlanId(testInfo, id) {
  testInfo.annotations.push({ type: 'plan-id', description: id })
}

async function trackBookingId(testInfo, id) {
  testInfo.annotations.push({ type: 'booking-id', description: id })
}

async function createBookingViaApi(client, { item_id, start, end, title }) {
  const body = await unwrap(
    createBookingEvent({
      client,
      body: { item_id, item_type: 'desktop', start, end, title },
    }),
  )
  if (!body?.id) {
    throw new Error(`createBookingViaApi: no id in response`)
  }
  return body
}

async function deleteBookingViaApi(client, id) {
  await deleteBookingEvent({ client, path: { booking_id: id } }).catch(() => {})
}

// Pick a fresh, never-before-used start ms within this worker's
// 200-year slot. We anchor on Date.now() so two test runs minutes apart
// land in different decade buckets — and we bump a monotonic counter
// for any two windows requested in the same millisecond.
//
// Layout: workers slice the 2400-01-01..2599-12-31 range into 200-year
// blocks (way more than needed; safety margin against integer-rounding
// in ``ceil_dt``). Within a worker, each call lands on a distinct minute
// derived from (epoch_seconds_now + counter). This guarantees no two
// plans created by this process ever overlap.
let _planCounter = 0
const _WORKER_SLOT_MS = 200 * 365 * 86400000
const _MAX_OFFSET_MS = _WORKER_SLOT_MS - 86400000

function _uniqueBaseMs(testInfo) {
  const workerBase = Date.UTC(2400, 0, 1) + testInfo.workerIndex * _WORKER_SLOT_MS
  // Spread by 1 hour per (counter + seconds since process start).
  const offsetHours = _planCounter++ + Math.floor(Date.now() / 1000) % (24 * 365)
  const offsetMs = (offsetHours * 3600000) % _MAX_OFFSET_MS
  return workerBase + offsetMs
}

function uniqueFuturePlan(testInfo) {
  const base = _uniqueBaseMs(testInfo)
  return {
    start: new Date(base).toISOString(),
    end: new Date(base + 3600000).toISOString(),
  }
}

// Picks a worker-staggered booking window inside a fresh per-worker plan
// in the year 2400+ range so no seed plan and no other worker's plan
// can ever cover it.
function workerBookingWindow(testInfo) {
  const planSlotMs = 7 * 86400000
  const base = _uniqueBaseMs(testInfo)
  return {
    planStart: new Date(base).toISOString(),
    planEnd: new Date(base + planSlotMs).toISOString(),
    bookingStart: new Date(base + 86400000).toISOString(),
    bookingEnd: new Date(base + 86400000 + 3600000).toISOString(),
  }
}

async function gotoEvents(page) {
  await page.goto(EVENTS_URL)
  await page
    .locator('#table-planning ~ .dataTables_wrapper, .dataTables_wrapper:has(#table-planning)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  await page
    .locator('#table-booking ~ .dataTables_wrapper, .dataTables_wrapper:has(#table-booking)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
}

async function clearDateFilters(page, scope) {
  // The page initialises both start-min inputs to "now"; clearing them
  // is the only way to surface plans/bookings dated in the past.
  await page.locator(`#${scope}-filters .clear-date`).first().click()
}

async function clickPnotifyOk(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^ok$/i })
    .first()
    .click({ timeout: 5000 })
}

async function clickPnotifyCancel(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^cancel$/i })
    .first()
    .click({ timeout: 5000 })
}

async function listPlans(client) {
  const data = await unwrap(listAllPlans({ client })).catch(() => [])
  return Array.isArray(data) ? data : []
}

async function listBookings(client) {
  const data = await unwrap(getAllBookings({ client })).catch(() => [])
  return Array.isArray(data) ? data : []
}

test.describe('Admin Bookables — Events', () => {
  // Sweep leftovers from prior runs of *this* worker only. Plans are
  // identified by their year-2400 slot; bookings by their worker-prefixed
  // title. Bookings first — they reference plans.
  test.beforeAll(async ({ authenticatedContext }, workerInfo) => {
    const page = await authenticatedContext.newPage()
    try {
      const client = apiv4ClientForPage(page)
      const workerBase = Date.UTC(2400, 0, 1) + workerInfo.workerIndex * _WORKER_SLOT_MS
      const workerEnd = workerBase + _WORKER_SLOT_MS
      const titlePrefixes = [
        `e2e-empty-${workerInfo.workerIndex}`,
        `e2e-del-${workerInfo.workerIndex}`,
        `e2e-del-sub-${workerInfo.workerIndex}`,
      ]
      const staleBookings = (await listBookings(client)).filter(
        (b) =>
          typeof b.title === 'string' &&
          titlePrefixes.some((p) => b.title.startsWith(p)),
      )
      for (const b of staleBookings) {
        await deleteBookingViaApi(client, b.id)
      }
      const stalePlans = (await listPlans(client)).filter((p) => {
        const t = new Date(p.start).getTime()
        return Number.isFinite(t) && t >= workerBase && t < workerEnd
      })
      for (const p of stalePlans) {
        await deletePlanViaApi(client, p.id)
      }
    } finally {
      await page.close()
    }
  })

  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    // Bookings first — they reference plans. Order keeps the cleanup
    // resilient if a test fails mid-flow (the booking's plan-membership
    // may still be intact).
    const bookingIds = testInfo.annotations
      .filter((a) => a.type === 'booking-id')
      .map((a) => a.description)
    for (const id of bookingIds) {
      await deleteBookingViaApi(apiv4Admin, id)
    }
    const planIds = testInfo.annotations
      .filter((a) => a.type === 'plan-id')
      .map((a) => a.description)
    for (const id of planIds) {
      await deletePlanViaApi(apiv4Admin, id)
    }
  })

  // ---------------------------------------------------------------------
  // Scenario 1 — lists planning + bookings + scheduler tables
  // ---------------------------------------------------------------------
  test('S1: loads planning, bookings and scheduler tables on page load', async ({
    authenticatedPage: page,
  }) => {
    const planningResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/items/reservables-planner') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    const bookingsResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/items/bookings/all') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    const schedulerResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/scheduler/jobs/bookings') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await page.goto(EVENTS_URL)
    expect((await planningResp).status()).toBeLessThan(400)
    expect((await bookingsResp).status()).toBeLessThan(400)
    expect((await schedulerResp).status()).toBeLessThan(400)

    await page
      .locator('#table-planning ~ .dataTables_wrapper, .dataTables_wrapper:has(#table-planning)')
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })
    await page
      .locator('#table-booking ~ .dataTables_wrapper, .dataTables_wrapper:has(#table-booking)')
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })
    await page
      .locator(
        '#table-booking-scheduler ~ .dataTables_wrapper, .dataTables_wrapper:has(#table-booking-scheduler)',
      )
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })

    // Seed plan/booking are dated in the past (epoch ~2001); the default
    // start-min filter hides them. Clear the filters to confirm the
    // existing rows are actually rendered into the DOM, not just that
    // the empty wrapper appeared.
    await clearDateFilters(page, 'table-planning')
    await clearDateFilters(page, 'table-booking')
    await expect(
      page.locator(`#table-planning tbody tr[id="${SEED_PLAN_ID}"]`),
    ).toBeVisible({ timeout: 10000 })
    await expect(
      page.locator(`#table-booking tbody tr[id="${SEED_BOOKING_ID}"]`),
    ).toBeVisible({ timeout: 10000 })
  })

  // ---------------------------------------------------------------------
  // Scenario 2 — filters plans by date range (clientside)
  // ---------------------------------------------------------------------
  test('S2: date filter hides plans outside the configured range', async ({
    authenticatedPage: page,
  }) => {
    await gotoEvents(page)

    // The default start-min hides past plans. Clear the filter so the
    // seed (2001-2286) becomes visible, then apply a far-future filter
    // and verify it disappears. The daterangepicker UI clamps to
    // ``now±2 years``, so we drive ``filterDateDatatable`` directly with
    // a raw input value to exercise the clientside filter end-to-end.
    await clearDateFilters(page, 'table-planning')
    await expect(
      page.locator(`#table-planning tbody tr[id="${SEED_PLAN_ID}"]`),
    ).toBeVisible({ timeout: 10000 })

    await page.evaluate(() => {
      // eslint-disable-next-line no-undef
      $('#table-planning-filters #start-min').val('01-01-2300 00:00')
      // eslint-disable-next-line no-undef
      filterDateDatatable('table-planning')
    })

    await expect(
      page.locator(`#table-planning tbody tr[id="${SEED_PLAN_ID}"]`),
    ).toBeHidden({ timeout: 5000 })
  })

  // ---------------------------------------------------------------------
  // Scenario 3 — filters bookings by date range (clientside)
  // ---------------------------------------------------------------------
  test('S3: date filter hides bookings outside the configured range', async ({
    authenticatedPage: page,
  }) => {
    await gotoEvents(page)

    await clearDateFilters(page, 'table-booking')
    await expect(
      page.locator(`#table-booking tbody tr[id="${SEED_BOOKING_ID}"]`),
    ).toBeVisible({ timeout: 10000 })

    await page.evaluate(() => {
      // eslint-disable-next-line no-undef
      $('#table-booking-filters #start-min').val('01-01-2300 00:00')
      // eslint-disable-next-line no-undef
      filterDateDatatable('table-booking')
    })

    await expect(
      page.locator(`#table-booking tbody tr[id="${SEED_BOOKING_ID}"]`),
    ).toBeHidden({ timeout: 5000 })
  })

  // ---------------------------------------------------------------------
  // Scenario 4 — expand a plan and see its bookings
  // ---------------------------------------------------------------------
  test('S4: expanding a plan loads its bookings in the detail subtable', async ({
    authenticatedPage: page,
  }) => {
    await gotoEvents(page)
    await clearDateFilters(page, 'table-planning')

    const row = page.locator(`#table-planning tbody tr[id="${SEED_PLAN_ID}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    const detailResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/reservables-planner/${SEED_PLAN_ID}/bookings`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await row.locator('td.details-control button').first().click()
    expect((await detailResponse).status()).toBeLessThan(400)

    const detailTable = page.locator('#table-p-detail:visible')
    await expect(detailTable).toBeVisible({ timeout: 10000 })
    await expect(
      detailTable.locator('tbody tr:not(.dataTables_empty)').first(),
    ).toBeVisible({ timeout: 10000 })
  })

  // ---------------------------------------------------------------------
  // Scenario 5 — expand a booking and see the plans that contain it
  // ---------------------------------------------------------------------
  test('S5: expanding a booking loads its plans in the detail subtable', async ({
    authenticatedPage: page,
  }) => {
    await gotoEvents(page)
    await clearDateFilters(page, 'table-booking')

    const row = page.locator(`#table-booking tbody tr[id="${SEED_BOOKING_ID}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    const detailResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/booking/${SEED_BOOKING_ID}/plans`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await row.locator('td.details-control button').first().click()
    expect((await detailResponse).status()).toBeLessThan(400)

    const detailTable = page.locator('#table-b-detail:visible')
    await expect(detailTable).toBeVisible({ timeout: 10000 })
    await expect(
      detailTable.locator('tbody tr:not(.dataTables_empty)').first(),
    ).toBeVisible({ timeout: 10000 })
  })

  // ---------------------------------------------------------------------
  // Scenario 6 — empty plan deletes every booking it contains
  // ---------------------------------------------------------------------
  test('S6: empties a plan via the Empty button', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const win = workerBookingWindow(testInfo)
    // Worker-isolated plan in year 2400+ so no seed plan covers our
    // booking window. The booking that follows will associate to *this*
    // plan only (new_booking_plans picks the smallest matching plan).
    const plan = await createPlanViaApi(apiv4Admin, {
      item_type: 'gpus',
      item_id: SEED_PLAN_GPU_ID,
      subitem_id: SHARED_RESERVABLE_DESKTOP.subitem_id,
      start: win.planStart,
      end: win.planEnd,
    })
    await trackPlanId(testInfo, plan.id)

    const booking = await createBookingViaApi(apiv4Admin, {
      item_id: SHARED_RESERVABLE_DESKTOP.id,
      start: win.bookingStart,
      end: win.bookingEnd,
      title: `e2e-empty-${testInfo.workerIndex}`,
    })
    await trackBookingId(testInfo, booking.id)

    await gotoEvents(page)
    await clearDateFilters(page, 'table-planning')

    const row = page.locator(`#table-planning tbody tr[id="${plan.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-empty').click()

    const emptyResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/booking/empty/${plan.id}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await emptyResponse).status()).toBeLessThan(400)
    await expect(
      page.locator('.ui-pnotify-title', { hasText: /^deleted$/i }),
    ).toBeVisible({ timeout: 5000 })

    // Plan still exists; its bookings list is empty.
    const bookingsAfter =
      (await unwrap(getPlanBookings({ client: apiv4Admin, path: { plan_id: plan.id } }))) || []
    expect(bookingsAfter.find((b) => b.id === booking.id)).toBeUndefined()

    // Empty must NOT delete the plan itself, nor touch unrelated plans
    // (regression guard against a backend that mass-deletes by mistake).
    const plansAfter = await listPlans(apiv4Admin)
    expect(plansAfter.find((p) => p.id === plan.id), 'emptied plan must still exist')
      .toBeDefined()
    expect(plansAfter.find((p) => p.id === SEED_PLAN_ID), 'seed plan must be untouched')
      .toBeDefined()
  })

  // ---------------------------------------------------------------------
  // Scenario 7 — delete plan via the trash icon
  // ---------------------------------------------------------------------
  test('S7: deletes a user-created plan through the trash icon', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const { start, end } = uniqueFuturePlan(testInfo)
    const plan = await createPlanViaApi(apiv4Admin, {
      item_type: 'gpus',
      item_id: SEED_PLAN_GPU_ID,
      subitem_id: SEED_PLAN_PROFILE,
      start,
      end,
    })
    await trackPlanId(testInfo, plan.id)

    await gotoEvents(page)
    // The plan is in the far future — clear the filter so the row shows.
    await clearDateFilters(page, 'table-planning')

    const row = page.locator(`#table-planning tbody tr[id="${plan.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-delete-plan').click()

    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/reservables-planner/${plan.id}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await deleteResponse).status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /^deleted$/i }),
    ).toBeVisible({ timeout: 5000 })
    await expect(row).toBeHidden({ timeout: 10000 })

    // Deleting one plan must NOT delete other plans (regression guard
    // against a backend that mass-deletes by mistake).
    const plansAfter = await listPlans(apiv4Admin)
    expect(plansAfter.find((p) => p.id === plan.id), 'deleted plan must be gone')
      .toBeUndefined()
    expect(plansAfter.find((p) => p.id === SEED_PLAN_ID), 'seed plan must be untouched')
      .toBeDefined()
  })

  // ---------------------------------------------------------------------
  // Scenario 8 — delete booking from the main table
  // ---------------------------------------------------------------------
  test('S8: deletes a booking from #table-booking', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const win = workerBookingWindow(testInfo)
    const plan = await createPlanViaApi(apiv4Admin, {
      item_type: 'gpus',
      item_id: SEED_PLAN_GPU_ID,
      subitem_id: SHARED_RESERVABLE_DESKTOP.subitem_id,
      start: win.planStart,
      end: win.planEnd,
    })
    await trackPlanId(testInfo, plan.id)

    const booking = await createBookingViaApi(apiv4Admin, {
      item_id: SHARED_RESERVABLE_DESKTOP.id,
      start: win.bookingStart,
      end: win.bookingEnd,
      title: `e2e-del-${testInfo.workerIndex}`,
    })
    await trackBookingId(testInfo, booking.id)

    await gotoEvents(page)
    await clearDateFilters(page, 'table-booking')

    const row = page.locator(`#table-booking tbody tr[id="${booking.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-delete-booking').click()

    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/booking/event/${booking.id}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await deleteResponse).status()).toBeLessThan(400)
    await expect(
      page.locator('.ui-pnotify-title', { hasText: /^deleted$/i }),
    ).toBeVisible({ timeout: 5000 })
    await expect(row).toBeHidden({ timeout: 10000 })
  })

  // ---------------------------------------------------------------------
  // Scenario 9 — delete booking from the plan-detail subtable
  // ---------------------------------------------------------------------
  test('S9: deletes a booking from inside a plan detail subtable', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const win = workerBookingWindow(testInfo)
    const plan = await createPlanViaApi(apiv4Admin, {
      item_type: 'gpus',
      item_id: SEED_PLAN_GPU_ID,
      subitem_id: SHARED_RESERVABLE_DESKTOP.subitem_id,
      start: win.planStart,
      end: win.planEnd,
    })
    await trackPlanId(testInfo, plan.id)

    const booking = await createBookingViaApi(apiv4Admin, {
      item_id: SHARED_RESERVABLE_DESKTOP.id,
      start: win.bookingStart,
      end: win.bookingEnd,
      title: `e2e-del-sub-${testInfo.workerIndex}`,
    })
    await trackBookingId(testInfo, booking.id)

    await gotoEvents(page)
    await clearDateFilters(page, 'table-planning')

    const planRow = page.locator(`#table-planning tbody tr[id="${plan.id}"]`)
    await expect(planRow).toBeVisible({ timeout: 10000 })
    await planRow.locator('td.details-control button').first().click()

    const detailTable = page.locator('#table-p-detail:visible')
    await expect(detailTable).toBeVisible({ timeout: 10000 })
    const detailRow = detailTable.locator(`tbody tr[id="${booking.id}"]`)
    await expect(detailRow).toBeVisible({ timeout: 10000 })

    await detailRow.locator('button#btn-delete-booking').click()
    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/booking/event/${booking.id}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await deleteResponse).status()).toBeLessThan(400)
    await expect(
      page.locator('.ui-pnotify-title', { hasText: /^deleted$/i }),
    ).toBeVisible({ timeout: 5000 })

    // The handler reloads `#table-booking` AND the open `#table-p-detail`
    // after a successful delete; the booking must NOT remain in either
    // table without the admin having to collapse and re-open the plan.
    await expect(
      page.locator(`#table-booking tbody tr[id="${booking.id}"]`),
    ).toHaveCount(0, { timeout: 10000 })
    await expect(
      page.locator(`#table-p-detail:visible tbody tr[id="${booking.id}"]`),
    ).toHaveCount(0, { timeout: 10000 })
  })

  // ---------------------------------------------------------------------
  // Scenario 10 — cross-link from plan-detail row → bookings table filter
  // ---------------------------------------------------------------------
  test('S10: clicking a booking row in the plan detail filters #table-booking', async ({
    authenticatedPage: page,
  }) => {
    await gotoEvents(page)
    await clearDateFilters(page, 'table-planning')
    await clearDateFilters(page, 'table-booking')

    const planRow = page.locator(`#table-planning tbody tr[id="${SEED_PLAN_ID}"]`)
    await expect(planRow).toBeVisible({ timeout: 10000 })
    await planRow.locator('td.details-control button').first().click()
    await page.locator('#table-p-detail:visible').waitFor({ state: 'visible', timeout: 10000 })

    // Click a non-button cell of the first booking row inside the detail.
    const detailRow = page
      .locator(`#table-p-detail:visible tbody tr[id="${SEED_BOOKING_ID}"]`)
    await expect(detailRow).toBeVisible({ timeout: 10000 })
    await detailRow.locator('td').first().click()

    // The handler writes the booking id into the bookings filter input
    // and triggers it; verify the value lands and the table narrows to
    // a single row.
    await expect(page.locator('#table-booking_filter input')).toHaveValue(
      SEED_BOOKING_ID,
      { timeout: 5000 },
    )
    await expect(
      page.locator(`#table-booking tbody tr[id="${SEED_BOOKING_ID}"]`),
    ).toBeVisible({ timeout: 10000 })
  })

  // ---------------------------------------------------------------------
  // Scenario 11 — cancelling the PNotify must not call DELETE
  // ---------------------------------------------------------------------
  test('S11: cancelling the delete-plan PNotify does NOT call DELETE', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const { start, end } = uniqueFuturePlan(testInfo)
    const plan = await createPlanViaApi(apiv4Admin, {
      item_type: 'gpus',
      item_id: SEED_PLAN_GPU_ID,
      subitem_id: SEED_PLAN_PROFILE,
      start,
      end,
    })
    await trackPlanId(testInfo, plan.id)

    let deleteFired = false
    page.on('request', (req) => {
      if (
        req.url().includes(`/api/v4/item/reservables-planner/${plan.id}`) &&
        req.method() === 'DELETE'
      ) {
        deleteFired = true
      }
    })

    await gotoEvents(page)
    await clearDateFilters(page, 'table-planning')

    const row = page.locator(`#table-planning tbody tr[id="${plan.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-delete-plan').click()
    await clickPnotifyCancel(page)

    // The row must still be there and the network must have stayed quiet.
    await page.waitForTimeout(500)
    expect(deleteFired, 'DELETE must NOT fire when the confirm is cancelled')
      .toBeFalsy()
    await expect(row).toBeVisible()
  })
})
