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

  // Capture the plan + create POST bodies so the tests can assert what the form
  // actually sends, and return a usable migration object for create.
  function captureMigrationPosts(page, captured, planTotals) {
    const json = (body) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    page.route(/\/api\/v4\/admin\/storage\/migrations\/plan(\?|$)/, (route) => {
      captured.plan = route.request().postDataJSON()
      route.fulfill(json({ totals: planTotals || {} }))
    })
    page.route(/\/api\/v4\/admin\/storage\/migrations(\?|$)/, (route) => {
      if (route.request().method() === 'POST') {
        captured.create = route.request().postDataJSON()
        route.fulfill(json({ id: 'm-e2e', status: 'planned', config: captured.create.config }))
      } else {
        route.fulfill(json([]))
      }
    })
  }

  test('SM4: oldest_first + 7 days sends usage_age_days=7 on plan and create', async ({
    authenticatedPage: page,
  }) => {
    await stubMigrationApis(page, {})
    const captured = {}
    await captureMigrationPosts(page, captured, {
      items_total: 1, trees: 1, order: 'oldest_first', usage_age_days: 7,
      usage_age_excluded_trees: 3, items_by_kind: {}, bytes_by_kind: {}, bytes_total: 0,
    })
    await openNewMigrationModal(page)
    await page.selectOption('#mig_src_pool', 'e2e-pool-src')
    await page.selectOption('#mig_dst_pool', 'e2e-pool-dst')
    await page.selectOption('#mig_order', 'oldest_first')
    await page.fill('#mig_usage_age_value', '7')

    const planned = page.waitForResponse(
      (r) => r.url().includes('/migrations/plan') && r.request().method() === 'POST',
    )
    await page.locator('#mig_preview').click()
    await planned
    expect(captured.plan.config.usage_age_days).toBe(7)

    const created = page.waitForResponse(
      (r) => /\/migrations(\?|$)/.test(r.url()) && r.request().method() === 'POST',
    )
    await page.locator('#mig_create_only').click()
    await created
    expect(captured.create.config.usage_age_days).toBe(7)
  })

  test('SM5: the preview shows how many trees fall within the usage-age threshold', async ({
    authenticatedPage: page,
  }) => {
    await stubMigrationApis(page, {
      items_total: 2, trees: 2, order: 'oldest_first', usage_age_days: 7,
      usage_age_excluded_trees: 3, items_by_kind: { desktop: 2 }, bytes_by_kind: {}, bytes_total: 0,
    })
    await openNewMigrationModal(page)
    await page.selectOption('#mig_order', 'oldest_first')
    await page.fill('#mig_usage_age_value', '7')
    await previewWholePoolPlan(page)

    const line = page.locator('#mig_sum_usage_age')
    await expect(line.locator('..')).toBeVisible()
    await expect(line).toContainText('2 tree(s) within')
    await expect(line).toContainText('3 outside')
  })

  test('SM6: min_free_pct defaults to 10 on create and is changeable', async ({
    authenticatedPage: page,
  }) => {
    await stubMigrationApis(page, {})
    const captured = {}
    await captureMigrationPosts(page, captured, {})
    await openNewMigrationModal(page)
    await page.selectOption('#mig_src_pool', 'e2e-pool-src')
    await page.selectOption('#mig_dst_pool', 'e2e-pool-dst')

    let created = page.waitForResponse(
      (r) => /\/migrations(\?|$)/.test(r.url()) && r.request().method() === 'POST',
    )
    await page.locator('#mig_create_only').click()
    await created
    expect(captured.create.config.min_free_pct).toBe(10)

    await openNewMigrationModal(page)
    await page.selectOption('#mig_src_pool', 'e2e-pool-src')
    await page.selectOption('#mig_dst_pool', 'e2e-pool-dst')
    await page.fill('#mig_min_free_pct', '25')
    created = page.waitForResponse(
      (r) => /\/migrations(\?|$)/.test(r.url()) && r.request().method() === 'POST',
    )
    await page.locator('#mig_create_only').click()
    await created
    expect(captured.create.config.min_free_pct).toBe(25)
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

  // A post-upgrade job: config carries every MigrationConfigData default. Editing
  // one field must still diff to just that field (the defaults match current).
  function jobFull(id, status) {
    const j = job(id, status)
    j.config = {
      ...j.config,
      on_damaged: 'pause',
      source_disposition: 'system',
      min_free_pct: 10,
      order: 'none',
      usage_age_days: null,
      include_never_used: false,
      load_policy: { mode: 'static', parallelism_min: 1, parallelism_max: 4, pause_above: 0, baseline_window: 5 },
    }
    return j
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

// The list rows are stubbed (the assertions are on how the JS orders/renders the
// table, paginates a job's trees/disks and deletes), so they hold in an
// environment with no real migrations.
const json = (body) => (route) =>
  route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

function migRow(id, status, createdAt, lastActivityAt, totals) {
  return {
    id,
    status,
    selection: { kind: 'pool', src_pool_id: 'e2e-pool-src', dst_pool_id: 'e2e-pool-dst' },
    config: {},
    totals: Object.assign({ items_total: 0, state_counts: {} }, totals || {}),
    created_at: createdAt,
    last_activity_at: lastActivityAt,
    eta_seconds: null,
    current_window: null,
    recurring: false,
    days: [],
    next_run_seconds: null,
  }
}

// Stub the reads the pools page makes on open, plus the migration LIST.
async function stubPageAndList(page, migrations) {
  await page.route(/\/api\/v4\/storage-pools(\?|$)/, json(POOLS))
  await page.route(/\/api\/v4\/admin\/items\/categories(\?|$)/, json([]))
  await page.route(/\/api\/v4\/admin\/storage\/migrations\/path-prefixes/, json({ prefixes: [] }))
  await page.route(/\/api\/v4\/admin\/storage\/migrations\/plan(\?|$)/, json({ totals: {} }))
  await page.route(/\/api\/v4\/admin\/storage\/migrations(\?|$)/, json({ migrations }))
}

async function openPools(page, migrations) {
  await stubPageAndList(page, migrations)
  await page.goto(STORAGE_POOLS_URL)
  await expect(page.locator('#migrations tbody tr.mig-row')).toHaveCount(migrations.length)
}

test.describe('Admin Storage-pool migration — list, pagination and delete', () => {
  test('SM4: list is created-desc, shows both date columns, and re-sorts on click', async ({
    authenticatedPage: page,
  }) => {
    await openPools(page, [
      migRow('mig-old', 'completed', 1000, 1500, { items_total: 1, state_counts: { released: 1 } }),
      migRow('mig-new', 'completed', 3000, null, { items_total: 1, state_counts: { released: 1 } }),
    ])
    const rows = page.locator('#migrations tbody tr.mig-row')
    // default: newest created first
    await expect(rows.nth(0)).toHaveAttribute('data-mig', 'mig-new')
    await expect(rows.nth(1)).toHaveAttribute('data-mig', 'mig-old')
    // both date columns render; a missing last_activity shows the em dash
    await expect(page.locator('tr.mig-row[data-mig="mig-new"] td.mig-created')).not.toHaveText('—')
    await expect(page.locator('tr.mig-row[data-mig="mig-new"] td.mig-last-activity')).toHaveText('—')
    await expect(page.locator('tr.mig-row[data-mig="mig-old"] td.mig-last-activity')).not.toHaveText('—')
    // sort by last activity: mig-old (1500) before mig-new (missing sorts last)
    await page.locator('#migrations thead .mig-sort[data-sortkey="last-activity"]').click()
    await expect(rows.nth(0)).toHaveAttribute('data-mig', 'mig-old')
  })

  test('SM5: the list renders without a per-row GET /{id}', async ({ authenticatedPage: page }) => {
    let statusHits = 0
    // the per-job status is /migrations/<id> with no further segment
    await page.route(/\/admin\/storage\/migrations\/m1(\?|$)/, (route) => {
      statusHits++
      return json({})(route)
    })
    await openPools(page, [
      migRow('m1', 'planned', 2000, null, { items_total: 5, state_counts: { pending: 5 } }),
    ])
    await page.waitForTimeout(500)
    expect(statusHits).toBe(0)
  })

  test('SM6: expanding a job paginates/searches/filters trees; a tree lists its disks', async ({
    authenticatedPage: page,
  }) => {
    let lastTreesQuery = ''
    await page.route(/\/admin\/storage\/migrations\/m1\/trees(\?|$)/, (route) => {
      const u = new URL(route.request().url())
      lastTreesQuery = u.search
      const pg = parseInt(u.searchParams.get('page') || '1', 10)
      const start = (pg - 1) * 2
      const trees = [start, start + 1]
        .filter((i) => i < 6)
        .map((i) => ({
          tree_id: 't' + i, root_storage_id: 't' + i, derivative_templates: 0,
          desktops: 1, items_total: 1, done: 0, bytes_total: 10, state_counts: { pending: 1 },
        }))
      return json({ trees, total: 6, page: pg, per_page: 2 })(route)
    })
    await page.route(/\/admin\/storage\/migrations\/m1\/items(\?|$)/, (route) => {
      const tree = new URL(route.request().url()).searchParams.get('tree_id')
      return json({
        items: [{ storage_id: 'disk-' + tree, kind: 'desktop', state: 'pending', size_bytes: 10, error: null }],
        total: 1, page: 1, per_page: 50,
      })(route)
    })
    await openPools(page, [
      migRow('m1', 'running', 2000, 2500, { items_total: 6, trees: 6, state_counts: { pending: 6 } }),
    ])
    await page.locator('tr.mig-row[data-mig="m1"]').click()
    // page 1 = 2 trees of 6
    await expect(page.locator('tr.mig-tree[data-mig="m1"]')).toHaveCount(2)
    // the trees pager is the one directly in the panel body (a tree's disks table
    // has its own pager, so scope to avoid matching both)
    const treesPager = '.mig-trees[data-mig="m1"] > .mig-trees-body > .mig-pager'
    await expect(page.locator(treesPager)).toContainText('Page 1 / 3')
    // next page -> page=2 requested, t2 shown
    await page.locator(`${treesPager} .mig-page-next`).click()
    await expect.poll(() => lastTreesQuery).toContain('page=2')
    await expect(page.locator('tr.mig-tree[data-tree="t2"]')).toHaveCount(1)
    // search + state filter travel to the server (debounced); each resets to page 1
    await page.locator('.mig-trees[data-mig="m1"] .mig-tree-q').fill('needle')
    await expect.poll(() => lastTreesQuery).toContain('q=needle')
    await page.locator('.mig-trees[data-mig="m1"] .mig-tree-state').selectOption('moving')
    await expect.poll(() => lastTreesQuery).toContain('state=moving')
    // finally, a tree lists its disks on its own page (via /items?tree_id)
    await page.locator('tr.mig-tree[data-tree="t0"]').click()
    await expect(page.locator('tr.mig-disks[data-tree="t0"]')).toContainText('disk-t0')
  })

  test('SM7: delete a terminal job with confirm; cancel = no call; a live job has no delete', async ({
    authenticatedPage: page,
  }) => {
    let deletes = 0
    await page.route(/\/admin\/storage\/migrations\/done(\?|$)/, (route) => {
      if (route.request().method() === 'DELETE') {
        deletes++
        return json({ id: 'done', status: 'completed', deleted_items: 3 })(route)
      }
      return json({})(route)
    })
    // a completed job the server refuses (428) — the row must stay
    await page.route(/\/admin\/storage\/migrations\/stale(\?|$)/, (route) => {
      if (route.request().method() === 'DELETE') {
        return route.fulfill({
          status: 428, contentType: 'application/json',
          body: JSON.stringify({ error: 'precondition_required', description: 'is running', description_code: 'storage_migration_not_deletable' }),
        })
      }
      return json({})(route)
    })
    await openPools(page, [
      migRow('done', 'completed', 3000, 3100, { items_total: 3, state_counts: { released: 3 } }),
      migRow('stale', 'completed', 2000, 2100, { items_total: 2, state_counts: { released: 2 } }),
      migRow('run', 'running', 1000, 1100, { items_total: 3, state_counts: { moving: 3 } }),
    ])
    // a running (non-terminal) job offers no Delete; terminal ones do
    await expect(page.locator('tr.mig-row[data-mig="run"] .mig-delete')).toHaveCount(0)
    await expect(page.locator('tr.mig-row[data-mig="done"] .mig-delete')).toHaveCount(1)
    // dismiss the confirm -> no DELETE call
    page.once('dialog', (d) => d.dismiss())
    await page.locator('tr.mig-row[data-mig="done"] .mig-delete').click()
    await page.waitForTimeout(300)
    expect(deletes).toBe(0)
    // accept the confirm -> DELETE sent; the confirm states the status + disk count
    let confirmMsg = ''
    page.once('dialog', (d) => { confirmMsg = d.message(); d.accept() })
    await page.locator('tr.mig-row[data-mig="done"] .mig-delete').click()
    await expect.poll(() => deletes).toBe(1)
    expect(confirmMsg).toContain('completed')
    expect(confirmMsg).toContain('3')
    // a delete the server rejects with 428 leaves the row in place
    page.once('dialog', (d) => d.accept())
    await page.locator('tr.mig-row[data-mig="stale"] .mig-delete').click()
    await page.waitForTimeout(400)
    await expect(page.locator('tr.mig-row[data-mig="stale"]')).toHaveCount(1)
  })
})
