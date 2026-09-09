// Drives the template admin flows on /isard-admin/admin/domains/render/Templates.
// Mirrors testing/e2e/specs/webapp/templates.md — each test(...) corresponds to a
// numbered scenario in that spec.
//
// Conventions:
//   - Seed template: `Template Test Frontend` (id: SEED.id). Only one exists.
//   - Dynamically created templates are named e2e-tpl-<workerIndex>-<timestamp>
//     and tracked via testInfo.annotations (type 'tpl-name') so afterEach
//     cleans them up even on failure.
//   - No test mutates the shared seed. Every mutating scenario operates on its
//     own duplicate so tests stay isolated under parallel workers — the seed is
//     read-only, which removes the cross-worker write contention that made the
//     suite flaky in CI. Read-only scenarios (S1, S4, S6-cancel, S7, S10b, S11,
//     S12-cancel, S16, S17, S18, S19-cancel) still reference the seed directly.
//   - S9 uses managerE2EPage: with cross-category derivatives the frontend hides the
//     Stop-and-Delete button (#send) entirely, so the manager cannot fire DELETE.
//   - S13/S14 (forced/favourite hyp) skip gracefully when no hypervisors exist in the dev DB.

import { test, expect, apiv4ClientForPage, unwrap } from '../../fixtures/apiv4/index.js'
import {
  adminListDomains,
  duplicateTemplate,
  deleteTemplate,
  setTemplateEnabled,
  adminTableList,
  adminTableUpdate,
} from '../../src/gen/apiv4/sdk.gen'

const TEMPLATES_URL = '/isard-admin/admin/domains/render/Templates'

// ─── seed constants ────────────────────────────────────────────────────────────

const SEED = {
  id: 'template-test-001',
  name: 'Template Test Frontend',
  description: 'Test template used by deployment-test-001',
  user: 'local-default-admin-admin',
  category: 'default',
  group: 'default-default',
}

// A second user for change-owner tests (must differ from SEED.user and have role
// admin/manager — the backend rejects role "user" as a template owner).
const OTHER_USER_ID = 'f5a63886-ad76-40cf-b767-ddc1a253d3a6' // Manager Default / uid: manager01

// S9 seed: a template in category 'default' whose derivative tree contains a desktop
// in 'another' category. When a manager (also in 'default') calls tree_list, the
// backend masks cross-category items with category='-' / unselectable=true, which
// triggers hasCrossCategoryItems in the frontend and hides the Stop and Delete button.
const S9_SEED = {
  id: 'template-s9-seed',
  name: 'Template S9 Cross Category',
}

// ─── pure helpers ──────────────────────────────────────────────────────────────

function uniqueTplName(testInfo, suffix = '') {
  return `e2e-tpl-${testInfo.workerIndex}-${Date.now()}${suffix ? `-${suffix}` : ''}`
}

function trackTplName(testInfo, name) {
  testInfo.annotations.push({ type: 'tpl-name', description: name })
}

async function listTemplatesViaApi(client) {
  const data = await unwrap(
    adminListDomains({ client, body: { kind: 'template' } }),
  ).catch(() => [])
  return Array.isArray(data) ? data : []
}

async function findTemplateByName(client, name) {
  const all = await listTemplatesViaApi(client)
  return all.find((t) => t.name === name) ?? null
}

async function createDuplicateViaApi(client, { name, description = '', enabled = true }) {
  const body = await unwrap(
    duplicateTemplate({
      client,
      path: { template_id: SEED.id },
      body: { name, description, enabled, allowed: {} },
    }),
  )
  if (!body?.id) throw new Error(`duplicateTemplate missing id: ${JSON.stringify(body)}`)
  return { id: body.id, name }
}

async function deleteTemplateViaApi(client, templateId) {
  await deleteTemplate({ client, path: { template_id: templateId } }).catch(() => {})
}

async function setEnabledViaApi(client, templateId, enabled) {
  await setTemplateEnabled({
    client,
    path: { template_id: templateId },
    body: { enabled },
  }).catch(() => {})
}

async function listHypervisors(client) {
  const data = await unwrap(
    adminTableList({
      client,
      path: { table: 'hypervisors' },
      body: { pluck: ['id', 'hostname'] },
    }),
  ).catch(() => [])
  return Array.isArray(data) ? data : []
}

// Force a template's status back to "Stopped" via the admin table endpoint,
// bypassing the edit precondition. A successful /edit flips the domain
// Stopped→Updating (parse_domain_update) and this diskless e2e env has no
// engine to complete Updating→Stopped, so it stays stuck. S13/S14 issue two
// consecutive /edit calls (assign then remove) on the same template, so the
// status must be reset between them or the second edit fails with 428.
async function forceStopped(client, id) {
  await adminTableUpdate({
    client,
    path: { table: 'domains' },
    body: { id, status: 'Stopped' },
  }).catch(() => {})
}

// ─── page helpers ─────────────────────────────────────────────────────────────

async function gotoTemplates(page) {
  await page.goto(TEMPLATES_URL)
  await page
    .locator('.dataTables_wrapper:has(#domains), #domains_wrapper')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  await page
    .locator('#domains tbody tr:not(.dataTables_empty)')
    .first()
    .waitFor({ state: 'visible', timeout: 20000 })
  // Force a fresh server fetch (ajax.reload) with all rows visible (page.len
  // -1). Pass resolve as the reload callback — DataTables calls it only after
  // this specific reload's draw completes, avoiding the race where page.len(-1)
  // fires draw.dt asynchronously and resolves the promise with stale data.
  await page.evaluate(
    () =>
      new Promise((resolve) => {
        // eslint-disable-next-line no-undef
        const t = $('#domains').DataTable()
        if (!t || typeof t.ajax?.reload !== 'function') {
          resolve()
          return
        }
        if (typeof t.page?.len === 'function') t.page.len(-1)
        t.ajax.reload(resolve, false)
      }),
  )
}

function waitForRow(page, id) {
  return page.locator(`#domains tbody tr[id="${id}"]`)
}

async function findRow(page, id, maxAttempts = 3) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await gotoTemplates(page)
    const row = waitForRow(page, id)
    try {
      await expect(row).toBeVisible({ timeout: 10000 })
      return row
    } catch (err) {
      if (attempt === maxAttempts) throw err
    }
  }
}

// Navigates to the templates page once, then polls ajax.reload until the row
// is visible. Polling only the reload (not a full page.goto each time) is much
// cheaper and avoids exhausting the 40s budget in battery runs where each full
// navigation can take several seconds under backend load.
async function waitForDupInTable(page, id) {
  await gotoTemplates(page)
  await expect
    .poll(
      async () => {
        await page.evaluate(
          () =>
            new Promise((resolve) => {
              // eslint-disable-next-line no-undef
              const t = $('#domains').DataTable()
              if (!t || typeof t.ajax?.reload !== 'function') { resolve(); return }
              t.ajax.reload(resolve, false)
            }),
        )
        return await waitForRow(page, id).isVisible()
      },
      { timeout: 40000, intervals: [2000, 3000, 5000] },
    )
    .toBe(true)
  return waitForRow(page, id)
}

async function expandDetail(page, id) {
  const row = page.locator(`#domains tbody tr[id="${id}"]`)
  await row.waitFor({ state: 'visible', timeout: 15000 })
  const panel = page.locator(`[id="actions-${id}"]`)
  // A concurrent template_data socket event can call table.draw(false) immediately
  // after the expand click, destroying the child row before the panel is stable.
  // Re-click only when the panel is not visible, poll until it stays visible.
  await expect.poll(
    async () => {
      if (!await panel.isVisible()) {
        await row.locator('td.details-control button').first().click()
      }
      return panel.isVisible()
    },
    { timeout: 15000, intervals: [500, 1000, 2000] },
  ).toBe(true)
  return panel
}


async function clickPnotifyConfirm(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^(ok|yes|confirm)$/i })
    .first()
    .click({ timeout: 8000 })
}

async function clickPnotifyCancel(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /cancel/i })
    .first()
    .click({ timeout: 8000 })
}

// ─── describe ─────────────────────────────────────────────────────────────────

test.describe('Admin Templates — webapp', () => {
  test.beforeAll(async ({ authenticatedContext }) => {
    const page = await authenticatedContext.newPage()
    try {
      const client = apiv4ClientForPage(page)
      // Remove ALL stale e2e-tpl-* leftovers from any previous run or worker.
      // Scoping by workerIndex would leave orphans from workers that didn't
      // participate in the current run (e.g. after an aborted -j 4 run).
      const stale = (await listTemplatesViaApi(client)).filter(
        (t) => typeof t.name === 'string' && t.name.startsWith('e2e-tpl-'),
      )
      for (const t of stale) await deleteTemplateViaApi(client, t.id)
    } finally {
      await page.close()
    }
  })

  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    const names = testInfo.annotations
      .filter((a) => a.type === 'tpl-name')
      .map((a) => a.description)
    for (const name of names) {
      const t = await findTemplateByName(apiv4Admin, name).catch(() => null)
      if (t) await deleteTemplateViaApi(apiv4Admin, t.id)
    }
  })

  // Touch the API before every test so the worker session (5-min inactivity
  // timeout) does not expire between tests when the worker is busy with
  // other specs that make no authenticated API calls.
  test.beforeEach(async ({ apiv4Admin }) => {
    await listTemplatesViaApi(apiv4Admin).catch(() => {})
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S1 — templates table loads with expected columns
  // ──────────────────────────────────────────────────────────────────────────
  test('S1: templates DataTable loads with correct columns and seed row visible', async ({
    authenticatedPage: page,
  }) => {
    const tableResponse = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/items/domains') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await page.goto(TEMPLATES_URL)
    expect((await tableResponse).status()).toBeLessThan(400)
    await gotoTemplates(page)

    const thead = page.locator('#domains thead')
    for (const col of ['Name', 'Description', 'User', 'Category', 'Group', 'Enabled', 'Shares']) {
      await expect(thead).toContainText(col)
    }

    const row = waitForRow(page, SEED.id)
    await expect(row).toBeVisible({ timeout: 10000 })

    // Each row has expand and info-circle buttons.
    await expect(row.locator('td.details-control button')).toBeVisible()
    await expect(row.locator('td.info-control button[data-domain-info]')).toBeVisible()
    // Enabled checkbox is checked for the seed.
    await expect(row.locator('input#chk-enabled')).toBeChecked()
    // Shares btn-alloweds.
    await expect(row.locator('#btn-alloweds')).toBeVisible()

    // Toolbar controls.
    await expect(page.locator('#domain-uuid-search')).toBeVisible()
    await expect(page.locator('.btn-disabled')).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S2 — show / hide disabled templates toggle
  // ──────────────────────────────────────────────────────────────────────────
  test('S2: show/hide disabled button toggles disabled rows', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueTplName(testInfo, 's2')
    trackTplName(testInfo, name)
    const dup = await createDuplicateViaApi(apiv4Admin, { name })
    await setEnabledViaApi(apiv4Admin, dup.id, false)

    test.setTimeout(60000)
    await waitForDupInTable(page, dup.id)
    const toggleBtn = page.locator('.btn-disabled')
    const disabledRow = waitForRow(page, dup.id)

    // Initial state: view="false" in the HTML → DataTable shows ALL templates including
    // disabled ones. The button label "Hide Disabled" means "click to hide the disabled rows"
    // (the label describes the action, not the current visibility of disabled rows).
    await expect(toggleBtn).toContainText(/hide disabled/i)
    await expect(disabledRow).toBeVisible({ timeout: 5000 })

    // Click → view becomes 'true' → only enabled templates shown → disabled row hidden.
    await toggleBtn.click()
    await expect(disabledRow).toBeHidden({ timeout: 8000 })
    await expect(toggleBtn).toContainText(/view disabled/i)

    // Click again → view back to 'false' → all templates shown → disabled row reappears.
    await toggleBtn.click()
    await expect(disabledRow).toBeVisible({ timeout: 8000 })
    await expect(toggleBtn).toContainText(/hide disabled/i)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S3 — admin enables a disabled template
  // ──────────────────────────────────────────────────────────────────────────
  test('S3: enabling a disabled template via the Enabled checkbox', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueTplName(testInfo, 's3')
    trackTplName(testInfo, name)
    const dup = await createDuplicateViaApi(apiv4Admin, { name, enabled: false })

    test.setTimeout(60000)
    // Default state is view="false": all templates (including disabled) are shown.
    // No need to click btn-disabled — the disabled row is already visible.
    const row = await waitForDupInTable(page, dup.id)
    const checkbox = row.locator('input#chk-enabled')
    await expect(checkbox).not.toBeChecked()

    const enableResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/template/${dup.id}/set-enabled`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await checkbox.click()
    await clickPnotifyConfirm(page)
    expect((await enableResponse).status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /template enabled/i }),
    ).toBeVisible({ timeout: 8000 })

    // After reload checkbox must be checked.
    await page
      .locator('#domains tbody tr:not(.dataTables_empty)')
      .first()
      .waitFor({ state: 'visible', timeout: 10000 })
    await expect(waitForRow(page, dup.id).locator('input#chk-enabled')).toBeChecked({ timeout: 10000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S4 — cancel disable confirmation: checkbox reverts, no API call
  // ──────────────────────────────────────────────────────────────────────────
  test('S4: cancelling the disable confirmation reverts the checkbox', async ({
    authenticatedPage: page,
  }) => {
    let putFired = false
    page.on('request', (req) => {
      if (req.url().includes('/set-enabled') && req.method() === 'PUT') putFired = true
    })

    await gotoTemplates(page)
    const row = waitForRow(page, SEED.id)
    await expect(row).toBeVisible({ timeout: 10000 })
    const checkbox = row.locator('input#chk-enabled')
    await expect(checkbox).toBeChecked()

    await checkbox.click()
    await expect(
      page.locator('.ui-pnotify', { hasText: /disable this template/i }),
    ).toBeVisible({ timeout: 8000 })
    await clickPnotifyCancel(page)

    expect(putFired, 'set-enabled PUT must not fire on cancel').toBeFalsy()
    await expect(checkbox).toBeChecked({ timeout: 5000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S5 — admin disables a template
  // ──────────────────────────────────────────────────────────────────────────
  test('S5: disabling a template via the Enabled checkbox', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueTplName(testInfo, 's5')
    trackTplName(testInfo, name)
    const dup = await createDuplicateViaApi(apiv4Admin, { name })

    test.setTimeout(60000)
    const row = await waitForDupInTable(page, dup.id)
    const checkbox = row.locator('input#chk-enabled')
    await expect(checkbox).toBeChecked()

    const disableResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/template/${dup.id}/set-enabled`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await checkbox.click()
    await clickPnotifyConfirm(page)
    expect((await disableResponse).status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /template disabled/i }),
    ).toBeVisible({ timeout: 8000 })

    const all = await listTemplatesViaApi(apiv4Admin)
    expect(all.find((t) => t.id === dup.id)?.enabled, 'template must be disabled via API').toBe(false)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S6 — duplicate template (cancel + happy path)
  // ──────────────────────────────────────────────────────────────────────────
  test('S6: duplicating a template — cancel makes no API call', async ({
    authenticatedPage: page,
  }) => {
    let postFired = false
    page.on('request', (req) => {
      if (req.url().includes('/duplicate') && req.method() === 'POST') postFired = true
    })

    await gotoTemplates(page)
    const panel = await expandDetail(page, SEED.id)
    await panel.locator('.btn-duplicate-template').click()

    const modal = page.locator('#modalDuplicateTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })

    expect(postFired, 'duplicate POST must not fire on cancel').toBeFalsy()
  })

  test('S6: duplicating a template — happy path creates a new row', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueTplName(testInfo, 's6')
    const desc = `e2e template duplicated at ${new Date().toISOString()}`
    trackTplName(testInfo, name)

    await gotoTemplates(page)
    const panel = await expandDetail(page, SEED.id)

    // Pre-fill is loaded from GET /api/v4/item/template/{id}/get-info.
    const infoResponse = page.waitForResponse(
      (r) => r.url().includes('/get-info') && r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await panel.locator('.btn-duplicate-template').click()
    const modal = page.locator('#modalDuplicateTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await infoResponse
    await expect(modal.locator('.template-name')).toHaveValue(/Template/i, { timeout: 8000 })

    await modal.locator('.template-name').fill(name)
    await modal.locator('.template-description').fill(desc)

    const dupResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/template/${SEED.id}/duplicate`) &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await dupResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /duplicated/i }),
    ).toBeVisible({ timeout: 8000 })

    // New row appears after DataTable reload.
    await page
      .locator('#domains tbody tr:not(.dataTables_empty)')
      .first()
      .waitFor({ state: 'visible', timeout: 10000 })
    await expect(page.locator(`#domains tbody tr:has-text("${name}")`)).toBeVisible({ timeout: 10000 })

    const fresh = await findTemplateByName(apiv4Admin, name)
    expect(fresh, 'duplicated template not in API').not.toBeNull()
    expect(fresh.description).toBe(desc)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S7 — duplicate with invalid name (Parsley validation)
  // ──────────────────────────────────────────────────────────────────────────
  test('S7: Parsley blocks Send when the duplicate name is invalid', async ({
    authenticatedPage: page,
  }) => {
    let postFired = false
    page.on('request', (req) => {
      if (req.url().includes('/duplicate') && req.method() === 'POST') postFired = true
    })

    await gotoTemplates(page)
    const panel = await expandDetail(page, SEED.id)
    await panel.locator('.btn-duplicate-template').click()

    const modal = page.locator('#modalDuplicateTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    for (const invalid of ['ab', 'tpl@1', 'my/template', '']) {
      await modal.locator('.template-name').fill(invalid)
      await modal.locator('#send').click()
      await expect(modal).toBeVisible()
      await expect(modal.locator('.template-name')).toHaveClass(/parsley-error/, { timeout: 3000 })
    }
    expect(postFired, 'POST must not fire with an invalid name').toBeFalsy()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S8 — delete duplicated template; original is NOT affected
  // ──────────────────────────────────────────────────────────────────────────
  test('S8: delete duplicate — cancel path makes no DELETE call', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueTplName(testInfo, 's8-cancel')
    trackTplName(testInfo, name)
    const dup = await createDuplicateViaApi(apiv4Admin, { name })

    let deleteFired = false
    page.on('request', (req) => {
      if (req.url().includes(dup.id) && req.method() === 'DELETE') deleteFired = true
    })

    test.setTimeout(60000)
    const row = await waitForDupInTable(page, dup.id)
    const panel = await expandDetail(page, dup.id)
    await panel.locator('.btn-delete-template').click()

    const modal = page.locator('#modalDeleteTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })

    expect(deleteFired, 'DELETE must not fire on cancel').toBeFalsy()
    await expect(row).toBeVisible()
  })

  test('S8: delete duplicate removes only the duplicate; Template Test Frontend remains', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueTplName(testInfo, 's8')
    trackTplName(testInfo, name) // safety net if the UI delete fails
    const dup = await createDuplicateViaApi(apiv4Admin, { name })

    test.setTimeout(60000)
    await waitForDupInTable(page, dup.id)
    const panel = await expandDetail(page, dup.id)

    // Register before the click so the response isn't missed when the modal opens.
    const treeListResponse = page.waitForResponse(
      (r) => r.url().includes('tree_list') && r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await panel.locator('.btn-delete-template').click()

    const modal = page.locator('#modalDeleteTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Wait for the derivative tree API to return (empty tree = button enabled).
    await treeListResponse
    await expect(modal.locator('#send:not([disabled])')).toBeVisible({ timeout: 8000 })

    const deleteResponse = page.waitForResponse(
      (r) => r.url().includes(dup.id) && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await deleteResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /deleted/i }).first(),
    ).toBeVisible({ timeout: 8000 })

    // Duplicate row is gone.
    await page
      .locator('#domains tbody tr:not(.dataTables_empty)')
      .first()
      .waitFor({ state: 'visible', timeout: 10000 })
    await expect(waitForRow(page, dup.id)).toBeHidden({ timeout: 10000 })

    // Original seed template still present in UI and API.
    await expect(waitForRow(page, SEED.id)).toBeVisible({ timeout: 10000 })
    const all = await listTemplatesViaApi(apiv4Admin)
    expect(all.find((t) => t.id === dup.id), 'duplicate must be absent from API').toBeUndefined()
    expect(all.find((t) => t.id === SEED.id), 'seed template must still exist in API').toBeDefined()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S9 — delete blocked (cross-category derivatives)
  // ──────────────────────────────────────────────────────────────────────────
  test('S9: delete is blocked when the derivative tree has cross-category items', async ({
    managerE2EPage: page,
  }) => {
    // Runs as manager_e2e_01 (category: default). template-s9-seed is also in
    // default, so the manager can see it. Its derived desktop is in 'another'
    // category — the backend masks it with category='-'/unselectable=true for
    // managers, so hasCrossCategoryItems returns true and the UI blocks deletion.
    let deleteFired = false
    page.on('request', (req) => {
      if (req.url().includes(S9_SEED.id) && req.method() === 'DELETE') deleteFired = true
    })

    await gotoTemplates(page)
    const row = waitForRow(page, S9_SEED.id)
    await expect(row).toBeVisible({ timeout: 10000 })

    const panel = await expandDetail(page, S9_SEED.id)

    const treeResponse = page.waitForResponse(
      (r) => r.url().includes('tree_list') && r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await panel.locator('.btn-delete-template').click()

    const modal = page.locator('#modalDeleteTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await treeResponse

    await expect(modal.locator('#manager-warning')).toBeVisible({ timeout: 8000 })
    await expect(modal.locator('#cross-category-footer')).toBeVisible({ timeout: 8000 })
    // When the derivative tree has cross-category items, populate_tree_template_delete
    // hides #delete-warning and the #send button entirely (templates.js: $('#send').hide()),
    // showing #manager-warning + #cross-category-footer instead. The frontend block is now
    // in effect: there is no clickable delete control, so no DELETE can be fired.
    await expect(modal.locator('#send')).toBeHidden({ timeout: 5000 })

    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })

    expect(deleteFired, 'DELETE must not fire on cancel').toBeFalsy()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S10a — edit hardware: happy path
  // ──────────────────────────────────────────────────────────────────────────
  test('S10a: edit name + description via the Edit button', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const srcName = uniqueTplName(testInfo, 's10a-src')
    const newName = uniqueTplName(testInfo, 's10a')
    // Track both: srcName in case the edit fails (duplicate keeps original name),
    // newName for the success case (duplicate is renamed to newName by the edit).
    trackTplName(testInfo, srcName)
    trackTplName(testInfo, newName)
    const dup = await createDuplicateViaApi(apiv4Admin, { name: srcName })

    test.setTimeout(60000)
    const row = await waitForDupInTable(page, dup.id)
    await expandDetail(page, dup.id)
    const panel = page.locator(`[id="actions-${dup.id}"]`)
    await panel.locator('.btn-edit').click()

    const modal = page.locator('#modalEditDesktop')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    // #name (hidden) is set by setHardwareDomainDefaults — use it as AJAX-done signal.
    await expect(modal.locator('#name')).toHaveValue(srcName, { timeout: 8000 })

    // #name_hidden is the visible text input; its value wins in serializeObject.
    await modal.locator('#name_hidden').fill(newName)
    await modal.locator('#description').fill('edited by S10a')

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/template/${dup.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /updated/i }),
    ).toBeVisible({ timeout: 8000 })
    await expect(row).toContainText(newName, { timeout: 10000 })

    const all = await listTemplatesViaApi(apiv4Admin)
    expect(all.find((t) => t.id === dup.id)?.name).toBe(newName)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S10b — edit cancel: no PUT is made
  // ──────────────────────────────────────────────────────────────────────────
  test('S10b: closing the Edit modal without saving makes no PUT call', async ({
    authenticatedPage: page,
  }) => {
    let putFired = false
    page.on('request', (req) => {
      if (req.url().includes('/edit') && req.method() === 'PUT') putFired = true
    })

    await gotoTemplates(page)
    await expandDetail(page, SEED.id)
    const panel = page.locator(`[id="actions-${SEED.id}"]`)
    await panel.locator('.btn-edit').click()

    const modal = page.locator('#modalEditDesktop')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('#name_hidden').fill('should-not-be-saved')
    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })

    expect(putFired, 'edit PUT must not fire when modal is closed').toBeFalsy()
    await expect(waitForRow(page, SEED.id)).toContainText(SEED.name)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S10c — viewers change persists after save
  // ──────────────────────────────────────────────────────────────────────────
  test('S10c: unchecking a viewer persists after save', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueTplName(testInfo, 's10c')
    trackTplName(testInfo, name)
    const dup = await createDuplicateViaApi(apiv4Admin, { name })

    test.setTimeout(60000)
    await waitForDupInTable(page, dup.id)
    await expandDetail(page, dup.id)
    const panel = page.locator(`[id="actions-${dup.id}"]`)

    // Register before the click so the response isn't missed when the modal opens.
    const infoResponse = page.waitForResponse(
      (r) => r.url().includes(`/api/v4/item/desktop/${dup.id}/get-info`) && r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await panel.locator('.btn-edit').click()
    const modal = page.locator('#modalEditDesktop')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await infoResponse
    // #name (hidden) is set by setHardwareDomainDefaults — use it as AJAX-done signal.
    await expect(modal.locator('#name')).toHaveValue(name, { timeout: 8000 })

    // Dup inherits browser_vnc and file_spice from SEED; verify initial state.
    await expect(modal.locator('#viewers-browser_vnc')).toBeChecked({ timeout: 5000 })
    await expect(modal.locator('#viewers-file_spice')).toBeChecked({ timeout: 5000 })

    // Uncheck file_spice via iCheck (checkbox is opacity:0 in the DOM).
    await page.evaluate(() => window.$('#modalEditDesktop #viewers-file_spice').iCheck('uncheck'))
    await expect(modal.locator('#viewers-file_spice')).not.toBeChecked({ timeout: 3000 })

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/template/${dup.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /updated/i }),
    ).toBeVisible({ timeout: 8000 })

    // Reopen and verify file_spice is still unchecked (change persisted).
    await expandDetail(page, dup.id)
    const panel2 = page.locator(`[id="actions-${dup.id}"]`)
    const infoResponse2 = page.waitForResponse(
      (r) => r.url().includes(`/api/v4/item/desktop/${dup.id}/get-info`) && r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await panel2.locator('.btn-edit').click()
    const modal2 = page.locator('#modalEditDesktop')
    await modal2.waitFor({ state: 'visible', timeout: 10000 })
    await infoResponse2
    // #name (hidden) is set by setHardwareDomainDefaults — use it as AJAX-done signal.
    await expect(modal2.locator('#name')).toHaveValue(name, { timeout: 8000 })

    await expect(modal2.locator('#viewers-file_spice')).not.toBeChecked({ timeout: 5000 })
    await expect(modal2.locator('#viewers-browser_vnc')).toBeChecked({ timeout: 5000 })

    await modal2.locator('button[data-dismiss="modal"]').first().click()
    await modal2.waitFor({ state: 'hidden', timeout: 5000 })
    // afterEach cleans up the dup by name.
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S11 — XML editor: modal opens and sections load
  // ──────────────────────────────────────────────────────────────────────────
  test('S11: XML editor modal opens and renders sections for Template Test Frontend', async ({
    authenticatedPage: page,
  }) => {
    await gotoTemplates(page)
    await expandDetail(page, SEED.id)
    const panel = page.locator(`[id="actions-${SEED.id}"]`)

    const xmlBtn = panel.locator('.btn-xml')
    await expect(xmlBtn).toBeVisible({ timeout: 5000 })

    const xmlResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/domains/xml_sections/') &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await xmlBtn.click()

    expect((await xmlResponse).status()).toBeLessThan(400)

    const modal = page.locator('#modalEditXmlSections')
    await modal.waitFor({ state: 'visible', timeout: 8000 })

    // At least one section textarea must be attached (sections loaded correctly).
    // Nav links exist in the DOM but may be hidden by CSS depending on viewport.
    await expect(modal.locator('.xml-section-textarea').first()).toBeAttached({ timeout: 8000 })

    // No error alert should be visible.
    await expect(modal.locator('.alert-danger')).toHaveCount(0)

    // TODO: test the save path once it can be validated without a real hypervisor.
    // Saving calls POST /api/v4/admin/item/domains/xml_sections/{id} which merges
    // the edited sections back and may trigger hypervisor-side XML validation.

    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S12 — change owner (cancel + happy path)
  // ──────────────────────────────────────────────────────────────────────────
  test('S12: change owner — cancel makes no API call', async ({
    authenticatedPage: page,
  }) => {
    let putFired = false
    page.on('request', (req) => {
      if (req.url().includes('change-owner') && req.method() === 'PUT') putFired = true
    })

    await gotoTemplates(page)
    const panel = await expandDetail(page, SEED.id)
    await panel.locator('.btn-owner').click()

    const modal = page.locator('#modalChangeOwnerDomain')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })

    expect(putFired, 'change-owner PUT must not fire on cancel').toBeFalsy()
  })

  test('S12: change owner — happy path updates the User column', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueTplName(testInfo, 's12')
    trackTplName(testInfo, name)
    const dup = await createDuplicateViaApi(apiv4Admin, { name })

    test.setTimeout(60000)
    const row = await waitForDupInTable(page, dup.id)
    const panel = await expandDetail(page, dup.id)
    await panel.locator('.btn-owner').click()

    const modal = page.locator('#modalChangeOwnerDomain')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Select2 requires minimumInputLength:2; inject the option programmatically.
    await page.evaluate((userId) => {
      const $sel = window.$('#new_owner')
      if (!$sel.find(`option[value="${userId}"]`).length) {
        $sel.append(new Option('Manager Default', userId, true, true))
      }
      $sel.val([userId]).trigger('change')
    }, OTHER_USER_ID)

    const ownerResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/template/${dup.id}/change-owner`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await ownerResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /owner changed/i }),
    ).toBeVisible({ timeout: 8000 })

    await page
      .locator('#domains tbody tr:not(.dataTables_empty)')
      .first()
      .waitFor({ state: 'visible', timeout: 10000 })
    await expect(waitForRow(page, dup.id)).toContainText(/manager01|Manager Default/i, { timeout: 10000 })
    // afterEach cleans up the dup by name.
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S13 — forced hypervisor (cancel + assign + remove)
  // ──────────────────────────────────────────────────────────────────────────
  test('S13: forced hypervisor — cancel makes no API call', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    const hyps = await listHypervisors(apiv4Admin)
    test.skip(hyps.length === 0, 'no hypervisors available in the dev DB')

    let putFired = false
    page.on('request', (req) => {
      if (req.url().includes('/edit') && req.method() === 'PUT') putFired = true
    })

    await gotoTemplates(page)
    const panel = await expandDetail(page, SEED.id)
    await panel.locator('.btn-forcedhyp').click()

    const modal = page.locator('#modalForcedhyp')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })

    expect(putFired, 'edit PUT must not fire on cancel').toBeFalsy()
  })

  test('S13: assign forced hypervisor then remove it', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const hyps = await listHypervisors(apiv4Admin)
    test.skip(hyps.length === 0, 'no hypervisors available in the dev DB')
    const firstHyp = hyps[0].id

    // Operate on an isolated duplicate so two concurrent workers never mutate
    // the shared seed's forced_hyp / status at the same time.
    const name = uniqueTplName(testInfo, 's13')
    trackTplName(testInfo, name)
    const dup = await createDuplicateViaApi(apiv4Admin, { name })

    test.setTimeout(60000)
    const row = await waitForDupInTable(page, dup.id)
    await expect(row).toBeVisible({ timeout: 10000 })
    const panel = await expandDetail(page, dup.id)
    await panel.locator('.btn-forcedhyp').click()

    const modal = page.locator('#modalForcedhyp')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Trigger iCheck 'ifChecked' to show the hypervisor dropdown.
    await page.evaluate(() => window.$('#forcedhyp-check').iCheck('check'))
    const dropdown = modal.locator('#forced_hyp')
    await dropdown.waitFor({ state: 'visible', timeout: 8000 })
    await expect(dropdown.locator('option')).not.toHaveCount(0, { timeout: 10000 })
    await dropdown.selectOption(firstHyp)

    const assignResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/template/${dup.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await assignResp).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-text', { hasText: /forced hypervisor updated/i }),
    ).toBeVisible({ timeout: 8000 })
    // The #send success handler does not reload the DataTable (no ajax.reload),
    // so force a fresh server fetch before asserting the cell — same as the
    // desktops S15 test which calls gotoDesktops after the edit.
    await gotoTemplates(page)
    // forced_hyp is column index 9 (0-based td) in the spliced templates layout.
    await expect(waitForRow(page, dup.id).locator('td').nth(9)).toContainText(firstHyp, { timeout: 10000 })

    // Remove.
    const panel2 = await expandDetail(page, dup.id)
    await panel2.locator('.btn-forcedhyp').click()
    const modal2 = page.locator('#modalForcedhyp')
    await modal2.waitFor({ state: 'visible', timeout: 10000 })
    // The check is now checked (forced_hyp is set); uncheck it.
    await expect(modal2.locator('#forcedhyp-check')).toBeChecked()
    await page.evaluate(() => window.$('#forcedhyp-check').iCheck('uncheck'))

    // The assign edit above flipped the duplicate Stopped→Updating; reset it so
    // the remove edit passes the "must be stopped or failed" precondition.
    await forceStopped(apiv4Admin, dup.id)

    const removeResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/template/${dup.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal2.locator('#send').click()
    expect((await removeResp).status()).toBeLessThan(400)
    await modal2.waitFor({ state: 'hidden', timeout: 10000 })

    // Reload so the cleared value is reflected (the success handler doesn't reload).
    await gotoTemplates(page)
    // forced_hyp is column index 9 (0-based td) — check only that cell.
    await expect(waitForRow(page, dup.id).locator('td').nth(9)).not.toContainText(firstHyp, { timeout: 10000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S14 — favourite hypervisor (cancel + assign + remove)
  // ──────────────────────────────────────────────────────────────────────────
  test('S14: favourite hypervisor — cancel makes no API call', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    const hyps = await listHypervisors(apiv4Admin)
    test.skip(hyps.length === 0, 'no hypervisors available in the dev DB')

    let putFired = false
    page.on('request', (req) => {
      if (req.url().includes('/edit') && req.method() === 'PUT') putFired = true
    })

    await gotoTemplates(page)
    const panel = await expandDetail(page, SEED.id)
    await panel.locator('.btn-favouritehyp').click()

    const modal = page.locator('#modalFavouriteHyp')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })

    expect(putFired, 'edit PUT must not fire on cancel').toBeFalsy()
  })

  test('S14: assign favourite hypervisor then remove it', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const hyps = await listHypervisors(apiv4Admin)
    test.skip(hyps.length === 0, 'no hypervisors available in the dev DB')
    const firstHyp = hyps[0].id

    // Operate on an isolated duplicate so two concurrent workers never mutate
    // the shared seed's favourite_hyp / status at the same time.
    const name = uniqueTplName(testInfo, 's14')
    trackTplName(testInfo, name)
    const dup = await createDuplicateViaApi(apiv4Admin, { name })

    test.setTimeout(60000)
    const row = await waitForDupInTable(page, dup.id)
    await expect(row).toBeVisible({ timeout: 10000 })
    const panel = await expandDetail(page, dup.id)
    await panel.locator('.btn-favouritehyp').click()

    const modal = page.locator('#modalFavouriteHyp')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await page.evaluate(() => window.$('#favouritehyp-check').iCheck('check'))
    const dropdown = modal.locator('#favourite_hyp')
    await dropdown.waitFor({ state: 'visible', timeout: 8000 })
    await expect(dropdown.locator('option')).not.toHaveCount(0, { timeout: 10000 })
    await dropdown.selectOption(firstHyp)

    const assignResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/template/${dup.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await assignResp).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /updated/i }),
    ).toBeVisible({ timeout: 8000 })
    // The #send success handler does not reload the DataTable (no ajax.reload),
    // so force a fresh server fetch before asserting the cell — same as the
    // desktops S19 test which calls gotoDesktops after the edit.
    await gotoTemplates(page)
    // favourite_hyp is column index 8 (0-based td) in the spliced templates layout.
    await expect(waitForRow(page, dup.id).locator('td').nth(8)).toContainText(firstHyp, { timeout: 10000 })

    // Remove.
    const panel2 = await expandDetail(page, dup.id)
    await panel2.locator('.btn-favouritehyp').click()
    const modal2 = page.locator('#modalFavouriteHyp')
    await modal2.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal2.locator('#favouritehyp-check')).toBeChecked()
    await page.evaluate(() => window.$('#favouritehyp-check').iCheck('uncheck'))

    // The assign edit above flipped the duplicate Stopped→Updating; reset it so
    // the remove edit passes the "must be stopped or failed" precondition.
    await forceStopped(apiv4Admin, dup.id)

    const removeResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/template/${dup.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal2.locator('#send').click()
    expect((await removeResp).status()).toBeLessThan(400)
    await modal2.waitFor({ state: 'hidden', timeout: 10000 })

    // Reload so the cleared value is reflected (the success handler doesn't reload).
    await gotoTemplates(page)
    // favourite_hyp is column index 8 (0-based td) — check only that cell.
    await expect(waitForRow(page, dup.id).locator('td').nth(8)).not.toContainText(firstHyp, { timeout: 10000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S15 — UUID search (valid / invalid format / empty)
  // ──────────────────────────────────────────────────────────────────────────
  // S15 happy path uses a duplicate (not the seed). The seed id
  // ('template-test-001') is not a UUID and would be rejected by the frontend,
  // but duplicates receive a proper UUID from the backend. The seed carries no
  // isos/floppies (see domains.json), so the duplicate inherits no dangling
  // media references and get-info returns 200 cleanly.
  test('S15: UUID search — valid UUID opens the domain info modal', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueTplName(testInfo, 's15')
    trackTplName(testInfo, name)
    const dup = await createDuplicateViaApi(apiv4Admin, { name })

    await gotoTemplates(page)

    const infoResponse = page.waitForResponse(
      (r) => r.url().includes(dup.id) && r.url().includes('get-info') && r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await page.locator('#domain-uuid-search').fill(dup.id)
    await page.locator('#domain-uuid-search-btn').click()
    expect((await infoResponse).status()).toBeLessThan(400)

    const modal = page.locator('#domain-info-modal')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  test('S15: UUID search — invalid UUID format shows PNotify error; no get-info call', async ({
    authenticatedPage: page,
  }) => {
    let getInfoFired = false
    page.on('request', (req) => {
      if (req.url().includes('get-info') && req.method() === 'GET') getInfoFired = true
    })

    await gotoTemplates(page)
    await page.locator('#domain-uuid-search').fill('not-a-valid-uuid-string')
    await page.locator('#domain-uuid-search-btn').click()

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /invalid uuid/i }),
    ).toBeVisible({ timeout: 5000 })
    expect(getInfoFired, 'get-info must not fire for an invalid UUID').toBeFalsy()
  })

  test('S15: UUID search — empty input shows PNotify error', async ({
    authenticatedPage: page,
  }) => {
    await gotoTemplates(page)
    await page.locator('#domain-uuid-search').fill('')
    await page.locator('#domain-uuid-search-btn').click()

    await expect(
      page.locator('.ui-pnotify-text, .ui-pnotify-title', { hasText: /please enter/i }),
    ).toBeVisible({ timeout: 5000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S16 — row data validation for Template Test Frontend
  // ──────────────────────────────────────────────────────────────────────────
  test('S16: Template Test Frontend row shows correct name, description and enabled state', async ({
    authenticatedPage: page,
  }) => {
    await gotoTemplates(page)
    const row = waitForRow(page, SEED.id)
    await expect(row).toBeVisible({ timeout: 10000 })

    await expect(row).toContainText(SEED.name)
    await expect(row).toContainText(SEED.description)
    await expect(row.locator('input#chk-enabled')).toBeChecked()
    await expect(row.locator('#btn-alloweds')).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S17 — info-circle button opens domain info modal
  // ──────────────────────────────────────────────────────────────────────────
  test('S17: info-circle button opens domain info modal with correct template data', async ({
    authenticatedPage: page,
  }) => {
    await gotoTemplates(page)
    const row = waitForRow(page, SEED.id)
    await expect(row).toBeVisible({ timeout: 10000 })

    const infoResponse = page.waitForResponse(
      (r) =>
        r.url().includes(SEED.id) &&
        r.url().includes('get-info') &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await row.locator('td.info-control button[data-domain-info]').click()
    expect((await infoResponse).status()).toBeLessThan(400)

    const modal = page.locator('#domain-info-modal')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await expect(modal.locator('#domain-info-title')).toContainText(SEED.name, { timeout: 8000 })
    await expect(modal.locator('#domain-info-content')).toContainText(SEED.id)
    await expect(modal.locator('#domain-info-content')).toContainText('template')

    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S18 — expand detail panel: action buttons present; no jumperurl button
  // ──────────────────────────────────────────────────────────────────────────
  test('S18: expanded detail panel shows action buttons and no jumperurl button', async ({
    authenticatedPage: page,
  }) => {
    await gotoTemplates(page)
    const panel = await expandDetail(page, SEED.id)

    await expect(panel.locator('.btn-duplicate-template')).toBeVisible()
    await expect(panel.locator('.btn-edit')).toBeVisible()
    await expect(panel.locator('.btn-xml')).toBeVisible()
    await expect(panel.locator('.btn-owner')).toBeVisible()
    await expect(panel.locator('.btn-delete-template')).toBeVisible()
    await expect(panel.locator('.btn-forcedhyp')).toBeVisible()
    await expect(panel.locator('.btn-favouritehyp')).toBeVisible()

    // Share link (jumperurl) must NOT exist in the admin template detail panel.
    await expect(panel.locator('.btn-jumperurl')).toHaveCount(0)

    // Collapse.
    await page
      .locator(`#domains tbody tr[id="${SEED.id}"] td.details-control button`)
      .first()
      .click()
    await panel.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S19 — edit permissions via Shares button (btn-alloweds)
  // ──────────────────────────────────────────────────────────────────────────
  test('S19: Shares button opens #modalAlloweds — cancel makes no change', async ({
    authenticatedPage: page,
  }) => {
    let allowedsFired = false
    page.on('request', (req) => {
      if (req.url().includes('/allowed/update/') && req.method() === 'POST') allowedsFired = true
    })

    await gotoTemplates(page)
    const row = waitForRow(page, SEED.id)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('#btn-alloweds').click()

    const modal = page.locator('#modalAlloweds')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('button[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })

    expect(allowedsFired, 'alloweds update must not fire when modal is cancelled').toBeFalsy()
  })

  test('S19: Shares button — happy path adds a group permission and persists', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueTplName(testInfo, 's19')
    trackTplName(testInfo, name)
    const dup = await createDuplicateViaApi(apiv4Admin, { name })

    test.setTimeout(60000)
    const row = await waitForDupInTable(page, dup.id)

    // Wait for the modal to load existing alloweds before interacting.
    const tableResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/item/allowed/table/domains') &&
        r.request().method() === 'POST',
      { timeout: 10000 },
    )
    await row.locator('#btn-alloweds').click()
    await tableResponse

    const modal = page.locator('#modalAlloweds')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Enable the groups section (iCheck) and inject the default group via Select2.
    await page.evaluate(() => window.$('#modalAllowedsForm #alloweds-add #a-groups-cb').iCheck('check'))
    await modal.locator('#a-groups').waitFor({ state: 'visible', timeout: 5000 })
    await page.evaluate(() => {
      const $sel = window.$('#modalAllowedsForm #alloweds-add #a-groups')
      if (!$sel.find('option[value="default-default"]').length) {
        $sel.append(new Option('Default', 'default-default', true, true))
      }
      $sel.val(['default-default']).trigger('change')
    })

    const updateResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/item/allowed/update/domains') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await updateResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /alloweds updated successfully/i }),
    ).toBeVisible({ timeout: 8000 })
  })
})
