// The disk-between-pools planner, not the user template migration of
// migrations.spec.js. The plan POST is stubbed: the assertions are on how the JS
// renders the totals, so they hold in an environment with no disks to plan.

import { test, expect } from '../../fixtures/apiv4/index.js'
import { bridgeAdminSession } from '../../fixtures/common.js'

const STORAGE_POOLS_URL = '/isard-admin/admin/storage_pools'

const POOLS = {
  storage_pools: [
    { id: 'e2e-pool-src', name: 'E2E Src Pool', mountpoint: '/isard/src' },
    { id: 'e2e-pool-dst', name: 'E2E Dst Pool', mountpoint: '/isard/dst' },
  ],
}

// Stub every read the page makes on open, plus the plan POST. `totals` is what the
// test wants the preview to render; each test overrides it via `planTotals`.
async function stubMigrationApis(page, planTotals) {
  const json = (body) => (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

  await page.route(/\/api\/v4\/storage-pools(\?|$)/, json(POOLS))
  await page.route(/\/api\/v4\/admin\/items\/categories(\?|$)/, json([]))
  await page.route(/\/api\/v4\/admin\/storage\/migrations(\?|$)/, json([]))
  await page.route(/\/api\/v4\/admin\/storage\/migrations\/path-prefixes/, json({ prefixes: [] }))
  await page.route(/\/api\/v4\/admin\/storage\/migrations\/plan(\?|$)/, json({ totals: planTotals }))
}

async function openNewMigrationModal(page) {
  await page.goto(STORAGE_POOLS_URL)
  await page.locator('.btn-mig-new').click()
  const modal = page.locator('#mig_new_modal')
  await modal.waitFor({ state: 'visible', timeout: 10000 })
  // The pool <select>s are filled from the stubbed /storage-pools on load.
  await expect(page.locator('#mig_src_pool option[value="e2e-pool-src"]')).toHaveCount(1)
  return modal
}

// Choose a valid whole-pool selection (source != destination) and force the
// dry-run, returning once the (stubbed) plan response has been rendered.
async function previewWholePoolPlan(page) {
  await page.selectOption('#mig_src_pool', 'e2e-pool-src')
  await page.selectOption('#mig_dst_pool', 'e2e-pool-dst')
  const planned = page.waitForResponse(
    (r) => r.url().includes('/admin/storage/migrations/plan') && r.request().method() === 'POST',
    { timeout: 15000 },
  )
  await page.locator('#mig_preview').click()
  await planned
  await expect(page.locator('#mig_sum_content')).toBeVisible()
}

test.describe('Admin Storage-pool migration — plan preview', () => {
  test('SM1: preview shows how many disks move, how many stay, and least-used-first order', async ({
    authenticatedPage: page,
  }) => {
    await stubMigrationApis(page, {
      items_total: 4,
      items_by_kind: { desktop: 3, template: 1 },
      bytes_by_kind: {},
      bytes_total: 0,
      not_moving_total: 2,
      not_moving_by_kind: { template: 2 },
      order: 'oldest_first',
      trees: 2,
    })
    await openNewMigrationModal(page)
    await previewWholePoolPlan(page)

    // N move: the total-files cell is the plan's items_total.
    await expect(page.locator('#mig_sum_total')).toHaveText('4')

    // M stay: the stay cell appears only when something stays, and carries the
    // per-kind breakdown. Its wrapping cell is hidden until then.
    const stay = page.locator('#mig_sum_stay')
    await expect(stay.locator('..')).toBeVisible()
    await expect(stay).toContainText('2')
    await expect(stay).toContainText('template')

    // order: oldest_first renders as the human label, and its line is shown.
    const order = page.locator('#mig_sum_order')
    await expect(order).toHaveText(/least-used first/)
    await expect(order.locator('..')).toBeVisible()
  })

  test('SM2: a plan with nothing left behind hides the stay cell and shows most-used-first', async ({
    authenticatedPage: page,
  }) => {
    await stubMigrationApis(page, {
      items_total: 5,
      items_by_kind: { desktop: 5 },
      bytes_by_kind: {},
      bytes_total: 0,
      not_moving_total: 0,
      not_moving_by_kind: {},
      order: 'newest_first',
      trees: 5,
    })
    await openNewMigrationModal(page)
    await previewWholePoolPlan(page)

    await expect(page.locator('#mig_sum_total')).toHaveText('5')
    // nothing stays -> the stay cell stays hidden.
    await expect(page.locator('#mig_sum_stay').locator('..')).toBeHidden()
    await expect(page.locator('#mig_sum_order')).toHaveText(/most-used first/)
  })
})

test.describe('Admin Storage-pool migration — permissions', () => {
  for (const roleKey of ['manager_e2e_01', 'user_e2e_01']) {
    test(`SM3: ${roleKey} is denied and redirected to login`, async ({
      page,
      users,
      categories,
      loginHelpers,
    }) => {
      await loginHelpers.login(page, users[roleKey], categories)
      await bridgeAdminSession(page)
      await page.goto(STORAGE_POOLS_URL)
      await expect(page).toHaveURL(/\/login/)
      await expect(page.locator('#mig_new_modal')).not.toBeAttached()
    })
  }
})
