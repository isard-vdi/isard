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

// The new-migration modal's "Source after copy" <select> (#mig_source_disposition:
// system | recycle_bin | delete). The API refuses "delete" without "verify", so the
// browser couples the two: picking delete ticks #mig_verify, a non-delete choice
// leaves it free. The create POST is stubbed; assertions read config.source_disposition
// and config.verify from the {selection, config} body the form builds.
test.describe('Admin Storage-pool migration — source disposition', () => {
  const MIGRATIONS_RE = /\/api\/v4\/admin\/storage\/migrations(\?|$)/
  const EMPTY_TOTALS = {
    items_total: 0,
    items_by_kind: {},
    bytes_by_kind: {},
    bytes_total: 0,
    not_moving_total: 0,
    not_moving_by_kind: {},
    order: 'none',
    trees: 0,
  }

  // Open the modal on a valid whole-pool selection, ready to press Create.
  async function openModalReadyToCreate(page) {
    await stubMigrationApis(page, EMPTY_TOTALS)
    await openNewMigrationModal(page)
    await page.selectOption('#mig_src_pool', 'e2e-pool-src')
    await page.selectOption('#mig_dst_pool', 'e2e-pool-dst')
  }

  // #mig_verify is skinned by iCheck (real <input> is opacity:0); drive the
  // underlying property and sync the skin, the way the other webapp specs do.
  async function setVerify(page, on) {
    await page.evaluate((checked) => {
      window.$('#mig_verify').prop('checked', checked).iCheck('update')
    }, on)
  }

  // Capture the {selection, config} body of the create POST for one click.
  async function createAndCaptureBody(page) {
    const req = page.waitForRequest(
      (r) => MIGRATIONS_RE.test(r.url()) && r.method() === 'POST',
      { timeout: 15000 },
    )
    await page.locator('#mig_create_only').click()
    return (await req).postDataJSON()
  }

  test('SM4: default disposition is "system"; create sends config.source_disposition:"system" + verify:true', async ({
    authenticatedPage: page,
  }) => {
    await openModalReadyToCreate(page)
    await expect(page.locator('#mig_source_disposition')).toHaveValue('system')
    await expect(page.locator('#mig_verify')).toBeChecked()

    const body = await createAndCaptureBody(page)
    expect(body.config.source_disposition).toBe('system')
    expect(body.config.verify).toBe(true)
  })

  test('SM5: choosing "delete" forces verify on; create sends source_disposition:"delete" + verify:true', async ({
    authenticatedPage: page,
  }) => {
    await openModalReadyToCreate(page)
    // start from verify OFF so the coupling has something to do
    await setVerify(page, false)
    await expect(page.locator('#mig_verify')).not.toBeChecked()

    await page.selectOption('#mig_source_disposition', 'delete')
    // delete cannot be sent without verify -> the change handler ticks it back on
    await expect(page.locator('#mig_verify')).toBeChecked()

    const body = await createAndCaptureBody(page)
    expect(body.config.source_disposition).toBe('delete')
    expect(body.config.verify).toBe(true)
  })

  test('SM6: a non-delete disposition ("recycle_bin") leaves verify free; create sends source_disposition:"recycle_bin" + verify:false', async ({
    authenticatedPage: page,
  }) => {
    await openModalReadyToCreate(page)
    await setVerify(page, false)
    await expect(page.locator('#mig_verify')).not.toBeChecked()

    await page.selectOption('#mig_source_disposition', 'recycle_bin')
    // recycle_bin does not require verify, so the coupling must NOT tick it on
    await expect(page.locator('#mig_verify')).not.toBeChecked()

    const body = await createAndCaptureBody(page)
    expect(body.config.source_disposition).toBe('recycle_bin')
    expect(body.config.verify).toBe(false)
  })
})

// The plan preview now lists the disks that will NOT move — each with its kind and
// which classifier held it back — as a tooltip on the "stay" cell (migRenderSummary
// reads totals.not_moving_disks, showing up to 8 lines then "… and N more").
// Bootstrap may park the text in title or data-original-title, so the assertions
// read whichever attribute holds it.
test.describe('Admin Storage-pool migration — non-moving disks breakdown', () => {
  async function stayTooltip(page) {
    return page
      .locator('#mig_sum_stay')
      .locator('..')
      .evaluate(
        (el) => (el.getAttribute('title') || '') + '\n' + (el.getAttribute('data-original-title') || ''),
      )
  }

  test('SM7: each non-moving disk is listed with its kind and classifier', async ({
    authenticatedPage: page,
  }) => {
    await stubMigrationApis(page, {
      items_total: 3,
      items_by_kind: { desktop: 3 },
      bytes_by_kind: {},
      bytes_total: 0,
      not_moving_total: 2,
      not_moving_by_kind: { template: 1, desktop: 1 },
      not_moving_disks: [
        { storage_id: 'e2e-stay-1', kind: 'template', classified_by: 'domain', reason: 'derivatives stay' },
        { storage_id: 'e2e-stay-2', kind: 'desktop', classified_by: 'category', reason: 'type not selected' },
      ],
      order: 'oldest_first',
      trees: 2,
    })
    await openNewMigrationModal(page)
    await previewWholePoolPlan(page)

    await expect(page.locator('#mig_sum_stay').locator('..')).toBeVisible()
    const tip = await stayTooltip(page)
    expect(tip).toContain('e2e-stay-1: template (by domain)')
    expect(tip).toContain('e2e-stay-2: desktop (by category)')
  })

  test('SM8: a long stay list is capped at 8 lines with "… and N more"', async ({
    authenticatedPage: page,
  }) => {
    const disks = Array.from({ length: 9 }, (_, i) => ({
      storage_id: `e2e-stay-${i + 1}`,
      kind: 'template',
      classified_by: 'domain',
      reason: 'x',
    }))
    await stubMigrationApis(page, {
      items_total: 12,
      items_by_kind: { desktop: 3 },
      bytes_by_kind: {},
      bytes_total: 0,
      not_moving_total: 9,
      not_moving_by_kind: { template: 9 },
      not_moving_disks: disks,
      order: 'oldest_first',
      trees: 3,
    })
    await openNewMigrationModal(page)
    await previewWholePoolPlan(page)

    const tip = await stayTooltip(page)
    expect(tip).toContain('e2e-stay-8: template (by domain)')
    expect(tip).not.toContain('e2e-stay-9:')
    expect(tip).toContain('… and 1 more')
  })
})

// The new-migration form gains #mig_on_damaged (pause | continue): what to do when a
// disk fails its integrity check mid-migration. migCreateConfig() sends the value as
// config.on_damaged in the create POST, which is stubbed so the assertions read the
// request body the form builds.
test.describe('Admin Storage-pool migration — on-damaged policy', () => {
  const MIGRATIONS_RE = /\/api\/v4\/admin\/storage\/migrations(\?|$)/
  const EMPTY_TOTALS = {
    items_total: 0,
    items_by_kind: {},
    bytes_by_kind: {},
    bytes_total: 0,
    not_moving_total: 0,
    not_moving_by_kind: {},
    order: 'none',
    trees: 0,
  }

  async function openModalReadyToCreate(page) {
    await stubMigrationApis(page, EMPTY_TOTALS)
    await openNewMigrationModal(page)
    await page.selectOption('#mig_src_pool', 'e2e-pool-src')
    await page.selectOption('#mig_dst_pool', 'e2e-pool-dst')
  }

  async function createAndCaptureBody(page) {
    const req = page.waitForRequest(
      (r) => MIGRATIONS_RE.test(r.url()) && r.method() === 'POST',
      { timeout: 15000 },
    )
    await page.locator('#mig_create_only').click()
    return (await req).postDataJSON()
  }

  test('SM9: default on-damaged is "pause"; create sends config.on_damaged:"pause"', async ({
    authenticatedPage: page,
  }) => {
    await openModalReadyToCreate(page)
    await expect(page.locator('#mig_on_damaged')).toHaveValue('pause')
    const body = await createAndCaptureBody(page)
    expect(body.config.on_damaged).toBe('pause')
  })

  test('SM10: choosing "continue" sends config.on_damaged:"continue"', async ({
    authenticatedPage: page,
  }) => {
    await openModalReadyToCreate(page)
    await page.selectOption('#mig_on_damaged', 'continue')
    const body = await createAndCaptureBody(page)
    expect(body.config.on_damaged).toBe('continue')
  })
})

// The per-job "Apply" form (fix/4242) sends only the fields that differ from the
// job's stored config (PUT /admin/storage/migrations/{id}/config), confirm()s a
// change that weakens a running job's guarantee and tags it confirm_weakening, and
// freezes verify once the job is live. The list, per-job detail and PUT are stubbed;
// the assertions read the PUT body the form builds.
test.describe('Admin Storage-pool migration — running-job config apply', () => {
  const GB = 1024 * 1024 * 1024
  const json = (body) => (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

  // A job whose config round-trips through the form, so a single edit is the only
  // field the diff sends. min_free is a whole number of GB so it survives the GB<->
  // bytes conversion unchanged.
  function job(id, status) {
    return {
      id,
      status,
      selection: { kind: 'pool', src_pool_id: 'e2e-pool-src', dst_pool_id: 'e2e-pool-dst', item_kinds: [] },
      config: {
        parallelism: 2,
        bwlimit_kbs: 0,
        verify: true,
        force_stop_desktops: false,
        recurring: false,
        rescan_cadence: 'edge_on_drain',
        failure_policy: 'retry_quarantine',
        quarantine_after: 3,
        max_bytes_per_occurrence: 0,
        min_free_bytes: 10 * GB,
      },
      totals: {},
      created_by: 'admin',
      created_at: 0,
      updated_at: 0,
    }
  }

  // Stub the page reads plus the migrations list/detail, and capture every PUT to a
  // job's /config into the returned array.
  async function stubJobs(page, jobs) {
    await stubMigrationApis(page, {})
    // the real list endpoint wraps rows as { migrations: [...] }
    await page.route(/\/api\/v4\/admin\/storage\/migrations(\?|$)/, json({ migrations: jobs }))
    const puts = []
    for (const j of jobs) {
      await page.route(new RegExp(`/api/v4/admin/storage/migrations/${j.id}(\\?|$)`), json(j))
      await page.route(new RegExp(`/api/v4/admin/storage/migrations/${j.id}/config`), (route) => {
        if (route.request().method() === 'PUT') puts.push(route.request().postDataJSON())
        return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
      })
    }
    return puts
  }

  // Open the page and expand one job's row so its Apply form is on screen.
  async function openJobForm(page, id) {
    await page.goto(STORAGE_POOLS_URL)
    const row = page.locator(`#migrations tr.mig-row[data-mig="${id}"]`)
    await row.waitFor({ state: 'visible', timeout: 10000 })
    await row.click()
    const form = page.locator(`form.mig-config[data-mig="${id}"]`)
    await form.waitFor({ state: 'visible', timeout: 10000 })
    return form
  }

  test('SM11: editing one field applies only that field (PUT carries just parallelism)', async ({
    authenticatedPage: page,
  }) => {
    await stubJobs(page, [job('mig-run', 'running')])
    const form = await openJobForm(page, 'mig-run')

    await form.locator('.cfg-parallel').fill('4')
    const putReq = page.waitForRequest(
      (r) => /\/migrations\/mig-run\/config/.test(r.url()) && r.method() === 'PUT',
      { timeout: 8000 },
    )
    await form.locator('.mig-config-apply').click()
    const body = (await putReq).postDataJSON()
    expect(Object.keys(body).sort()).toEqual(['parallelism'])
    expect(body.parallelism).toBe(4)
  })

  test('SM12: lowering keep-free weakens the job — confirmed, the PUT carries confirm_weakening', async ({
    authenticatedPage: page,
  }) => {
    await stubJobs(page, [job('mig-run', 'running')])
    const form = await openJobForm(page, 'mig-run')
    let dialogShown = false
    page.on('dialog', (d) => {
      dialogShown = true
      d.accept()
    })

    await form.locator('.cfg-minfree-gb').fill('5')
    const putReq = page.waitForRequest(
      (r) => /\/migrations\/mig-run\/config/.test(r.url()) && r.method() === 'PUT',
      { timeout: 8000 },
    )
    await form.locator('.mig-config-apply').click()
    const body = (await putReq).postDataJSON()
    expect(dialogShown).toBe(true)
    expect(Object.keys(body).sort()).toEqual(['confirm_weakening', 'min_free_bytes'])
    expect(body.confirm_weakening).toBe(true)
    expect(body.min_free_bytes).toBe(5 * GB)
  })

  test('SM13: rejecting the weakening confirmation sends no PUT', async ({
    authenticatedPage: page,
  }) => {
    const puts = await stubJobs(page, [job('mig-run', 'running')])
    const form = await openJobForm(page, 'mig-run')
    let dialogShown = false
    page.on('dialog', (d) => {
      dialogShown = true
      d.dismiss()
    })

    await form.locator('.cfg-minfree-gb').fill('5')
    await form.locator('.mig-config-apply').click()
    await page.waitForTimeout(1000)
    expect(dialogShown).toBe(true)
    expect(puts).toHaveLength(0)
  })

  test('SM14: verify is frozen on a running job and editable on a planned one', async ({
    authenticatedPage: page,
  }) => {
    await stubJobs(page, [job('mig-run', 'running'), job('mig-plan', 'planned')])
    await page.goto(STORAGE_POOLS_URL)

    const runRow = page.locator('#migrations tr.mig-row[data-mig="mig-run"]')
    await runRow.waitFor({ state: 'visible', timeout: 10000 })
    await runRow.click()
    await expect(page.locator('form.mig-config[data-mig="mig-run"] .cfg-verify')).toBeDisabled()

    const planRow = page.locator('#migrations tr.mig-row[data-mig="mig-plan"]')
    await planRow.click()
    await expect(page.locator('form.mig-config[data-mig="mig-plan"] .cfg-verify')).toBeEnabled()
  })
})
