// Vue 2 (old-frontend) — admin Planning; mirrors specs/vue2/planning.md.
// The admin creates/deletes/joins resource-planner *plannings* on a
// dedicated, plan-free GPU device (`e2e-gpu-planning`, profile
// NVIDIA-T4-2Q) so it never collides with the seeded wide plans.
// Per-worker windows keep the single device collision-free; the specs
// run serial. API (listAllPlans filtered) is the authoritative
// assertion; the calendar block is verified after an explicit refetch
// because the Vue 2 store does not re-fetch plannings after create.

import {
  test,
  expect,
  cleanupTrackedResources,
  createPlanAndTrack,
  track,
  unwrap,
} from '../../fixtures/apiv4/index.js'
import { createPlan, deletePlan, listAllPlans } from '../../src/gen/apiv4/sdk.gen'

const PLANNER_URL = '/api/v4/item/reservables-planner'
const BY_ITEM_RE = /\/api\/v4\/item\/reservables-planner\/by-item\//
const GPU_ITEM = 'e2e-gpu-planning'
const PROFILE = 'NVIDIA-T4-2Q'

// -----------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------

// Future, 5-minute-aligned, per-worker, per-slot window so parallel
// workers never overlap on the shared single device (the backend
// rejects overlapping plannings on the same GPU item).
function planWindow(workerIndex, slotMinutes, durationMin = 20) {
  const base = Date.now() + (60 + workerIndex * 240 + slotMinutes) * 60 * 1000
  const startMs = Math.ceil(base / (5 * 60 * 1000)) * (5 * 60 * 1000)
  const endMs = startMs + durationMin * 60 * 1000
  return { startMs, endMs }
}

// Resolve a key through the live app's i18n so text assertions hold
// whatever the session locale is.
async function appI18n(page, key) {
  return page.evaluate((k) => {
    const root = document.getElementById('app')?.__vue__
    if (!root) throw new Error('Vue 2 root instance not found on #app')
    return root.$t(k)
  }, key)
}

function watchPlannerPost(page) {
  const state = { count: 0 }
  const onReq = (req) => {
    if (req.url().endsWith(PLANNER_URL) && req.method() === 'POST') state.count += 1
  }
  page.on('request', onReq)
  state.stop = () => page.off('request', onReq)
  return state
}

// Drive the two reservable selects (type, then item) the way the
// admin would; the page renders exactly two <select> until the modal
// opens. Waits for the by-item GET the item-select watcher fires.
async function selectTypeAndItem(page) {
  const typeSel = page.locator('select').first()
  const itemSel = page.locator('select').nth(1)
  await expect(typeSel.locator('option[value="gpus"]')).toHaveCount(1, { timeout: 15000 })
  await typeSel.selectOption('gpus')
  await expect(itemSel.locator(`option[value="${GPU_ITEM}"]`)).toHaveCount(1, {
    timeout: 15000,
  })
  const byItem = page.waitForResponse(
    (r) => BY_ITEM_RE.test(r.url()) && r.request().method() === 'GET',
    { timeout: 15000 },
  )
  await itemSel.selectOption(GPU_ITEM)
  await byItem
  await expect(page.locator('#vuecal').first()).toBeVisible({ timeout: 15000 })
}

// Open PlanningModal in 'create' mode through Vuex with prefilled
// local times — vue-cal split-day drag is fragile to drive raw (same
// rationale as the bookings specs).
async function openCreateModal(page, startMs, endMs) {
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
      $store.dispatch('eventPlanningModalData', {
        type: 'create',
        subitemId: null,
        startDate: fmtDate(startMs),
        startTime: fmtTime(startMs),
        endDate: fmtDate(endMs),
        endTime: fmtTime(endMs),
      })
      $store.dispatch('showPlanningModal', true)
    },
    { startMs, endMs },
  )
  await page.locator('#eventModal').waitFor({ state: 'visible', timeout: 5000 })
  // The modalShow watcher fetches the profile options.
  await expect(
    page.locator(`#eventModal #subitemId option[value="${PROFILE}"]`),
  ).toHaveCount(1, { timeout: 10000 })
  await page.locator('#eventModal #subitemId').selectOption(PROFILE)
}

async function pressCreate(page) {
  await page.locator('#eventModal .modal-footer button.btn-primary').click()
}

// The Vue 2 planning store does not re-fetch after create; re-run the
// exact fetch the item-select watcher would, then the calendar paints.
async function refetchPlanning(page, startMs, endMs) {
  const byItem = page.waitForResponse(
    (r) => BY_ITEM_RE.test(r.url()) && r.request().method() === 'GET',
    { timeout: 15000 },
  )
  await page.evaluate(
    ({ startMs, endMs }) => {
      const root = document.getElementById('app')?.__vue__
      root.$store.dispatch('fetchPlanning', {
        itemId: 'e2e-gpu-planning',
        start: new Date(startMs - 6 * 3600 * 1000).toISOString(),
        end: new Date(endMs + 6 * 3600 * 1000).toISOString(),
      })
    },
    { startMs, endMs },
  )
  await byItem
}

// listAllPlans is authoritative; isolate this test's plans by device
// and window overlap (per-worker windows are disjoint).
async function plansInWindow(client, startMs, endMs) {
  const all = (await unwrap(listAllPlans({ client })).catch(() => [])) || []
  return all.filter((p) => {
    if (p.item_id !== GPU_ITEM) return false
    const s = new Date(p.start).getTime()
    const e = new Date(p.end).getTime()
    return s < endMs && e > startMs
  })
}

// =================================================================
// Admin planning (serial — single shared dedicated device)
// =================================================================

test.describe('Vue 2 — Planning (admin — serial)', () => {
  test.describe.configure({ mode: 'serial' })

  // Login once per worker (worker-scoped admin context); each test
  // gets a fresh tab from it — no per-test login.
  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    await cleanupTrackedResources(apiv4Admin, testInfo)
  })

  // ---------------------------------------------------------------
  // P1: an administrator creates a planning.
  // ---------------------------------------------------------------
  test('P1 admin creates a planning', async ({ authenticatedPage: page, apiv4Admin: apiv4 }, testInfo) => {
    const { startMs, endMs } = planWindow(testInfo.workerIndex, /* slot */ 0)

    await page.goto('/planning')
    await selectTypeAndItem(page)

    await openCreateModal(page, startMs, endMs)
    const post = page.waitForResponse(
      (r) => r.url().endsWith(PLANNER_URL) && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await pressCreate(page)
    expect((await post).status(), 'create planning POST must succeed').toBeLessThan(400)

    await expect(page.locator('#eventModal')).toBeHidden({ timeout: 5000 })
    await expect(page.locator('.snotifyToast.snotify-error')).toHaveCount(0)

    // Authoritative: exactly one plan on the device for this window.
    const plans = await plansInWindow(apiv4, startMs, endMs)
    expect(plans, 'one planning must be persisted').toHaveLength(1)
    track(testInfo, 'plan-id', plans[0].id)

    // Frontend: after an explicit refetch exactly one block is painted
    // and it displays the persisted data (PlanningUtils.parseEvent
    // title = "<subitem> (<units> units)").
    await refetchPlanning(page, startMs, endMs)
    const block = page.locator(`#vuecal .vuecal__event.unavailable:has-text("${PROFILE}")`)
    await expect(block).toHaveCount(1, { timeout: 10000 })
    await expect(block.first()).toBeVisible()
    await expect(block.first(), 'block shows the profile').toContainText(PROFILE)
    await expect(block.first(), 'block shows the units').toContainText(
      String(plans[0].units),
    )
  })

  // ---------------------------------------------------------------
  // P1b: a window in the past is blocked client-side (no POST).
  // ---------------------------------------------------------------
  test('P1b a past window is rejected client-side', async ({ authenticatedPage: page }, testInfo) => {
    await page.goto('/planning')
    await selectTypeAndItem(page)

    const pastStart = Date.now() - 60 * 60 * 1000
    const post = watchPlannerPost(page)
    await openCreateModal(page, pastStart, pastStart + 20 * 60 * 1000)
    await pressCreate(page)

    const expected = await appI18n(page, 'components.bookings.errors.past-booking')
    await expect(
      page.locator('.snotifyToast.snotify-info .snotifyToast__body').first(),
    ).toContainText(expected, { timeout: 5000 })
    expect(post.count, 'no POST for a past window').toBe(0)
    await expect(page.locator('#eventModal')).toBeVisible()
    post.stop()
  })

  // ---------------------------------------------------------------
  // P2: an administrator deletes a planning.
  // ---------------------------------------------------------------
  test('P2 admin deletes a planning', async ({ authenticatedPage: page, apiv4Admin: apiv4 }, testInfo) => {
    const { startMs, endMs } = planWindow(testInfo.workerIndex, /* slot */ 60)
    await createPlanAndTrack(apiv4, testInfo, {
      item_type: 'gpus',
      item_id: GPU_ITEM,
      subitem_id: PROFILE,
      start: new Date(startMs).toISOString(),
      end: new Date(endMs).toISOString(),
    })

    await page.goto('/planning')
    await selectTypeAndItem(page)

    const block = page
      .locator(`#vuecal .vuecal__event.unavailable:has-text("${PROFILE}")`)
      .first()
    await expect(block).toBeVisible({ timeout: 10000 })

    // Click the block → edit modal with Delete; confirm via snotify prompt.
    await block.click()
    await expect(page.locator('#eventModal')).toBeVisible({ timeout: 5000 })
    const del = page.waitForResponse(
      (r) =>
        new RegExp(`${PLANNER_URL}/`).test(r.url()) && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await page.locator('#eventModal .modal-footer button.btn-outline-danger').click()
    const yes = await appI18n(page, 'messages.yes')
    await page.locator('.snotifyToast button', { hasText: yes }).first().click()
    expect((await del).status(), 'delete planning must succeed').toBeLessThan(400)

    await expect(page.locator('#eventModal')).toBeHidden({ timeout: 5000 })
    await expect(page.locator('.snotifyToast.snotify-error')).toHaveCount(0)
    expect(await plansInWindow(apiv4, startMs, endMs), 'planning must be gone').toHaveLength(
      0,
    )

    // Frontend: after a refetch the block is no longer shown to the
    // admin (the store does not remove it on delete without a refetch).
    await refetchPlanning(page, startMs, endMs)
    await expect(
      page.locator(`#vuecal .vuecal__event.unavailable:has-text("${PROFILE}")`),
      'the deleted planning must disappear from the calendar',
    ).toHaveCount(0, { timeout: 10000 })
  })

  // ---------------------------------------------------------------
  // P3: a planning created contiguous to another's end is joined
  //     into a single planning (not a second row).
  // ---------------------------------------------------------------
  test('P3 a contiguous planning is joined into one', async ({ authenticatedPage: page, apiv4Admin: apiv4 }, testInfo) => {
    const base = planWindow(testInfo.workerIndex, /* slot */ 120, /* dur */ 30)
    const aStart = base.startMs
    const aEnd = base.startMs + 30 * 60 * 1000
    const bStart = aEnd // contiguous
    const bEnd = aEnd + 30 * 60 * 1000

    const planA = await createPlanAndTrack(apiv4, testInfo, {
      item_type: 'gpus',
      item_id: GPU_ITEM,
      subitem_id: PROFILE,
      start: new Date(aStart).toISOString(),
      end: new Date(aEnd).toISOString(),
    })

    await page.goto('/planning')
    await selectTypeAndItem(page)

    await openCreateModal(page, bStart, bEnd)
    const post = page.waitForResponse(
      (r) => r.url().endsWith(PLANNER_URL) && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await pressCreate(page)
    expect((await post).status(), 'contiguous create POST must succeed').toBeLessThan(400)
    await expect(page.locator('#eventModal')).toBeHidden({ timeout: 5000 })

    // Authoritative: the two plannings merged into one spanning A→B.
    const plans = await plansInWindow(apiv4, aStart, bEnd)
    expect(plans, 'contiguous plannings must merge into one').toHaveLength(1)
    expect(plans[0].id, 'the surviving plan is the existing one (A)').toBe(planA.id)
    expect(
      new Date(plans[0].end).getTime(),
      'A must be stretched to B end',
    ).toBeGreaterThan(aEnd)

    await refetchPlanning(page, aStart, bEnd)
    await expect(
      page.locator(`#vuecal .vuecal__event.unavailable:has-text("${PROFILE}")`),
      'a single merged block, no seam at A end',
    ).toHaveCount(1, { timeout: 10000 })
  })

  // ---------------------------------------------------------------
  // P3 control: a non-adjacent planning stays a separate row.
  // ---------------------------------------------------------------
  test('P3 control a non-adjacent planning stays separate', async ({
    authenticatedPage: page,
    apiv4Admin: apiv4,
  }, testInfo) => {
    const base = planWindow(testInfo.workerIndex, /* slot */ 180, /* dur */ 30)
    const aStart = base.startMs
    const aEnd = base.startMs + 30 * 60 * 1000
    const bStart = aEnd + 15 * 60 * 1000 // real 15-min gap
    const bEnd = bStart + 30 * 60 * 1000

    await createPlanAndTrack(apiv4, testInfo, {
      item_type: 'gpus',
      item_id: GPU_ITEM,
      subitem_id: PROFILE,
      start: new Date(aStart).toISOString(),
      end: new Date(aEnd).toISOString(),
    })

    await page.goto('/planning')
    await selectTypeAndItem(page)

    await openCreateModal(page, bStart, bEnd)
    const post = page.waitForResponse(
      (r) => r.url().endsWith(PLANNER_URL) && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await pressCreate(page)
    expect((await post).status(), 'non-adjacent create POST must succeed').toBeLessThan(400)
    await expect(page.locator('#eventModal')).toBeHidden({ timeout: 5000 })

    const plans = await plansInWindow(apiv4, aStart, bEnd)
    expect(plans, 'a real gap must keep two separate plannings').toHaveLength(2)
    for (const p of plans) track(testInfo, 'plan-id', p.id)

    await refetchPlanning(page, aStart, bEnd)
    await expect(
      page.locator(`#vuecal .vuecal__event.unavailable:has-text("${PROFILE}")`),
      'two distinct blocks',
    ).toHaveCount(2, { timeout: 10000 })
  })
})
