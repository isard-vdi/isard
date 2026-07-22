// Drives the Storage admin flows on /isard-admin/admin/domains/render/Storage.
// Mirrors testing/e2e/specs/webapp/storage.md — each `test(...)` corresponds
// to a numbered scenario in that spec.
//
// Conventions:
//   - Three fixtures provide seed data: Seed A (non-UUID id, row-level tests),
//     Seed B (UUID id, all modal-based action tests), Seed C (UUID id, delete test).
//   - The e2e environment runs a real hypervisor (CI starts one; local has one
//     too), but the seeds have NO physical disk file. So a disk operation the
//     hypervisor actually executes (Find, Increase, Move, Sparsify, Disconnect,
//     Windows Registry, derived Create) does not no-op: it scans, finds nothing
//     and marks the storage `deleted` (or spawns a wedged task) in <1s,
//     corrupting the shared seed for later tests. Every such op a test really
//     *fires* against a shared seed is stubbed in beforeEach (see below) — the
//     test verifies the API call fires and the modal closes/notifies without
//     letting the side effect wreck shared state. The Cancel-path tests just open
//     and dismiss the modal, so they never reach the hypervisor.
//   - S24 (derivatives-blocked) builds its own fixture at runtime via the apiv4
//     SDK: a real parent + 2 derived children (unattached create works here), so
//     `has-derivatives` returns 2 and the Move/WinReg/Increase guards trip.

import { test, expect } from '../../fixtures/apiv4/index.js'
import {
  adminStorageDelete,
  adminStorageSearchInfo,
  createStorage,
  getStorageHasDerivatives,
} from '../../src/gen/apiv4/sdk.gen'

const SEED_A = 'storage-template-test-001'
const SEED_B = 'e2e00000-0000-0000-0000-000000000001'
const SEED_C = 'e2e00000-0000-0000-0000-000000000002'
const STORAGE_URL = '/isard-admin/admin/domains/render/Storage'

async function deleteStorageViaApi(client, storageId) {
  await adminStorageDelete({
    client,
    path: { storage_id: storageId },
  }).catch(() => {})
}

// A storage is a fresh, deletable seed only when it is `ready` with no in-flight
// task. The diskless e2e env never completes the async delete task, so a prior
// attempt leaves Seed C in `maintenance` and/or with a pending `task` — and the
// webapp DELETE then returns 428 precondition_required. Used to skip (not fail)
// S23 on a retry / un-reseeded run instead of hammering a non-deletable row.
async function storageDeletableViaApi(client, storageId) {
  const result = await adminStorageSearchInfo({
    client,
    path: { storage_id: storageId },
  }).catch(() => null)
  if (!result || (result.response?.status ?? 500) >= 400) return false
  const data = result.data ?? {}
  return data.status === 'ready' && !data.task
}

// S24 fixture helpers. These go through the apiv4 SDK client (apiv4Admin), which
// uses its own bearer-auth request context — NOT the page's network — so they are
// not touched by the beforeEach `page.route` create-stub. That lets S24 build REAL
// disks (a parent + 2 derived children) while S19's UI-driven derive stays stubbed.
async function createStorageViaApi(client, { parent = '', usage = 'desktop' } = {}) {
  const res = await createStorage({
    client,
    path: { priority: 'default' },
    body: {
      usage,
      storage_type: 'qcow2',
      parent,
      size: '1G',
      user_id: 'local-default-admin-admin',
    },
  }).catch(() => null)
  if (!res || (res.response?.status ?? 500) >= 400) return null
  return res.data?.storage_id ?? null
}

async function waitStorageReadyViaApi(client, storageId, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const res = await adminStorageSearchInfo({ client, path: { storage_id: storageId } }).catch(() => null)
    const status = res?.data?.status
    if (status === 'ready') return true
    if (status === 'failed' || status === 'deleted') return false
    await new Promise((r) => setTimeout(r, 1500))
  }
  return false
}

async function waitDerivativesViaApi(client, storageId, want, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const res = await getStorageHasDerivatives({ client, path: { storage_id: storageId } }).catch(() => null)
    if ((res?.data?.derivatives ?? 0) >= want) return true
    await new Promise((r) => setTimeout(r, 1000))
  }
  return false
}

async function gotoStorage(page) {
  await page.goto(STORAGE_URL)
  await page
    .locator('#storage_wrapper, .dataTables_wrapper:has(#storage)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  // Collapse pagination so all seeded rows are visible
  await page.evaluate(() => {
    const t = $('#storage').DataTable()
    if (t && typeof t.page?.len === 'function') t.page.len(-1).draw(false)
  })
}

async function waitForSeedARow(page) {
  const row = page.locator(`#storage tbody tr[id="${SEED_A}"]`)
  await row.waitFor({ state: 'visible', timeout: 15000 })
  return row
}

async function openSearchModalFor(page, storageId) {
  await page.locator('#storage-uuid-search').fill(storageId)
  const searchResp = page.waitForResponse(
    (r) =>
      r.url().includes('/api/v4/admin/item/storage/search-info/') &&
      r.request().method() === 'GET',
    { timeout: 15000 },
  )
  await page.locator('#storage-uuid-search-btn').click()
  await searchResp
  const modal = page.locator('#modalSearchStorage')
  await modal.waitFor({ state: 'visible', timeout: 10000 })
  return modal
}

async function openModalForSeedB(page) {
  return openSearchModalFor(page, SEED_B)
}

async function clickPnotifyOk(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^ok$/i })
    .first()
    .click({ timeout: 5000 })
}

test.describe('Admin Storage — webapp', () => {
  // No leftovers to clean in beforeAll — seeds are static DB records.
  // S23 creates a runtime storage tracked via testInfo annotation; afterEach
  // deletes it if the test left it behind.
  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    const ids = testInfo.annotations
      .filter((a) => a.type === 'storage-id')
      .map((a) => a.description)
    for (const id of ids) {
      await deleteStorageViaApi(apiv4Admin, id)
    }
  })

  // The e2e environment has no physical disk files, so any disk operation that
  // the Online hypervisor actually runs against a seed flips it to `deleted`
  // (the scan finds no file) and poisons every later test that needs that seed
  // `ready`. The spec puts these results out of scope ("operations are
  // triggered and the API call is verified; the resulting status transition is
  // not awaited"). Stub the destructive ops that some test really *fires*
  // against a shared seed so the call and its notification still happen without
  // the side effect:
  //   - find  (S7 on Seed A, S22 on Seed B) → would mark the seed `deleted`,
  //     breaking S9, S15, S20, S21 and S10's row lookup.
  //   - increase (S18 on Seed B) → fires a real resize task that marks Seed B
  //     `deleted`, disabling its modal action buttons and breaking S19/S20/S21.
  //   - batch sparsify (S9 on selected rows, S10 global-no-filter) → calls
  //     storage.sparsify() which set_maintenance("sparsify") on EVERY selected
  //     ready storage, including Seed A and Seed B. With fullyParallel workers
  //     this flips the shared seeds out of `ready` mid-run, so the modal
  //     disables their action buttons (storage.js: status !== "ready") and
  //     every Seed B action test (S16–S22) times out clicking a disabled
  //     button. S9/S10 only assert the call fired, so stubbing keeps them green.
  //   - batch find (S9 Ok branch) → PUT /items/storage/find on the filtered
  //     rows. S9 filters by /isard/templates, which matches Seed A and Seed B,
  //     so a real find would scan, find no disk and mark them `deleted`. Stub it
  //     so S9 can exercise the Ok branch (call fires + success PNotify) safely.
  //   - virt-win-reg (S17 valid-file branch) → PUT /item/storage/<id>/virt-win-reg
  //     on Seed B. The real op set_maintenance + scans the (missing) disk, so stub
  //     it so S17 can verify the valid-file Send fires and the modal closes.
  //   - sparsify (singular, S20 Send) → PUT /item/storage/<id>/sparsify/priority
  //     on Seed B. set_maintenance("sparsify") flips it out of `ready`; stub so
  //     S20 can verify Send fires and the modal closes.
  //   - disconnect (S21 Send) → PUT /item/storage/<id>/disconnect/priority on
  //     Seed B. disconnect_chain() set_maintenance("disconnect") flips it out of
  //     `ready`; stub so S21 can verify Send fires and the modal closes.
  //   - move (S16 Send) → PUT /item/storage/<id>/move/by-path (or rsync/to-path).
  //     The real op set_maintenance + scans the missing disk and flips Seed B out
  //     of `ready`; stub so S16 can verify Send fires and the modal closes.
  //   - create/derive (S19 Send) → POST /item/storage/priority/<priority> with a
  //     `parent`. A real derive spawns a child storage record (and, diskless, a
  //     wedged task) that pollutes shared state and gives Seed B a derivative; stub
  //     so S19 can verify the POST fires and the modal closes. (S11's empty-form
  //     test is Parsley-blocked and never POSTs, so this route is inert for it.)
  // Matches singular `/item/storage/<id>/...` and the batch find/sparsify; DELETE
  // (S23 on disposable Seed C) is not stubbed since that test asserts the real
  // deletion. Direct apiv4 SDK calls (afterEach cleanup, S23 search-info) go
  // through page.request, which page.route does not intercept.
  test.beforeEach(async ({ authenticatedPage: page }) => {
    const stubOk = (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ task_id: 'e2e-stub' }),
      })
    await page.route(/\/api\/v4\/item\/storage\/[^/]+\/find(\?|$)/, stubOk)
    await page.route(/\/api\/v4\/item\/storage\/[^/]+\/priority\/[^/]+\/increase\/[0-9]+(\?|$)/, stubOk)
    await page.route(/\/api\/v4\/item\/storage\/[^/]+\/virt-win-reg\//, stubOk)
    await page.route(/\/api\/v4\/item\/storage\/[^/]+\/sparsify\//, stubOk)
    await page.route(/\/api\/v4\/item\/storage\/[^/]+\/disconnect\//, stubOk)
    await page.route(/\/api\/v4\/items\/storage\/sparsify(\/|\?|$)/, stubOk)
    await page.route(/\/api\/v4\/items\/storage\/find(\/|\?|$)/, stubOk)
    await page.route(/\/api\/v4\/item\/storage\/[^/]+\/move\//, stubOk)
    await page.route(/\/api\/v4\/item\/storage\/[^/]+\/rsync\//, stubOk)
    // Create POST: stub ONLY the derive case (body carries a `parent` — S19), whose
    // real run would spawn a child storage record off Seed B and give it a
    // derivative. The unattached create (no parent — S11b) must reach the real API
    // so it exercises the unattached-create path and returns a real storage_id to
    // clean up. (S11's empty-form submit is Parsley-blocked and never POSTs, so this
    // route is irrelevant to it.)
    await page.route(/\/api\/v4\/item\/storage\/priority\/[^/]+(\?|$)/, (route) => {
      let parent = ''
      try {
        parent = JSON.parse(route.request().postData() || '{}').parent
      } catch {
        /* non-JSON body — let it through */
      }
      return parent ? stubOk(route) : route.continue()
    })
  })

  // -------------------------------------------------------------------
  // Scenario 1 — page loads and the three table panels render
  // -------------------------------------------------------------------
  test('S1: page loads and the three table panels render', async ({ authenticatedPage: page }) => {
    const readyResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/storage/by-status/ready') &&
        r.request().method() === 'POST',
      { timeout: 20000 },
    )
    await page.goto(STORAGE_URL)
    const resp = await readyResp
    expect(resp.status()).toBeLessThan(500)

    await expect(page.locator('h3').filter({ hasText: 'Storage files' }).first()).toBeVisible()

    // Ready table: show all rows (pagination defaults to 10; env may have many rows)
    const storageWrapper = page.locator('#storage_wrapper, .dataTables_wrapper:has(#storage)').first()
    await storageWrapper.waitFor({ state: 'visible', timeout: 15000 })
    await page.evaluate(() => {
      const t = $('#storage').DataTable()
      if (t && typeof t.page?.len === 'function') t.page.len(-1).draw(false)
    })
    await expect(page.locator(`#storage tbody tr[id="${SEED_A}"]`)).toBeVisible({ timeout: 10000 })

    // Maintenance panel
    await expect(
      page.locator('h3').filter({ hasText: /Storage files in maintenance/ }),
    ).toBeVisible()

    // Other status panel
    const statusDropdown = page.locator('#status')
    await expect(statusDropdown).toBeVisible()
    await expect(statusDropdown).toBeEnabled()
    const optionCount = await statusDropdown.locator('option').count()
    expect(optionCount).toBeGreaterThan(1)

    // UUID duplicates panel
    await expect(page.locator('#uuid_status')).toBeVisible()
    await expect(page.locator('#uuid_status')).toBeEnabled()
  })

  // -------------------------------------------------------------------
  // Scenario 1b — Seed A row renders the expected value in every column
  // -------------------------------------------------------------------
  test('S1b: Seed A row renders correct data and admin action buttons', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)
    const row = await waitForSeedARow(page)

    // Column content checks via text assertions on td cells
    await expect(row.locator('td').filter({ hasText: 'ready' }).first()).toBeVisible()
    await expect(row.locator('td').filter({ hasText: '/isard/templates' }).first()).toBeVisible()
    await expect(row.locator('td').filter({ hasText: SEED_A }).first()).toBeVisible()
    await expect(row.locator('td').filter({ hasText: 'qcow2' }).first()).toBeVisible()

    // Admin action buttons
    await expect(row.locator('.btn-find')).toBeVisible()
    await expect(row.locator('.btn-delete-scheduler')).toBeVisible()
    await expect(row.locator('.btn-retry-task')).toHaveCount(0)
    await expect(row.locator('.btn-delete-orphan')).toHaveCount(0)
  })

  // -------------------------------------------------------------------
  // Scenario 1c — Category filter is added automatically on page load
  // -------------------------------------------------------------------
  test('S1c: category filter is auto-added on page load', async ({ authenticatedPage: page }) => {
    await page.goto(STORAGE_URL)
    // Wait for the filter box to appear
    const filterBox = page.locator('#filter-category')
    await filterBox.waitFor({ state: 'visible', timeout: 15000 })

    // Category Select2 is populated
    await expect(page.locator('#filter-category #category')).toBeVisible()

    // "default" is pre-selected — check via the underlying select value
    const selectedVals = await page.evaluate(() => $('#filter-category #category').val() ?? [])
    const arr = Array.isArray(selectedVals) ? selectedVals : [selectedVals]
    expect(arr).toContainEqual(expect.stringContaining('default'))
    await expect(page.locator('#filter-select option[value="category"]')).not.toBeAttached()
  })

  // -------------------------------------------------------------------
  // Scenario 1d — Adding a path filter shows clickable options
  // -------------------------------------------------------------------
  test('S1d: adding a path filter populates Select2 from table data', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)
    await waitForSeedARow(page)

    // Select "Path" from the filter dropdown
    await page.locator('#filter-select').selectOption('path')

    // The Path filter box appears with operator selector and Select2
    const filterPath = page.locator('#filter-path')
    await filterPath.waitFor({ state: 'visible', timeout: 10000 })
    await expect(filterPath.locator('#operator-path')).toBeVisible()
    await expect(filterPath.locator('.select2-container')).toBeVisible()

    // Check that /isard/templates is among the options (populated from table data)
    const pathOptions = await page.evaluate(() =>
      $('#filter-path #path option').map(function () { return $(this).val() }).get()
    )
    expect(pathOptions).toContain('/isard/templates')

    // "Path" is removed from the add-filter dropdown
    await expect(page.locator('#filter-select option[value="path"]')).not.toBeAttached()
  })

  // -------------------------------------------------------------------
  // Scenario 1e — Search with "is" operator filters the Ready table
  // -------------------------------------------------------------------
  test('S1e: path "is" operator narrows the Ready table', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)
    await waitForSeedARow(page)

    // Add path filter
    await page.locator('#filter-select').selectOption('path')
    const filterPath = page.locator('#filter-path')
    await filterPath.waitFor({ state: 'visible', timeout: 10000 })

    // Set "/isard/templates" via jQuery (more reliable than Select2 UI interaction)
    await page.evaluate(() => {
      var opt = new Option('/isard/templates', '/isard/templates', true, true)
      $('#filter-path #path').append(opt).trigger('change')
    })
    await filterPath.locator('#operator-path').selectOption('is')

    // Click Search
    await page.locator('#btn-search').click()

    // Seed A (a /isard/templates disk) remains visible
    await expect(page.locator(`#storage tbody tr[id="${SEED_A}"]`)).toBeVisible({ timeout: 5000 })

    // Prove the filter NARROWS, not just "Seed A survived": every visible row must
    // be a /isard/templates disk (non-matching paths excluded). toPass() retries
    // while the server-side DataTable redraws; count-independent so it tolerates
    // the fluctuating dev-data row totals.
    await expect(async () => {
      const total = await page.locator('#storage tbody tr').count()
      const matching = await page.locator('#storage tbody tr', { hasText: '/isard/templates' }).count()
      expect(total).toBeGreaterThan(0)
      expect(matching).toBe(total)
    }).toPass({ timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 1f — Operator "is not" excludes the selected path value
  // -------------------------------------------------------------------
  test('S1f: path "is not" operator hides Seed A row', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)
    await waitForSeedARow(page)

    // Add path filter with "is not" operator
    await page.locator('#filter-select').selectOption('path')
    const filterPath = page.locator('#filter-path')
    await filterPath.waitFor({ state: 'visible', timeout: 10000 })

    await page.evaluate(() => {
      var opt = new Option('/isard/templates', '/isard/templates', true, true)
      $('#filter-path #path').append(opt).trigger('change')
    })
    await filterPath.locator('#operator-path').selectOption('is not')
    await page.locator('#btn-search').click()

    // Seed A row should be hidden (excluded by "is not /isard/templates")
    await expect(page.locator(`#storage tbody tr[id="${SEED_A}"]`)).toBeHidden({ timeout: 5000 })

    // Symmetric to S1e: with "is not", NO visible row may be a /isard/templates
    // disk, while non-matching rows (e.g. /isard/groups) remain. toPass() retries
    // through the redraw; count-independent so it tolerates dev-data row flux.
    await expect(async () => {
      const total = await page.locator('#storage tbody tr').count()
      const matching = await page.locator('#storage tbody tr', { hasText: '/isard/templates' }).count()
      expect(total).toBeGreaterThan(0)
      expect(matching).toBe(0)
    }).toPass({ timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 1g — Clear button removes all filter boxes
  // -------------------------------------------------------------------
  test('S1g: clear button removes all filters and restores dropdown', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)
    await waitForSeedARow(page)

    // Add a path filter in addition to the default category filter
    await page.locator('#filter-select').selectOption('path')
    await page.locator('#filter-path').waitFor({ state: 'visible', timeout: 10000 })

    // Click Clear
    await page.locator('#btn-clear').click()

    // All filter boxes removed
    await expect(page.locator('#filter-category')).not.toBeAttached()
    await expect(page.locator('#filter-path')).not.toBeAttached()

    // Exactly one option per filter is restored to the dropdown.
    await expect(page.locator('#filter-select option[value="category"]')).toHaveCount(1)
    await expect(page.locator('#filter-select option[value="path"]')).toHaveCount(1)
    await expect(page.locator('#filter-select option[value="user"]')).toHaveCount(1)
    await expect(page.locator('#filter-select option[value="parent"]')).toHaveCount(1)

    // Table still shows Seed A
    await expect(page.locator(`#storage tbody tr[id="${SEED_A}"]`)).toBeVisible({ timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 1h — Individual × removes one filter only
  // -------------------------------------------------------------------
  test('S1h: individual × removes one filter and restores its dropdown option', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)
    await waitForSeedARow(page)

    // Add Path and User filters
    await page.locator('#filter-select').selectOption('path')
    await page.locator('#filter-path').waitFor({ state: 'visible', timeout: 10000 })
    await page.locator('#filter-select').selectOption('user')
    await page.locator('#filter-user').waitFor({ state: 'visible', timeout: 10000 })

    // Delete only the Path filter via its × button
    await page.locator('#filter-path .btn-delete-filter').click()

    // Path filter box gone, User filter intact
    await expect(page.locator('#filter-path')).not.toBeAttached()
    await expect(page.locator('#filter-user')).toBeVisible()

    // Path option restored in dropdown; User option still absent
    await expect(page.locator('#filter-select option[value="path"]')).toBeAttached()
    await expect(page.locator('#filter-select option[value="user"]')).not.toBeAttached()
  })

  // -------------------------------------------------------------------
  // Scenario 1i — Reload repopulates non-category filter options
  // -------------------------------------------------------------------
  test('S1i: reload button repopulates User filter Select2', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)
    await waitForSeedARow(page)

    // Add User filter
    await page.locator('#filter-select').selectOption('user')
    const filterUser = page.locator('#filter-user')
    await filterUser.waitFor({ state: 'visible', timeout: 10000 })

    // Click Reload and observe table redraws (no crash from the known
    // domains_table bug — if a JS error is thrown, the assertion below fails)
    await page.locator('#btn-reload').click()

    // Ready table still renders Seed A after reload
    await expect(page.locator(`#storage tbody tr[id="${SEED_A}"]`)).toBeVisible({ timeout: 15000 })

    // User filter Select2 is still present (repopulated)
    await expect(filterUser.locator('.select2-container')).toBeVisible()
  })

  // -------------------------------------------------------------------
  // Scenario 2 — UUID search bar blocks an invalid UUID
  // -------------------------------------------------------------------
  test('S2: UUID search bar rejects an invalid UUID', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)

    await page.locator('#storage-uuid-search').fill('not-a-valid-uuid')
    await page.locator('#storage-uuid-search-btn').click()

    // PNotify error about invalid UUID format
    const pnotify = page.locator('.ui-pnotify').filter({ hasText: /invalid uuid/i })
    await pnotify.waitFor({ state: 'visible', timeout: 5000 })

    // Modal must not open
    await expect(page.locator('#modalSearchStorage')).not.toBeVisible()
  })

  // -------------------------------------------------------------------
  // Scenario 3 — UUID search bar opens the modal for a known storage
  // -------------------------------------------------------------------
  test('S3: UUID search opens modal for Seed B', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)

    const searchResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/storage/search-info/') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await page.locator('#storage-uuid-search').fill(SEED_B)
    await page.locator('#storage-uuid-search-btn').click()
    const resp = await searchResp
    expect(resp.status()).toBeLessThan(400)

    const modal = page.locator('#modalSearchStorage')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#storage-info')).toBeVisible()
    await expect(modal.locator('#storage-actions')).toBeVisible()

    // Close modal
    await modal.locator('[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 4 — UUID search shows "not found" for an unknown storage
  // -------------------------------------------------------------------
  test('S4: UUID search shows error for unknown UUID', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)

    const searchResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/storage/search-info/') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await page.locator('#storage-uuid-search').fill('00000000-0000-0000-0000-000000000000')
    await page.locator('#storage-uuid-search-btn').click()
    const resp = await searchResp
    expect(resp.status()).toBe(404)

    // PNotify error
    const pnotify = page.locator('.ui-pnotify').filter({ hasText: /not found|error/i }).first()
    await pnotify.waitFor({ state: 'visible', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 5 — row info icon opens the search modal pre-populated
  // -------------------------------------------------------------------
  // Seed B is used here because openStorageSearchModal validates UUID format —
  // Seed A's non-UUID id would be rejected by isValidStorageUUID and no API
  // call would be made.
  test('S5: row info icon opens modal pre-populated with Seed B id', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)
    const row = page.locator(`#storage tbody tr[id="${SEED_B}"]`)
    await row.waitFor({ state: 'visible', timeout: 10000 })

    const searchResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/storage/search-info/') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await row.locator('#btn-info').click()
    await searchResp

    const modal = page.locator('#modalSearchStorage')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Storage ID field pre-populated with Seed B's UUID
    await expect(modal.locator('#storage-id')).toHaveValue(SEED_B)

    // Info and actions sections visible
    await expect(modal.locator('#storage-info')).toBeVisible()
    await expect(modal.locator('#storage-actions')).toBeVisible()

    // Close
    await modal.locator('[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 6 — row detail expands the backing chain and UUID subtables
  // -------------------------------------------------------------------
  test('S6: row detail expand shows backing chain subtable', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)
    const row = await waitForSeedARow(page)

    const parentsResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_A}/parents`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await row.locator('#btn-details').click()
    await parentsResp

    // Child DataTable rendered
    const childTable = page.locator(`[id="cl${SEED_A}"]`)
    await childTable.waitFor({ state: 'visible', timeout: 10000 })

    // Storage actions button present in expanded area (admin only)
    const actionsBtn = page.locator(`.btn-storage-actions[data-id="${SEED_A}"]`).first()
    await expect(actionsBtn).toBeVisible({ timeout: 5000 })

    // Collapse by clicking expand button again
    await row.locator('#btn-details').click()
    await childTable.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 7 — Find action enqueues a task and shows success notification
  // -------------------------------------------------------------------
  test('S7: find row button enqueues a find task', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)
    const row = await waitForSeedARow(page)

    const findResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_A}/find`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await row.locator('.btn-find').click()
    const resp = await findResp
    expect(resp.status()).toBeLessThan(400)

    const pnotify = page.locator('.ui-pnotify').filter({ hasText: /find task started/i })
    await pnotify.waitFor({ state: 'visible', timeout: 5000 })

    // Still on the storage page
    expect(page.url()).toContain('Storage')
  })

  // -------------------------------------------------------------------
  // Scenario 8 — Other status dropdown populates and loads a table
  // -------------------------------------------------------------------
  test('S8: Other status dropdown loads the storagesOtherTable', async ({ authenticatedPage: page }) => {
    await gotoStorage(page)

    const statusDropdown = page.locator('#status')
    await expect(statusDropdown).toBeEnabled()

    // Pick any non-default option (index 1)
    const options = await statusDropdown.locator('option').allInnerTexts()
    const firstReal = options.find((o) => o.toLowerCase() !== 'select status')
    test.skip(!firstReal, 'no non-default status option available')

    const tableResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/storage/by-status/') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await statusDropdown.selectOption({ label: firstReal })
    const resp = await tableResp
    expect(resp.status()).toBeLessThan(500)

    // Table wrapper rendered (even if empty)
    await page.locator('#storagesOtherTable_wrapper, .dataTables_wrapper:has(#storagesOtherTable)').first().waitFor({
      state: 'visible',
      timeout: 10000,
    })
  })

  // -------------------------------------------------------------------
  // Scenario 9 — Global action with a filter applied: N-rows confirmation
  // -------------------------------------------------------------------
  test('S9: global action with filter — Ok fires the bulk find (md Then 2)', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    await waitForSeedARow(page)

    // Apply a global DataTables search so mactionsStorage takes the N-rows path
    await page.evaluate(() => {
      $('#storage').DataTable().search('/isard/templates').draw()
    })

    // Select "Find & update disks" from global actions
    await page
      .locator('.mactionsStorage[selectedTableId="storage"]')
      .selectOption('find')

    // PNotify confirmation dialog (md Then 1)
    const pnotify = page.locator('.ui-pnotify').filter({ hasText: /confirmation needed/i })
    await pnotify.waitFor({ state: 'visible', timeout: 10000 })

    // Ok → bulk find fires. The batch find is stubbed in beforeEach so the call
    // and its success PNotify still happen without flipping the matching seeds
    // (Seed A/B are /isard/templates) to `deleted`.
    const findResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/items/storage/find') &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)

    // md Then 2a + 2b: PUT fired and returned < 400
    expect((await findResp).status()).toBeLessThan(400)
    // md Then 2c: success PNotify (storage.js: "Action queued: find" / "Queued …")
    await page
      .locator('.ui-pnotify')
      .filter({ hasText: /queued/i })
      .waitFor({ state: 'visible', timeout: 5000 })
    // md Then 2d: dropdown resets to "Select action"
    await expect(
      page.locator('.mactionsStorage[selectedTableId="storage"]'),
    ).toHaveValue('none')
  })

  // -------------------------------------------------------------------
  // Scenario 9b — Cancel branch of the filtered global action (md Then 3)
  // -------------------------------------------------------------------
  test('S9b: global action with filter — Cancel fires no API and resets (md Then 3)', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    await waitForSeedARow(page)

    await page.evaluate(() => {
      $('#storage').DataTable().search('/isard/templates').draw()
    })

    // No bulk find request may fire on the Cancel path
    const findReq = page
      .waitForRequest((r) => /\/items\/storage\/find/.test(r.url()), { timeout: 2000 })
      .catch(() => null)

    await page
      .locator('.mactionsStorage[selectedTableId="storage"]')
      .selectOption('find')

    const pnotify = page.locator('.ui-pnotify').filter({ hasText: /confirmation needed/i })
    await pnotify.waitFor({ state: 'visible', timeout: 10000 })

    // Cancel
    await page
      .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /cancel/i })
      .first()
      .click({ timeout: 5000 })

    // md Then 3: no API call, dropdown resets to "Select action"
    expect(await findReq).toBeNull()
    await expect(
      page.locator('.mactionsStorage[selectedTableId="storage"]'),
    ).toHaveValue('none')
  })

  // -------------------------------------------------------------------
  // Scenario 10 — Global action with no filter: text confirmation
  // -------------------------------------------------------------------
  test('S10: global action with no filter requires "I\'m aware" text', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    await waitForSeedARow(page)

    // No global search — clear any previous
    await page.evaluate(() => {
      $('#storage').DataTable().search('').draw()
    })

    await page
      .locator('.mactionsStorage[selectedTableId="storage"]')
      .selectOption('sparsify')

    // "I'm aware" dialog
    const pnotify = page.locator('.ui-pnotify').filter({ hasText: /warning/i })
    await pnotify.waitFor({ state: 'visible', timeout: 10000 })

    // Type wrong phrase — API must NOT be called
    const textInput = pnotify.locator('input[type="text"]')
    await textInput.fill('wrong phrase')

    // Actively assert no bulk sparsify request leaves the page: storage.js only
    // proceeds when the phrase matches exactly "I'm aware". (A page.route stub is
    // registered in beforeEach, so a wrong-phrase request would still be visible
    // here — this guards against the confirmation gate regressing.)
    const sparsifyReq = page
      .waitForRequest((r) => /\/items\/storage\/sparsify/.test(r.url()), { timeout: 2000 })
      .catch(() => null)
    await clickPnotifyOk(page)
    expect(await sparsifyReq).toBeNull()
    // Dropdown still visible = no redirect/crash
    await expect(page.locator('.mactionsStorage[selectedTableId="storage"]')).toBeVisible()

    // The wrong-phrase "Ok" leaves the warning pnotify open: storage.js only
    // calls notice.remove() when the phrase matches "I'm aware". If we don't
    // close it, reopening sparsify stacks a second pnotify and clickPnotifyOk's
    // .first() would click this stale one. Dismiss it via its Cancel button
    // (which calls notice.remove()) so the next "Ok" hits the fresh dialog.
    await pnotify
      .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^cancel$/i })
      .click({ timeout: 5000 })
    await pnotify.waitFor({ state: 'hidden', timeout: 5000 })

    // Reopen and type the correct phrase
    await page
      .locator('.mactionsStorage[selectedTableId="storage"]')
      .selectOption('sparsify')
    const pnotify2 = page.locator('.ui-pnotify').filter({ hasText: /warning/i }).last()
    await pnotify2.waitFor({ state: 'visible', timeout: 10000 })
    const textInput2 = pnotify2.locator('input[type="text"]')
    await textInput2.fill("I'm aware")

    const sparsifyResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/items/storage/sparsify/') &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    const resp = await sparsifyResp
    // The bulk sparsify is stubbed in beforeEach (a real one would set_maintenance
    // on every ready seed and corrupt shared state), so it always returns 200.
    // This confirms the "I'm aware" phrase actually fired the bulk sparsify PUT.
    expect(resp.status()).toBeLessThan(400)
  })

  // -------------------------------------------------------------------
  // Scenario 11 — Create storage modal opens and validates required fields
  // -------------------------------------------------------------------
  test('S11: create storage modal opens and Parsley blocks empty form', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)

    await page.locator('.btn-add-storage').click()
    const modal = page.locator('#modalCreateStorage')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('h4').filter({ hasText: /add new unattached storage disk/i })).toBeVisible()

    // User search field (Select2 with min 2 chars)
    await expect(modal.locator('#user')).toBeVisible()

    // Click Send without filling in required fields — Parsley blocks it
    await modal.locator('#send').click()
    // No API call: Parsley prevents submission; modal stays open
    await expect(modal).toBeVisible()

    // Close modal
    await modal.locator('[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // md Scenario 11, steps 4–5: filling a valid user/size/format and clicking Send
  // POSTs to /api/v4/item/storage/priority/<priority> and closes the modal on
  // success. Unattached create is now supported (create_new_storage builds a blank
  // disk when no parent is given, and the webapp sends `usage`/`parent`), so this
  // exercises the real create end-to-end. Unlike the derive case (S19, stubbed),
  // the unattached POST has an empty `parent` and falls through to the real API;
  // the created disk's id is captured from the response and deleted in afterEach.
  test('S11b: create storage Send posts an unattached disk and closes the modal', async ({
    authenticatedPage: page,
  }, testInfo) => {
    await gotoStorage(page)

    await page.locator('.btn-add-storage').click()
    const modal = page.locator('#modalCreateStorage')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('h4').filter({ hasText: /add new unattached storage disk/i })).toBeVisible()

    // Pick a valid owner. The #user Select2 searches users via AJAX (min 2 chars);
    // inject the option directly for determinism (mirrors S1e's path-filter approach)
    // so serializeObject sends a real user_id. Size (10) and format (qcow2) keep
    // their defaults.
    await page.evaluate((uid) => {
      var opt = new Option(uid, uid, true, true)
      $('#modalCreateStorage #user').append(opt).trigger('change')
    }, 'local-default-admin-admin')

    // md step 4: Send fires the real create POST (no parent → not stubbed).
    const createResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/item/storage/priority/') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await createResp
    expect(resp.status()).toBeLessThan(400)

    // Track the newly created disk so afterEach deletes it (md cleanup step 3).
    const body = await resp.json().catch(() => ({}))
    if (body.storage_id) {
      testInfo.annotations.push({ type: 'storage-id', description: body.storage_id })
    }

    // md step 4-5: success notification appears and the modal closes automatically.
    await page
      .locator('.ui-pnotify')
      .filter({ hasText: /task created/i })
      .waitFor({ state: 'visible', timeout: 5000 })
    await modal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 12 — Duplicated UUIDs section loads when a status is selected
  // -------------------------------------------------------------------
  test('S12: UUID duplicates section loads when "All" is selected', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)

    const tableResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/items/storage/storages_with_uuid') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await page.locator('#uuid_status').selectOption('all')
    await tableResp

    // storagesUUID table wrapper appears
    await page
      .locator('#storagesUUID_wrapper, .dataTables_wrapper:has(#storagesUUID)')
      .first()
      .waitFor({ state: 'visible', timeout: 10000 })

    // No JS crash — table visible even if empty
    const tbody = page.locator('#storagesUUID tbody')
    await expect(tbody).toBeVisible()
  })

  // -------------------------------------------------------------------
  // Scenario 13 — Maintenance table renders and shows progress column
  // -------------------------------------------------------------------
  test('S13: maintenance table renders with progress column', async ({ authenticatedPage: page }) => {
    const maintResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/storage/by-status/maintenance') &&
        r.request().method() === 'POST',
      { timeout: 20000 },
    )
    await page.goto(STORAGE_URL)
    await maintResp

    // Panel heading visible
    await expect(
      page.locator('h3').filter({ hasText: /Storage files in maintenance/ }),
    ).toBeVisible()

    // DataTable wrapper present
    await page
      .locator('#storagesMaintenance_wrapper, .dataTables_wrapper:has(#storagesMaintenance)')
      .first()
      .waitFor({ state: 'visible', timeout: 10000 })

    // Table renders without JS error (empty state is acceptable)
    await expect(page.locator('#storagesMaintenance tbody')).toBeVisible()

    // md Then 3: the Progress column (DataTable col `visible: status=="maintenance"`)
    // is shown in the maintenance table and hidden in the ready table.
    await expect(
      page.locator('#storagesMaintenance thead th', { hasText: 'Progress' }),
    ).toBeVisible()
    await expect(
      page.locator('#storage thead th', { hasText: 'Progress' }),
    ).toBeHidden()
  })

  // -------------------------------------------------------------------
  // Scenario 15 — Delete scheduler confirms and calls the scheduler endpoint
  // -------------------------------------------------------------------
  test('S15: delete scheduler button fires DELETE to scheduler endpoint', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const row = await waitForSeedARow(page)

    await row.locator('.btn-delete-scheduler').click()

    // PNotify confirmation dialog
    const pnotify = page.locator('.ui-pnotify').filter({ hasText: /confirmation needed/i })
    await pnotify.waitFor({ state: 'visible', timeout: 10000 })

    const deleteResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/scheduler/${SEED_A}.stg_action`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    const resp = await deleteResp
    // May 404 if scheduler entry didn't exist — that's acceptable
    expect(resp.status()).toBeDefined()

    // Either "Deleted" success or an error PNotify should appear
    await page.locator('.ui-pnotify').first().waitFor({ state: 'visible', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 16 — Move action: modal opens with pool options and Send fires
  // -------------------------------------------------------------------
  test('S16: move modal opens with pool options and Send fires the move API', async ({
    authenticatedPage: page,
  }) => {
    // The Move flow chains has-derivatives → info → by-path → storage-pools and
    // opens #modalMoveStorage inside the by-path call's .done(). The move op itself
    // is stubbed in beforeEach so firing Send does not flip Seed B out of `ready`.
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    // md Then 2-5: the action chains has-derivatives → info → by-path → storage-pools.
    const derivResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_B}/has-derivatives`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    const byPathResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/storage-pool/by-path') &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    const poolsResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/storage-pools') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await modal.locator('.btn-modal-move').click()
    await derivResp
    // md Then 4: by-path returns < 400 and populates the destination pool selector.
    expect((await byPathResp).status()).toBeLessThan(400)
    await poolsResp

    const moveModal = page.locator('#modalMoveStorage')
    await moveModal.waitFor({ state: 'visible', timeout: 10000 })

    // md Then 7: same-pool / different-pool radios are present
    await expect(moveModal.locator('#same_pool')).toBeAttached()
    await expect(moveModal.locator('#different_pool')).toBeAttached()

    // md Then 8: priority dropdown populated
    expect(await moveModal.locator('#priority option').count()).toBeGreaterThan(0)

    // md "Send path": the move requires a destination path (required field).
    // populateSelectByPool may yield only a disabled placeholder for the seed's
    // pool/category, so inject a concrete option to satisfy validation
    // deterministically (mirrors S1e's path-filter approach).
    await page.evaluate(() => {
      var opt = new Option('/isard/templates-moved', '/isard/templates-moved', true, true)
      $('#modalMoveStorageForm select[name="destination_path"]')
        .append(opt)
        .val('/isard/templates-moved')
        .trigger('change')
    })

    // Default radio (same pool) + default method (mv) → PUT /item/storage/<id>/move/by-path
    // (stubbed in beforeEach so Seed B isn't flipped to maintenance). Verify the call
    // fires and the modal closes on success.
    const moveResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_B}/move/by-path`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await moveModal.locator('#send').click()
    expect((await moveResp).status()).toBeLessThan(400)
    await page
      .locator('.ui-pnotify')
      .filter({ hasText: /task created/i })
      .waitFor({ state: 'visible', timeout: 5000 })
    await moveModal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 16b — Move Cancel closes without firing the move API (md Then 9)
  // -------------------------------------------------------------------
  test('S16b: move modal Cancel closes without any move API call (md Then 9)', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    await modal.locator('.btn-modal-move').click()
    const moveModal = page.locator('#modalMoveStorage')
    await moveModal.waitFor({ state: 'visible', timeout: 10000 })

    // No move/rsync request may fire on the Cancel path
    const moveReq = page
      .waitForRequest((r) => /\/item\/storage\/[^/]+\/(move|rsync)\//.test(r.url()), { timeout: 2000 })
      .catch(() => null)
    await moveModal.locator('[data-dismiss="modal"]').first().click()
    await moveModal.waitFor({ state: 'hidden', timeout: 5000 })
    expect(await moveReq).toBeNull()
  })

  // -------------------------------------------------------------------
  // Scenario 17 — Windows Registry action: modal validates the file
  // -------------------------------------------------------------------
  test('S17: windows registry modal validates file and sends a valid one', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    const derivResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_B}/has-derivatives`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await modal.locator('.btn-modal-virt_win_reg').click()
    await derivResp

    const winRegModal = page.locator('#modalVirtWinReg')
    await winRegModal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(
      winRegModal.locator('h4').filter({ hasText: /Apply Windows Registry Patch/i }),
    ).toBeVisible()

    // md step 5: Click Send without a file — Parsley blocks it
    await winRegModal.locator('#send').click()
    await expect(winRegModal).toBeVisible()

    // md step 6: wrong MIME type → "File must be a regedit file"
    await winRegModal.locator('#registry_file').setInputFiles({
      name: 'patch.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('not a reg file'),
    })
    await winRegModal.locator('#send').click()
    await page
      .locator('.ui-pnotify')
      .filter({ hasText: /regedit/i })
      .waitFor({ state: 'visible', timeout: 5000 })

    // md step 7: correct MIME but >1MB → "File size must be less than 1MB"
    await winRegModal.locator('#registry_file').setInputFiles({
      name: 'big.reg',
      mimeType: 'text/x-ms-regedit',
      buffer: Buffer.alloc(1 * 1024 * 1024 + 16),
    })
    await winRegModal.locator('#send').click()
    await page
      .locator('.ui-pnotify')
      .filter({ hasText: /size/i })
      .waitFor({ state: 'visible', timeout: 5000 })

    // md note "Send with a valid file": a valid .reg under 1MB fires
    // PUT /item/storage/<id>/virt-win-reg/priority/<priority> (stubbed in
    // beforeEach so Seed B isn't touched) and the modal closes on success.
    await winRegModal.locator('#registry_file').setInputFiles({
      name: 'patch.reg',
      mimeType: 'text/x-ms-regedit',
      buffer: Buffer.from('Windows Registry Editor Version 5.00\r\n'),
    })
    const winRegResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_B}/virt-win-reg/`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await winRegModal.locator('#send').click()
    expect((await winRegResp).status()).toBeLessThan(400)
    await page
      .locator('.ui-pnotify')
      .filter({ hasText: /task created/i })
      .waitFor({ state: 'visible', timeout: 5000 })
    await winRegModal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 18 — Increase action: modal opens with current size
  // -------------------------------------------------------------------
  test('S18: increase modal validates new-size and submits a valid increase', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    const derivResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_B}/has-derivatives`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await modal.locator('.btn-modal-increase').click()
    await derivResp

    const increaseModal = page.locator('#modalIncreaseStorage')
    await increaseModal.waitFor({ state: 'visible', timeout: 10000 })

    // Current size shown, never "NaN"
    const currentSizeText = await increaseModal.locator('#current-size').innerText()
    expect(currentSizeText).not.toMatch(/NaN/)

    // New-size input has min attribute set
    const minAttr = await increaseModal.locator('#new-size').getAttribute('min')
    expect(Number(minAttr)).toBeGreaterThanOrEqual(0)

    // `min` is the smallest VALID increase (floor(currentGB)+1), not a blocked
    // boundary: filling it would pass validation and fire a real increase that
    // closes the modal. Clear the field instead so the `required` rule trips
    // Parsley — value-independent and without mutating the seed.
    const increaseReq = page
      .waitForRequest((r) => /\/increase\//.test(r.url()), { timeout: 2000 })
      .catch(() => null)
    await increaseModal.locator('#new-size').fill('')
    await increaseModal.locator('#send').click()
    // Parsley blocks; modal stays open and no increase request is sent
    await expect(increaseModal).toBeVisible()
    expect(await increaseReq).toBeNull()

    // md step 9: a valid larger value fires the increase. `minAttr` is the
    // app's pre-filled value (⌊currentGB⌋+1, i.e. > current), so it passes
    // validation. The increase op is stubbed in beforeEach (a real resize would
    // touch Seed B's missing disk), so the call + success happen side-effect-free.
    await increaseModal.locator('#new-size').fill(minAttr)
    const increasePut = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_B}/priority/`) &&
        /\/increase\/\d+/.test(r.url()) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await increaseModal.locator('#send').click()
    expect((await increasePut).status()).toBeLessThan(400)
    await page
      .locator('.ui-pnotify')
      .filter({ hasText: /task created/i })
      .waitFor({ state: 'visible', timeout: 5000 })
    await increaseModal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 19 — Add Disk (derive) action: modal opens in derive mode
  // -------------------------------------------------------------------
  test('S19: add disk from modal opens create modal in derive mode and Send fires create', async ({
    authenticatedPage: page,
  }) => {
    // The derive flow populates the create modal from PUT /api/v4/storage-pool/by-path
    // and opens #modalCreateStorage in derive mode inside that call's .done(). The
    // derive create POST is stubbed in beforeEach so no real child storage is spawned
    // and Seed B does not gain a derivative.
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    await modal.locator('.btn-modal-create').click()

    const createModal = page.locator('#modalCreateStorage')
    await createModal.waitFor({ state: 'visible', timeout: 15000 })

    // md Then 3: the modal opens in "Create derived storage disk" mode
    await expect(
      createModal.locator('.modal-body h4').filter({ hasText: /create derived storage disk/i }),
    ).toBeVisible()
    // Parent ID pre-populated in the span
    await expect(createModal.locator('#storage_id')).toContainText(SEED_B)
    // Owner wrapper hidden in derive mode
    await expect(createModal.locator('#owner-wrapper')).toBeHidden()

    // md Then 4: Send POSTs /api/v4/item/storage/priority/<priority> with the parent
    // id in the body (stubbed in beforeEach). The derive form is valid out of the box
    // (retry defaults to 0, size to 10), so Send fires without filling anything.
    const createResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/item/storage/priority/') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await createModal.locator('#send').click()
    expect((await createResp).status()).toBeLessThan(400)
    await page
      .locator('.ui-pnotify')
      .filter({ hasText: /task created/i })
      .waitFor({ state: 'visible', timeout: 5000 })
    await createModal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 19b — Add Disk Cancel closes the create modal without firing create
  // -------------------------------------------------------------------
  test('S19b: add disk Cancel closes the create modal without firing create', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    await modal.locator('.btn-modal-create').click()
    const createModal = page.locator('#modalCreateStorage')
    await createModal.waitFor({ state: 'visible', timeout: 15000 })

    // No create POST may fire on the Cancel path
    const createReq = page
      .waitForRequest(
        (r) =>
          r.url().includes('/api/v4/item/storage/priority/') &&
          r.request().method() === 'POST',
        { timeout: 2000 },
      )
      .catch(() => null)
    await createModal.locator('[data-dismiss="modal"]').first().click()
    await createModal.waitFor({ state: 'hidden', timeout: 5000 })
    expect(await createReq).toBeNull()
  })

  // -------------------------------------------------------------------
  // Scenario 20 — Sparsify action: modal opens with priority selector
  // -------------------------------------------------------------------
  test('S20: sparsify modal opens and Send fires the sparsify (md Then 5-6)', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    await modal.locator('.btn-modal-sparsify').click()

    const sparsifyModal = page.locator('#modalSparsify')
    await sparsifyModal.waitFor({ state: 'visible', timeout: 10000 })

    // md Then 4: priority dropdown populated (Low/Default/High for admin)
    expect(await sparsifyModal.locator('#priority option').count()).toBeGreaterThan(0)

    // md Then 5-6: Send fires PUT /item/storage/<id>/sparsify/priority/<priority>
    // (stubbed in beforeEach so Seed B isn't flipped to maintenance), then a
    // success PNotify appears and the modal closes.
    const sparsifyResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_B}/sparsify/priority/`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await sparsifyModal.locator('#send').click()
    expect((await sparsifyResp).status()).toBeLessThan(400)
    await page
      .locator('.ui-pnotify')
      .filter({ hasText: /task created/i })
      .waitFor({ state: 'visible', timeout: 5000 })
    await sparsifyModal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 20b — Sparsify Cancel closes without firing the API (md Then 7)
  // -------------------------------------------------------------------
  test('S20b: sparsify Cancel closes without any API call (md Then 7)', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    await modal.locator('.btn-modal-sparsify').click()
    const sparsifyModal = page.locator('#modalSparsify')
    await sparsifyModal.waitFor({ state: 'visible', timeout: 10000 })

    // No sparsify request may fire on the Cancel path
    const sparsifyReq = page
      .waitForRequest((r) => /\/item\/storage\/[^/]+\/sparsify\//.test(r.url()), { timeout: 2000 })
      .catch(() => null)
    await sparsifyModal.locator('[data-dismiss="modal"]').first().click()
    await sparsifyModal.waitFor({ state: 'hidden', timeout: 5000 })
    expect(await sparsifyReq).toBeNull()
  })

  // -------------------------------------------------------------------
  // Scenario 21 — Disconnect action: modal opens and Send fires the API
  // -------------------------------------------------------------------
  test('S21: disconnect modal opens and Send fires the API (md Then 4)', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    await modal.locator('.btn-modal-disconnect').click()

    const disconnectModal = page.locator('#modalDisconnect')
    await disconnectModal.waitFor({ state: 'visible', timeout: 10000 })

    // md Then 3: priority dropdown populated
    expect(await disconnectModal.locator('#priority option').count()).toBeGreaterThan(0)

    // md Then 4: Send fires PUT /item/storage/<id>/disconnect/priority/<priority>
    // (stubbed in beforeEach so Seed B isn't flipped to maintenance). `retry`
    // defaults to 0, so the form is valid without filling anything.
    const disconnectResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_B}/disconnect/priority/`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await disconnectModal.locator('#send').click()
    expect((await disconnectResp).status()).toBeLessThan(400)
    await page
      .locator('.ui-pnotify')
      .filter({ hasText: /task created/i })
      .waitFor({ state: 'visible', timeout: 5000 })
    await disconnectModal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 21b — Disconnect Cancel closes without firing the API (md Then 5)
  // -------------------------------------------------------------------
  test('S21b: disconnect Cancel closes without any API call (md Then 5)', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    await modal.locator('.btn-modal-disconnect').click()
    const disconnectModal = page.locator('#modalDisconnect')
    await disconnectModal.waitFor({ state: 'visible', timeout: 10000 })

    // No disconnect request may fire on the Cancel path
    const disconnectReq = page
      .waitForRequest((r) => /\/item\/storage\/[^/]+\/disconnect\//.test(r.url()), { timeout: 2000 })
      .catch(() => null)
    await disconnectModal.locator('[data-dismiss="modal"]').first().click()
    await disconnectModal.waitFor({ state: 'hidden', timeout: 5000 })
    expect(await disconnectReq).toBeNull()
  })

  // -------------------------------------------------------------------
  // Scenario 22 — Find action from modal: direct API call, no secondary modal
  // -------------------------------------------------------------------
  test('S22: find from modal calls the find API and shows success PNotify', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    const findResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_B}/find`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await modal.locator('.btn-modal-find').click()
    const resp = await findResp
    expect(resp.status()).toBeLessThan(400)

    // md Then 1: the search modal closes
    await page.locator('#modalSearchStorage').waitFor({ state: 'hidden', timeout: 5000 })

    // md Then 3: success PNotify
    const pnotify = page.locator('.ui-pnotify').filter({ hasText: /find task started/i })
    await pnotify.waitFor({ state: 'visible', timeout: 5000 })

    // md Then 4: find is a direct API call — no secondary modal opens
    // (.modal.in is Bootstrap's "currently shown" marker; none should remain).
    await expect(page.locator('.modal.in')).toHaveCount(0)
  })

  // -------------------------------------------------------------------
  // Scenario 23 — Delete action from modal: confirmation and DELETE call
  // Uses Seed C so Seed B remains intact for other tests.
  // -------------------------------------------------------------------
  test('S23: delete from modal confirms and calls DELETE API', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    // Track Seed C for cleanup in afterEach (in case the delete fails mid-flow)
    testInfo.annotations.push({ type: 'storage-id', description: SEED_C })

    // Seed C is a single-use disposable row that THIS test deletes. populate
    // restores it on the next full-run reseed, but a Playwright retry does NOT
    // reseed. Because the async delete task wedges in the diskless env, a prior
    // attempt leaves Seed C non-`ready` / with a pending task, so a retry would
    // hit 428 precondition_required. Skip (don't fail) unless it is a fresh,
    // deletable seed (mirrors migrations.spec.js convention).
    test.skip(
      !(await storageDeletableViaApi(apiv4Admin, SEED_C)),
      `${SEED_C} not a fresh deletable seed (missing / non-ready / pending task) — consumed by a prior attempt or no reseed; review manually`,
    )

    await gotoStorage(page)

    // Open modal for Seed C
    await page.locator('#storage-uuid-search').fill(SEED_C)
    const searchResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/storage/search-info/') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await page.locator('#storage-uuid-search-btn').click()
    const sResp = await searchResp
    expect(sResp.status()).toBeLessThan(400)

    const modal = page.locator('#modalSearchStorage')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    const deleteResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/storage/${SEED_C}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await modal.locator('.btn-modal-delete').click()

    // md Then 2: confirmation PNotify (md Then 1: the search modal closes first)
    const pnotify = page.locator('.ui-pnotify').filter({ hasText: /confirmation needed/i })
    await pnotify.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal).toBeHidden()
    await clickPnotifyOk(page)

    const resp = await deleteResp
    expect(resp.status()).toBeLessThan(400)

    // Success PNotify — the UI confirmed and fired the DELETE. The physical row
    // removal is OUT OF SCOPE: task_delete() only flips the row to `maintenance`
    // synchronously and enqueues a worker task that never completes in the
    // diskless env (it would wedge with a pending task), so we do NOT poll for
    // the row to disappear — that's an async backend effect this suite doesn't
    // await. afterEach attempts the SDK cleanup; the next full-run reseed
    // restores Seed C.
    const successNotify = page.locator('.ui-pnotify').filter({ hasText: /deleted/i })
    await successNotify.waitFor({ state: 'visible', timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // Scenario 23b — Delete Cancel fires no DELETE (md Then 4)
  // Uses Seed B: Cancel deletes nothing, so the shared seed stays intact.
  // -------------------------------------------------------------------
  test('S23b: delete Cancel fires no DELETE and keeps the storage (md Then 4)', async ({
    authenticatedPage: page,
  }) => {
    await gotoStorage(page)
    const modal = await openModalForSeedB(page)

    await modal.locator('.btn-modal-delete').click()

    // Confirmation dialog appears (the search modal closes first)
    const pnotify = page.locator('.ui-pnotify').filter({ hasText: /confirmation needed/i })
    await pnotify.waitFor({ state: 'visible', timeout: 10000 })

    // No DELETE may fire on the Cancel path
    const deleteReq = page
      .waitForRequest(
        (r) => r.url().includes(`/api/v4/item/storage/${SEED_B}`) && r.request().method() === 'DELETE',
        { timeout: 2000 },
      )
      .catch(() => null)
    await pnotify
      .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /cancel/i })
      .first()
      .click({ timeout: 5000 })

    // md Then 4: no DELETE call, page remains unchanged (still on the storage page)
    expect(await deleteReq).toBeNull()
    await expect(page.locator('#storage-uuid-search')).toBeVisible()
  })

  // -------------------------------------------------------------------
  // Scenario 24 — Move / WinReg / Increase blocked when storage has derivatives
  // -------------------------------------------------------------------
  test('S24: move/winreg/increase are blocked when the storage has derivatives', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    // Building the parent+children fixture (real disks + polling) is slow.
    test.setTimeout(180000)

    // Build the fixture via the SDK: an unattached parent that reaches `ready`,
    // then 2 derived children so `has-derivatives` returns 2 (> 1) — the count the
    // webapp guards on. SDK calls bypass the beforeEach create-stub, so these are
    // REAL disks. If the env can't build them, skip (don't fail) like S23.
    const parentId = await createStorageViaApi(apiv4Admin, { parent: '' })
    test.skip(!parentId, 'could not create the parent storage in this env')
    // afterEach cleanup deletes annotated ids in order; children must go before the
    // parent, so push the parent first and unshift each child ahead of it.
    testInfo.annotations.push({ type: 'storage-id', description: parentId })

    const parentReady = await waitStorageReadyViaApi(apiv4Admin, parentId)
    test.skip(!parentReady, 'parent storage never reached `ready` in this env')

    for (let i = 0; i < 2; i++) {
      const childId = await createStorageViaApi(apiv4Admin, { parent: parentId })
      if (childId) testInfo.annotations.unshift({ type: 'storage-id', description: childId })
    }
    const hasTwo = await waitDerivativesViaApi(apiv4Admin, parentId, 2)
    test.skip(!hasTwo, 'could not build a parent with 2 derivatives in this env')

    await gotoStorage(page)

    // Each action triggers GET has-derivatives (not stubbed). With derivatives > 1
    // the webapp must surface the block PNotify and keep the action modal closed.
    const cases = [
      { btn: '.btn-modal-move', modal: '#modalMoveStorage', text: /this storage has derivatives/i },
      { btn: '.btn-modal-virt_win_reg', modal: '#modalVirtWinReg', text: /this storage has derivatives/i },
      {
        btn: '.btn-modal-increase',
        modal: '#modalIncreaseStorage',
        text: /size of disks with derivatives cannot be modified/i,
      },
    ]
    for (const c of cases) {
      // Clear any prior block PNotify so each assertion targets a fresh one.
      await page.evaluate(() => document.querySelectorAll('.ui-pnotify').forEach((e) => e.remove()))
      const modal = await openSearchModalFor(page, parentId)
      const derivResp = page.waitForResponse(
        (r) =>
          r.url().includes(`/api/v4/item/storage/${parentId}/has-derivatives`) &&
          r.request().method() === 'GET',
        { timeout: 15000 },
      )
      await modal.locator(c.btn).click()
      await derivResp
      // md Then 2: the block error PNotify appears…
      await page
        .locator('.ui-pnotify')
        .filter({ hasText: c.text })
        .first()
        .waitFor({ state: 'visible', timeout: 5000 })
      // md Then 3: …and the action modal does NOT open.
      await expect(page.locator(c.modal)).not.toBeVisible()
    }
  })
})
