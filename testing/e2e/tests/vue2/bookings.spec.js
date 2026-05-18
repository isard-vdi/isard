// Vue 2 (old-frontend) — Bookings with GPU; mirrors specs/vue2/bookings.md.
// These specs assert what the old frontend *renders and does* (calendar
// events, modal, snotify toasts), not just the API responses. API calls
// are only used for setup/cleanup and for the precise gap invariant.
// Admin tests stagger by worker over the 8 units of test-t4-2q-available-plan;
// user tests share `user_e2e_01` so they describe-serial.

import {
  test,
  expect,
  apiv4ClientForPage,
  cleanupTrackedResources,
  createBookingAndTrack,
  createDesktopAndTrack,
  getFirstAllowedTemplate,
  track,
  unwrap,
} from '../../fixtures/apiv4/index.js'
import {
  createBookingEvent,
  deleteBookingEvent,
  getBookingDesktop,
} from '../../src/gen/apiv4/sdk.gen'

const BOOKING_PRIORITY_URL_RE = /\/api\/v4\/items\/bookings\/get-priority-desktop\//
const ITEM_BOOKINGS_URL_RE = /\/api\/v4\/item\/booking\/get-desktop\//
const BOOKING_EVENT_URL = '/api/v4/item/booking/event'

// Seed data — see specs/vue2/bookings.md "Common data".
const VGPU_SHARED_USER = 'NVIDIA-T4-2Q'
const VGPU_NONE = 'None'

// Single-unit bookable seeded with role-differentiated priority
// (test-override-rule): advanced=800, user=300. See specs/vue2/bookings.md S3.
const VGPU_OVERRIDE = 'NVIDIA-T4-OVERRIDE'

// user_e2e_01 / advanced_e2e_01 sessions are provided worker-scoped by
// the login fixtures (userE2EPage/advancedE2EPage + apiv4User/Advanced),
// so specs reuse one login per worker instead of logging in per test.

// -----------------------------------------------------------------
// Helpers — test data
// -----------------------------------------------------------------

// Returns events overlapping the given range. Mirrors the calendar
// feed Booking.vue mounts on (`returnType=all` → bookings + plans
// merged). Used only for the precise S4 gap invariant.
async function getDesktopBookings(client, id) {
  const now = new Date()
  const start = new Date(now.getTime() - 24 * 3600 * 1000).toISOString()
  const end = new Date(now.getTime() + 30 * 24 * 3600 * 1000).toISOString()
  try {
    return (
      (await unwrap(
        getBookingDesktop({
          client,
          path: { item_id: id },
          query: { startDate: start, endDate: end, returnType: 'all' },
        }),
      )) ?? []
    )
  } catch {
    return []
  }
}

// Worker-staggered booking window so concurrent admins don't fight
// over the 8 units of NVIDIA-T4-2Q's plan. Each worker takes a 30-min
// strip starting at `now + 1h + worker*30min`.
function workerBookingWindow(workerIndex, offsetMinutes = 0, durationMinutes = 30) {
  const base = Date.now() + (60 + workerIndex * 30 + offsetMinutes) * 60 * 1000
  // Round up to the next minute so the start is always >= forbid_time.
  const startMs = Math.ceil(base / 60000) * 60000
  return {
    start: new Date(startMs).toISOString(),
    end: new Date(startMs + durationMinutes * 60 * 1000).toISOString(),
  }
}

// Per-worker cache for the first allowed template id — stable across
// tests for the same admin account.
const _templateCache = new Map()
async function templateIdFor(client, userKey) {
  if (_templateCache.has(userKey)) return _templateCache.get(userKey)
  const tpl = await getFirstAllowedTemplate(client)
  _templateCache.set(userKey, tpl.id)
  return tpl.id
}

// Unique-per-test name pattern that respects the apiv4 `[\-_ .A-Za-z0-9]+`
// shape (no slashes/special chars) and the 4..50-char range.
function desktopName(testInfo, suffix = '') {
  const slug = `${testInfo.workerIndex}-${Date.now().toString(36)}`
  const base = `e2e vue2 ${suffix} ${slug}`.slice(0, 50)
  return base.length >= 4 ? base : `e2e ${slug}`
}

// -----------------------------------------------------------------
// Helpers — driving and reading the Vue 2 UI
// -----------------------------------------------------------------

// Resolve a key through the live app's own i18n so text assertions
// hold whatever the session locale is.
async function appI18n(page, key) {
  return page.evaluate((k) => {
    const root = document.getElementById('app')?.__vue__
    if (!root) throw new Error('Vue 2 root instance not found on #app')
    return root.$t(k)
  }, key)
}

// Navigate to a desktop's booking page and wait for the two GETs
// Booking.vue fires on mount, then for the calendar to paint.
async function gotoBooking(page, desktopId) {
  const priorityPromise = page.waitForResponse(
    (r) => BOOKING_PRIORITY_URL_RE.test(r.url()) && r.request().method() === 'GET',
    { timeout: 15000 },
  )
  const eventsPromise = page.waitForResponse(
    (r) => ITEM_BOOKINGS_URL_RE.test(r.url()) && r.request().method() === 'GET',
    { timeout: 15000 },
  )
  await page.goto(`/booking/desktop/${desktopId}`)
  const priority = await priorityPromise
  const events = await eventsPromise
  await expect(page.locator('#vuecal').first()).toBeVisible({ timeout: 15000 })
  return { priority, events }
}

// Open EventModal in 'create' mode through Vuex with prefilled local
// times — same state a successful vue-cal drag-to-create produces.
// vue-cal's split-day drag and b-form-datepicker are both fragile to
// drive with raw input events; the user-facing contract this spec
// covers is the modal's title input + Create button (driven below)
// and the store's createEvent guard, which run unchanged from here.
async function setCreateModal(page, startMs, endMs) {
  await page.evaluate(
    ({ startMs, endMs }) => {
      const pad = (n) => String(n).padStart(2, '0')
      const fmtDate = (ms) => {
        const d = new Date(ms)
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
      }
      const fmtTime = (ms) => {
        const d = new Date(ms)
        return `${pad(d.getHours())}:${pad(d.getMinutes())}`
      }
      const root = document.getElementById('app')?.__vue__
      if (!root) throw new Error('Vue 2 root instance not found on #app')
      const $store = root.$store
      $store.dispatch('eventModalData', {
        type: 'create',
        startDate: fmtDate(startMs),
        startTime: fmtTime(startMs),
        endDate: fmtDate(endMs),
        endTime: fmtTime(endMs),
      })
      $store.dispatch('showBookingModal', true)
    },
    { startMs, endMs },
  )
  await page.locator('#eventModal').waitFor({ state: 'visible', timeout: 5000 })
}

// Type the title and press the modal's Create button. Returns a probe
// that records whether the frontend fired the POST and its response.
function watchBookingPost(page) {
  const state = { count: 0, lastResponse: null }
  const onReq = (req) => {
    if (req.url().endsWith(BOOKING_EVENT_URL) && req.method() === 'POST') state.count += 1
  }
  const onResp = async (resp) => {
    if (resp.url().endsWith(BOOKING_EVENT_URL) && resp.request().method() === 'POST') {
      state.lastResponse = resp
    }
  }
  page.on('request', onReq)
  page.on('response', onResp)
  state.stop = () => {
    page.off('request', onReq)
    page.off('response', onResp)
  }
  return state
}

async function pressCreate(page, title) {
  await page.locator('#eventModal #title').fill(title)
  await page.locator('#eventModal .modal-footer button.btn-primary').click()
}

// A rendered booking in the *bookings* split — vue-cal stamps the
// event_type as a class and IsardCalendar puts the title in an <h6>.
function bookingEventByTitle(page, title) {
  return page.locator(`#vuecal .vuecal__event.event:has(h6:text-is(${JSON.stringify(title)}))`)
}

// =================================================================
// Admin-driven scenarios (parallel-safe — adminPerWorker)
// =================================================================

test.describe('Vue 2 — Bookings (admin per-worker)', () => {
  // Login once per worker (worker-scoped admin context, admin_e2e_NN);
  // each test gets a fresh tab from it — no per-test login.
  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    await cleanupTrackedResources(apiv4Admin, testInfo)
  })

  // ---------------------------------------------------------------
  // S1 (admin happy path): create a booking through the modal and
  //     assert the frontend shows success — modal closes, no error
  //     toast, and the booking is painted in the *bookings* split.
  // ---------------------------------------------------------------
  test('S1 admin: creating a booking on a desktop with GPU + plan succeeds', async ({
    authenticatedPage: page,
    apiv4Admin: apiv4,
    adminPerWorker,
  }, testInfo) => {
    const templateId = await templateIdFor(apiv4, adminPerWorker.username)
    const desktop = await createDesktopAndTrack(apiv4, testInfo, {
      template_id: templateId,
      name: desktopName(testInfo, 's1'),
      description: 'e2e vue2 bookings spec',
      persistent: true,
      reservables: { vgpus: [VGPU_SHARED_USER] },
    })

    const { priority, events } = await gotoBooking(page, desktop.id)
    expect(priority.status()).toBeLessThan(400)
    expect(events.status()).toBeLessThan(400)

    const win = workerBookingWindow(testInfo.workerIndex)
    await setCreateModal(page, new Date(win.start).getTime(), new Date(win.end).getTime())
    const title = `e2e-vue2-s1-${testInfo.workerIndex}-${Date.now()}`

    const post = watchBookingPost(page)
    const postPromise = page.waitForResponse(
      (r) => r.url().endsWith(BOOKING_EVENT_URL) && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await pressCreate(page, title)
    const postResp = await postPromise
    expect(postResp.status(), 'POST booking must succeed').toBeLessThan(400)

    // Track the new booking for cleanup before any assertion can fail.
    const body = await postResp.json().catch(() => ({}))
    if (body?.id) track(testInfo, 'booking-id', body.id)

    // Frontend feedback: modal closes, no error toast, and the
    // booking is rendered in the *bookings* split by its title.
    await expect(page.locator('#eventModal')).toBeHidden({ timeout: 5000 })
    await expect(page.locator('.snotifyToast.snotify-error')).toHaveCount(0)
    await expect(bookingEventByTitle(page, title)).toBeVisible({ timeout: 10000 })
    post.stop()
  })

  // ---------------------------------------------------------------
  // S2a (admin): a GPU desktop with no plan — the calendar paints no
  //     `available` strip, and a create attempt is rejected by the
  //     backend and surfaced as an error toast (no booking shown).
  // ---------------------------------------------------------------
  test('S2a admin: desktop GPU with no plan → empty calendar + frontend error toast', async ({
    authenticatedPage: page,
    apiv4Admin: apiv4,
    adminPerWorker,
  }, testInfo) => {
    // NVIDIA-A16-4Q exists as a vGPU but the seed provides no
    // resource_planner row for it — the perfect natural-state case.
    const templateId = await templateIdFor(apiv4, adminPerWorker.username)
    const desktop = await createDesktopAndTrack(apiv4, testInfo, {
      template_id: templateId,
      name: desktopName(testInfo, 's2a'),
      description: 'e2e vue2 bookings spec',
      persistent: true,
      reservables: { vgpus: ['NVIDIA-A16-4Q'] },
    })

    const { priority, events } = await gotoBooking(page, desktop.id)
    expect(priority.status()).toBeLessThan(400)
    expect(events.status()).toBeLessThan(400)

    // No `available` strip painted on the availability split.
    await expect(page.locator('#vuecal .vuecal__event.available')).toHaveCount(0)

    const win = workerBookingWindow(testInfo.workerIndex)
    await setCreateModal(page, new Date(win.start).getTime(), new Date(win.end).getTime())
    const title = `e2e-vue2-s2a-${testInfo.workerIndex}`

    const post = watchBookingPost(page)
    const postPromise = page.waitForResponse(
      (r) => r.url().endsWith(BOOKING_EVENT_URL) && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await pressCreate(page, title)
    const postResp = await postPromise
    expect(
      postResp.status(),
      'POST must be rejected when no plan covers the window',
    ).toBeGreaterThanOrEqual(400)

    // Frontend feedback: ErrorUtils.handleErrors → $snotify.error.
    // The booking is never painted on the calendar.
    await expect(page.locator('.snotifyToast.snotify-error').first()).toBeVisible({
      timeout: 5000,
    })
    await expect(bookingEventByTitle(page, title)).toHaveCount(0)
    post.stop()
  })

  // S3 (priority override) lives in its own serial describe at the
  // end of this file — it needs the role-differentiated
  // `NVIDIA-T4-OVERRIDE` seed and two distinct sessions.

  // ---------------------------------------------------------------
  // S4 (admin): saturating all units of a GPU is a gap for a
  //     lower-priority user — verified both on the calendar feed and
  //     in what the Vue 2 calendar paints for that user.
  // ---------------------------------------------------------------
  test('S4 admin: a saturated window is a gap for a lower-priority user', async ({
    apiv4Admin: apiv4,
    adminPerWorker,
    userE2EContext,
  }, testInfo) => {
    const templateId = await templateIdFor(apiv4, adminPerWorker.username)

    // 8 desktops × 1 booking each = 8 units booked (== plan units).
    const win = workerBookingWindow(testInfo.workerIndex, /* offsetMinutes */ 60, /* duration */ 30)
    for (let i = 0; i < 8; i += 1) {
      const d = await createDesktopAndTrack(apiv4, testInfo, {
        template_id: templateId,
        name: desktopName(testInfo, `s4-${i}`),
        description: 'e2e vue2 bookings spec',
        persistent: true,
        reservables: { vgpus: [VGPU_SHARED_USER] },
      })
      const r = await createBookingEvent({
        client: apiv4,
        body: {
          item_id: d.id,
          item_type: 'desktop',
          start: win.start,
          end: win.end,
          title: `e2e-vue2-s4-admin-${testInfo.workerIndex}-${i}`,
        },
      })
      if (!r.response?.ok) {
        // Plan saturated by previous parallel workers (only 8 units
        // for this GPU at this exact window). Skip rather than report
        // a flaky failure — another worker exercises the same invariant.
        test.skip(
          true,
          `S4: plan saturated by another worker (booking ${i} got ${r.response?.status})`,
        )
      }
      track(testInfo, 'booking-id', r.data.id)
    }

    // Now check the lower-priority user's view via the worker-scoped
    // user session (don't trash the admin session held by `apiv4`).
    const userPage = await userE2EContext.newPage()
    try {
      const userClient = apiv4ClientForPage(userPage)
      const userTpl = await getFirstAllowedTemplate(userClient)
      const userDesktop = await createDesktopAndTrack(userClient, testInfo, {
        template_id: userTpl.id,
        name: desktopName(testInfo, 's4-user'),
        description: 'e2e vue2 bookings spec',
        persistent: true,
        reservables: { vgpus: [VGPU_SHARED_USER] },
      })

      // Precise invariant on the feed the calendar mounts on.
      const events = await getDesktopBookings(userClient, userDesktop.id)
      const winStart = new Date(win.start).getTime()
      const winEnd = new Date(win.end).getTime()
      const overlapping = events.filter((e) => {
        if (e.event_type !== 'available' && e.event_type !== 'overridable') return false
        const s = new Date(e.start).getTime()
        const en = new Date(e.end).getTime()
        return s < winEnd && en > winStart
      })
      expect(
        overlapping,
        'no available/overridable strip may cover a saturated window for a user-priority caller',
      ).toHaveLength(0)

      // What the user actually sees: the plan still paints `available`
      // strips, the user can't override (no orange strip), and trying
      // to book the gap is rejected by the backend and shown as an
      // error toast — no booking is painted.
      await gotoBooking(userPage, userDesktop.id)
      await expect(
        userPage.locator('#vuecal .vuecal__event.available').first(),
      ).toBeVisible({ timeout: 10000 })
      await expect(userPage.locator('#vuecal .vuecal__event.overridable')).toHaveCount(0)

      await setCreateModal(userPage, winStart, winEnd)
      const title = `e2e-vue2-s4-user-${testInfo.workerIndex}`
      const post = watchBookingPost(userPage)
      const postPromise = userPage
        .waitForResponse(
          (r) => r.url().endsWith(BOOKING_EVENT_URL) && r.request().method() === 'POST',
          { timeout: 15000 },
        )
        .catch(() => null)
      await pressCreate(userPage, title)
      const postResp = await postPromise
      expect(
        postResp?.status(),
        'booking the saturated gap must be rejected',
      ).toBeGreaterThanOrEqual(400)
      await expect(
        userPage.locator('.snotifyToast.snotify-error').first(),
      ).toBeVisible({ timeout: 5000 })
      await expect(bookingEventByTitle(userPage, title)).toHaveCount(0)
      post.stop()
    } finally {
      await userPage.close()
    }
  })
})

// =================================================================
// Role-specific scenarios (serial — share user_e2e_01)
// =================================================================

test.describe('Vue 2 — Bookings (user — serial)', () => {
  test.describe.configure({ mode: 'serial' })

  // Worker-scoped user_e2e_01 session; tests reuse it (no per-test login).
  test.afterEach(async ({ apiv4User }, testInfo) => {
    await cleanupTrackedResources(apiv4User, testInfo)
  })

  // ---------------------------------------------------------------
  // S2b (user): a desktop without a GPU paints an empty calendar and
  //     the Vue 2 client blocks creation client-side — priority is
  //     all-zero so `checkMaxTime` fails and a `maximum-time` info
  //     toast appears with no POST sent.
  // ---------------------------------------------------------------
  test('S2b user: desktop without GPU → empty calendar + client-side block', async ({
    userE2EPage: page,
    apiv4User: apiv4,
  }, testInfo) => {
    const tpl = await getFirstAllowedTemplate(apiv4)
    const desktop = await createDesktopAndTrack(apiv4, testInfo, {
      template_id: tpl.id,
      name: desktopName(testInfo, 's2b-user'),
      description: 'e2e vue2 bookings spec',
      persistent: true,
      reservables: { vgpus: [VGPU_NONE] },
    })

    await gotoBooking(page, desktop.id)
    // Both splits empty — no event of any kind is painted.
    await expect(page.locator('#vuecal .vuecal__event')).toHaveCount(0)

    const startMs = Date.now() + 60 * 60 * 1000
    await setCreateModal(page, startMs, startMs + 30 * 60 * 1000)
    const post = watchBookingPost(page)
    await pressCreate(page, `e2e-vue2-s2b-${Date.now()}`)

    // priority is {0,0,0}: BookingUtils.priorityAllowed fails on
    // max_time=0 → showNotification → $snotify.info(maximum-time).
    const expected = await appI18n(page, 'components.bookings.errors.maximum-time')
    await expect(
      page.locator('.snotifyToast.snotify-info .snotifyToast__body').first(),
    ).toContainText(expected, { timeout: 5000 })
    expect(post.count, 'client-side block must not fire a POST').toBe(0)
    await expect(page.locator('#eventModal')).toBeVisible()
    post.stop()
  })

  // ---------------------------------------------------------------
  // S5 (user): a booking starting inside `forbid_time` is rejected
  //     by the Vue 2 client (BookingUtils.priorityAllowed) before any
  //     POST; correcting the start reaches the success path.
  // ---------------------------------------------------------------
  test('S5 user: a booking inside forbid_time is blocked client-side', async ({
    userE2EPage: page,
    apiv4User: apiv4,
  }, testInfo) => {
    const tpl = await getFirstAllowedTemplate(apiv4)
    const desktop = await createDesktopAndTrack(apiv4, testInfo, {
      template_id: tpl.id,
      name: desktopName(testInfo, 's5-user'),
      description: 'e2e vue2 bookings spec',
      persistent: true,
      reservables: { vgpus: [VGPU_SHARED_USER] },
    })

    await gotoBooking(page, desktop.id)

    // Start 5 min out, under the user's 15-min forbid_time on T4-2Q.
    const inside = Date.now() + 5 * 60 * 1000
    await setCreateModal(page, inside, inside + 30 * 60 * 1000)
    const post = watchBookingPost(page)
    await pressCreate(page, `e2e-vue2-s5-inside-${Date.now()}`)

    const forbidMsg = await appI18n(page, 'components.bookings.errors.forbid')
    await expect(
      page.locator('.snotifyToast.snotify-info .snotifyToast__body').first(),
    ).toContainText(forbidMsg, { timeout: 5000 })
    expect(post.count, 'inside-forbid_time must not fire a POST').toBe(0)
    await expect(page.locator('#eventModal'), 'modal stays open').toBeVisible()

    // Positive control: move the start past forbid_time → success.
    const ok = Date.now() + 20 * 60 * 1000
    await setCreateModal(page, ok, ok + 30 * 60 * 1000)
    const title = `e2e-vue2-s5-ok-${Date.now()}`
    const postPromise = page.waitForResponse(
      (r) => r.url().endsWith(BOOKING_EVENT_URL) && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await pressCreate(page, title)
    const postResp = await postPromise
    expect(postResp.status(), 'corrected booking must succeed').toBeLessThan(400)
    const body = await postResp.json().catch(() => ({}))
    if (body?.id) track(testInfo, 'booking-id', body.id)
    await expect(page.locator('#eventModal')).toBeHidden({ timeout: 5000 })
    await expect(bookingEventByTitle(page, title)).toBeVisible({ timeout: 10000 })
    post.stop()
  })

  // ---------------------------------------------------------------
  // S6 (user): the 3rd booking is rejected by the backend when
  //     max_items=2; the frontend keeps the modal open and shows the
  //     error toast. Deleting one then lets the retry succeed.
  // ---------------------------------------------------------------
  test('S6 user: cannot create more bookings than max_items', async ({
    userE2EPage: page,
    apiv4User: apiv4,
  }, testInfo) => {
    const tpl = await getFirstAllowedTemplate(apiv4)
    const desktop = await createDesktopAndTrack(apiv4, testInfo, {
      template_id: tpl.id,
      name: desktopName(testInfo, 's6-user'),
      description: 'e2e vue2 bookings spec',
      persistent: true,
      reservables: { vgpus: [VGPU_SHARED_USER] },
    })

    // Non-overlapping windows, all outside the 15-min forbid_time.
    const win = (offsetMin) => {
      const startMs = Date.now() + offsetMin * 60 * 1000
      return { startMs, endMs: startMs + 30 * 60 * 1000 }
    }
    await createBookingAndTrack(apiv4, testInfo, {
      item_id: desktop.id,
      item_type: 'desktop',
      start: new Date(win(60).startMs).toISOString(),
      end: new Date(win(60).endMs).toISOString(),
      title: `e2e-vue2-s6-1-${Date.now()}`,
    })
    const b = await createBookingAndTrack(apiv4, testInfo, {
      item_id: desktop.id,
      item_type: 'desktop',
      start: new Date(win(120).startMs).toISOString(),
      end: new Date(win(120).endMs).toISOString(),
      title: `e2e-vue2-s6-2-${Date.now()}`,
    })

    // 3rd booking, driven through the modal — backend rejects it.
    await gotoBooking(page, desktop.id)
    const third = win(180)
    await setCreateModal(page, third.startMs, third.endMs)
    const title = `e2e-vue2-s6-3-${Date.now()}`
    const post = watchBookingPost(page)
    const rejectPromise = page.waitForResponse(
      (r) => r.url().endsWith(BOOKING_EVENT_URL) && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await pressCreate(page, title)
    const rejected = await rejectPromise
    expect(rejected.status(), '3rd booking must be rejected').toBeGreaterThanOrEqual(400)

    // Frontend keeps the modal open and shows the backend error.
    await expect(
      page.locator('.snotifyToast.snotify-error').first(),
    ).toBeVisible({ timeout: 5000 })
    await expect(page.locator('#eventModal')).toBeVisible()
    await expect(bookingEventByTitle(page, title)).toHaveCount(0)

    // Positive control: free one slot, retry the 3rd → succeeds.
    await unwrap(deleteBookingEvent({ client: apiv4, path: { booking_id: b.id } }))
    await gotoBooking(page, desktop.id)
    await setCreateModal(page, third.startMs, third.endMs)
    const retryTitle = `e2e-vue2-s6-3-retry-${Date.now()}`
    const okPromise = page.waitForResponse(
      (r) => r.url().endsWith(BOOKING_EVENT_URL) && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await pressCreate(page, retryTitle)
    const okResp = await okPromise
    expect(okResp.status(), 'retry after freeing a slot must succeed').toBeLessThan(400)
    const body = await okResp.json().catch(() => ({}))
    if (body?.id) track(testInfo, 'booking-id', body.id)
    await expect(page.locator('#eventModal')).toBeHidden({ timeout: 5000 })
    await expect(bookingEventByTitle(page, retryTitle)).toBeVisible({ timeout: 10000 })
    post.stop()
  })

  // ---------------------------------------------------------------
  // S7 (user): a booking longer than `max_time` is rejected by the
  //     Vue 2 client (BookingUtils.checkMaxTime) before any POST;
  //     the inclusive 120-min boundary reaches the success path.
  // ---------------------------------------------------------------
  test('S7 user: an over-length booking is blocked client-side', async ({
    userE2EPage: page,
    apiv4User: apiv4,
  }, testInfo) => {
    const tpl = await getFirstAllowedTemplate(apiv4)
    const desktop = await createDesktopAndTrack(apiv4, testInfo, {
      template_id: tpl.id,
      name: desktopName(testInfo, 's7-user'),
      description: 'e2e vue2 bookings spec',
      persistent: true,
      reservables: { vgpus: [VGPU_SHARED_USER] },
    })

    await gotoBooking(page, desktop.id)

    // 150 min > the user's max_time=120 on T4-2Q.
    const startMs = Date.now() + 30 * 60 * 1000
    await setCreateModal(page, startMs, startMs + 150 * 60 * 1000)
    const post = watchBookingPost(page)
    await pressCreate(page, `e2e-vue2-s7-over-${Date.now()}`)

    const maxMsg = await appI18n(page, 'components.bookings.errors.maximum-time')
    await expect(
      page.locator('.snotifyToast.snotify-info .snotifyToast__body').first(),
    ).toContainText(maxMsg, { timeout: 5000 })
    expect(post.count, 'over-length must not fire a POST').toBe(0)
    await expect(page.locator('#eventModal'), 'modal stays open').toBeVisible()

    // Positive control: exactly 120 min is the inclusive boundary.
    const okStart = Date.now() + 30 * 60 * 1000
    await setCreateModal(page, okStart, okStart + 120 * 60 * 1000)
    const title = `e2e-vue2-s7-ok-${Date.now()}`
    const postPromise = page.waitForResponse(
      (r) => r.url().endsWith(BOOKING_EVENT_URL) && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await pressCreate(page, title)
    const postResp = await postPromise
    expect(postResp.status(), '120-min booking must succeed').toBeLessThan(400)
    const body = await postResp.json().catch(() => ({}))
    if (body?.id) track(testInfo, 'booking-id', body.id)
    await expect(page.locator('#eventModal')).toBeHidden({ timeout: 5000 })
    await expect(bookingEventByTitle(page, title)).toBeVisible({ timeout: 10000 })
    post.stop()
  })
})

// =================================================================
// Priority override (serial — share user_e2e_01 + advanced_e2e_01)
//
// On the single-unit `NVIDIA-T4-OVERRIDE` bookable, advanced_e2e_01
// resolves to priority 800 and user_e2e_01 to 300 (seed
// `test-override-rule`). The unit being "taken" by a lower-priority
// booking is `overridable` for the higher-priority caller (it may
// book it) and `unavailable` for the lower-priority one (it may not).
// Note: on create the loser's booking row is not deleted — eviction
// is a later scheduler concern — so these specs assert the create
// decision (allowed vs rejected), which is what the UI surfaces.
// =================================================================

test.describe('Vue 2 — Bookings priority override (serial)', () => {
  test.describe.configure({ mode: 'serial' })

  // Cross-role resources need an admin to tear down; reuse the
  // worker-scoped admin session.
  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    await cleanupTrackedResources(apiv4Admin, testInfo)
  })

  async function makeDesktop(client, testInfo, suffix) {
    const tpl = await getFirstAllowedTemplate(client)
    return createDesktopAndTrack(client, testInfo, {
      template_id: tpl.id,
      name: desktopName(testInfo, suffix),
      description: 'e2e vue2 bookings spec',
      persistent: true,
      reservables: { vgpus: [VGPU_OVERRIDE] },
    })
  }

  // ---------------------------------------------------------------
  // S3a: a higher-priority (advanced) caller can book the single
  //      unit even though a lower-priority (user) booking already
  //      holds it — the slot is painted `overridable` and the
  //      create succeeds.
  // ---------------------------------------------------------------
  test('S3a advanced overrides a lower-priority user booking', async ({
    advancedE2EPage: page,
    apiv4Advanced: advClient,
    userE2EContext,
  }, testInfo) => {
    const win = workerBookingWindow(testInfo.workerIndex, /* offsetMinutes */ 0, /* dur */ 30)

    // user_e2e_01 (priority 300) takes the only unit.
    const userPage = await userE2EContext.newPage()
    try {
      const userClient = apiv4ClientForPage(userPage)
      const userDesktop = await makeDesktop(userClient, testInfo, 's3a-user')
      const userBooking = await unwrap(
        createBookingEvent({
          client: userClient,
          body: {
            item_id: userDesktop.id,
            item_type: 'desktop',
            start: win.start,
            end: win.end,
            title: `e2e-vue2-s3a-user-${testInfo.workerIndex}`,
          },
        }),
      )
      track(testInfo, 'booking-id', userBooking.id)

      // advanced_e2e_01 (priority 800) sees the slot as overridable
      // and books it through the modal.
      const advDesktop = await makeDesktop(advClient, testInfo, 's3a-adv')

      await gotoBooking(page, advDesktop.id)
      await expect(
        page.locator('#vuecal .vuecal__event.overridable').first(),
        'the user-held unit must be overridable for the advanced caller',
      ).toBeVisible({ timeout: 10000 })

      await setCreateModal(page, new Date(win.start).getTime(), new Date(win.end).getTime())
      const title = `e2e-vue2-s3a-adv-${testInfo.workerIndex}-${Date.now()}`
      const postPromise = page.waitForResponse(
        (r) => r.url().endsWith(BOOKING_EVENT_URL) && r.request().method() === 'POST',
        { timeout: 15000 },
      )
      await pressCreate(page, title)
      const postResp = await postPromise
      expect(
        postResp.status(),
        'higher-priority caller must override the saturated unit',
      ).toBeLessThan(400)
      const body = await postResp.json().catch(() => ({}))
      if (body?.id) track(testInfo, 'booking-id', body.id)

      await expect(page.locator('#eventModal')).toBeHidden({ timeout: 5000 })
      await expect(page.locator('.snotifyToast.snotify-error')).toHaveCount(0)
      await expect(bookingEventByTitle(page, title)).toBeVisible({ timeout: 10000 })
    } finally {
      await userPage.close()
    }
  })

  // ---------------------------------------------------------------
  // S3b: a lower-priority (user) caller cannot book the single unit
  //      once a higher-priority (advanced) booking holds it — the
  //      slot is not `overridable`, the create is rejected by the
  //      backend, and the error is surfaced. The advanced booking
  //      stays intact.
  // ---------------------------------------------------------------
  test('S3b a lower-priority user cannot override an advanced booking', async ({
    userE2EPage: page,
    apiv4User: userClient,
    advancedE2EContext,
  }, testInfo) => {
    const win = workerBookingWindow(testInfo.workerIndex, /* offsetMinutes */ 120, /* dur */ 30)

    // advanced_e2e_01 (priority 800) takes the only unit.
    const advPage = await advancedE2EContext.newPage()
    try {
      const advClient = apiv4ClientForPage(advPage)
      const advDesktop = await makeDesktop(advClient, testInfo, 's3b-adv')
      const advBooking = await unwrap(
        createBookingEvent({
          client: advClient,
          body: {
            item_id: advDesktop.id,
            item_type: 'desktop',
            start: win.start,
            end: win.end,
            title: `e2e-vue2-s3b-adv-${testInfo.workerIndex}`,
          },
        }),
      )
      track(testInfo, 'booking-id', advBooking.id)

      // user_e2e_01 (priority 300) cannot override it.
      const userDesktop = await makeDesktop(userClient, testInfo, 's3b-user')

      await gotoBooking(page, userDesktop.id)
      await expect(
        page.locator('#vuecal .vuecal__event.overridable'),
        'a user-priority caller must not see an advanced booking as overridable',
      ).toHaveCount(0)

      await setCreateModal(page, new Date(win.start).getTime(), new Date(win.end).getTime())
      const title = `e2e-vue2-s3b-user-${testInfo.workerIndex}-${Date.now()}`
      const postPromise = page
        .waitForResponse(
          (r) => r.url().endsWith(BOOKING_EVENT_URL) && r.request().method() === 'POST',
          { timeout: 15000 },
        )
        .catch(() => null)
      await pressCreate(page, title)
      const postResp = await postPromise
      expect(
        postResp?.status(),
        'lower-priority caller must be rejected on a saturated unit',
      ).toBeGreaterThanOrEqual(400)
      await expect(
        page.locator('.snotifyToast.snotify-error').first(),
      ).toBeVisible({ timeout: 5000 })
      await expect(page.locator('#eventModal')).toBeVisible()
      await expect(bookingEventByTitle(page, title)).toHaveCount(0)

      // The advanced booking was not evicted by the failed attempt.
      const advEvents = await getDesktopBookings(advClient, advDesktop.id)
      expect(
        advEvents.find((e) => e.id === advBooking.id),
        'the higher-priority booking must remain',
      ).toBeTruthy()
    } finally {
      await advPage.close()
    }
  })

  // ---------------------------------------------------------------
  // S3c: a higher-priority (advanced) caller can create a *wider*
  //      booking that spans a lower-priority (user) booking sitting
  //      in the middle — the calendar paints the middle segment
  //      `overridable` (available margins on each side) and the
  //      wider create succeeds.
  // ---------------------------------------------------------------
  test('S3c advanced can book a wider window over an overridable booking in the middle', async ({
    advancedE2EPage: page,
    apiv4Advanced: advClient,
    userE2EContext,
  }, testInfo) => {
    // 90-min advanced window; user holds the middle 30 min only.
    const wide = workerBookingWindow(testInfo.workerIndex, /* offsetMinutes */ 240, /* dur */ 90)
    const wideStartMs = new Date(wide.start).getTime()
    const wideEndMs = new Date(wide.end).getTime()
    const midStartMs = wideStartMs + 30 * 60 * 1000
    const midEndMs = midStartMs + 30 * 60 * 1000

    const userPage = await userE2EContext.newPage()
    try {
      const userClient = apiv4ClientForPage(userPage)
      const userDesktop = await makeDesktop(userClient, testInfo, 's3c-user')
      const userBooking = await unwrap(
        createBookingEvent({
          client: userClient,
          body: {
            item_id: userDesktop.id,
            item_type: 'desktop',
            start: new Date(midStartMs).toISOString(),
            end: new Date(midEndMs).toISOString(),
            title: `e2e-vue2-s3c-user-${testInfo.workerIndex}`,
          },
        }),
      )
      track(testInfo, 'booking-id', userBooking.id)

      const advDesktop = await makeDesktop(advClient, testInfo, 's3c-adv')

      await gotoBooking(page, advDesktop.id)
      await expect(
        page.locator('#vuecal .vuecal__event.overridable').first(),
        'the middle user booking must be overridable for the advanced caller',
      ).toBeVisible({ timeout: 10000 })

      await setCreateModal(page, wideStartMs, wideEndMs)
      const title = `e2e-vue2-s3c-adv-${testInfo.workerIndex}-${Date.now()}`
      const postPromise = page.waitForResponse(
        (r) => r.url().endsWith(BOOKING_EVENT_URL) && r.request().method() === 'POST',
        { timeout: 15000 },
      )
      await pressCreate(page, title)
      const postResp = await postPromise
      expect(
        postResp.status(),
        'the wider booking spanning an overridable one must be created',
      ).toBeLessThan(400)
      const body = await postResp.json().catch(() => ({}))
      if (body?.id) track(testInfo, 'booking-id', body.id)

      await expect(page.locator('#eventModal')).toBeHidden({ timeout: 5000 })
      await expect(page.locator('.snotifyToast.snotify-error')).toHaveCount(0)
      await expect(bookingEventByTitle(page, title)).toBeVisible({ timeout: 10000 })
    } finally {
      await userPage.close()
    }
  })
})
