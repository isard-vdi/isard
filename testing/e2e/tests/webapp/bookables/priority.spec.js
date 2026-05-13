// Drives the Bookables → Priority admin page. Mirrors
// testing/e2e/specs/webapp/bookables/priority.md — each test(...) maps to
// a numbered scenario in that spec.
//
// Conventions:
//   - Each test creates its own priority rule with a worker+timestamp
//     unique name so parallel workers don't collide. The rule id is
//     tracked via testInfo.annotations (type: "priority-id") so afterEach
//     can delete it even if the test failed mid-flow.
//   - System rules `default` and `default admins` are touched only by
//     read-only assertions (S1, S5) — never mutated.

import { test, expect } from '../../../fixtures/login.js'

const PRIORITY_URL = '/isard-admin/admin/domains/render/Priority'
const VALID_NAME_RE = /^[\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/

async function listPriorities(page) {
  const resp = await page.request.post('/api/v4/admin/table/bookings_priority', {
    data: { order_by: 'name' },
  })
  if (!resp.ok()) return []
  return (await resp.json().catch(() => [])) || []
}

async function findPriorityByName(page, name) {
  const items = await listPriorities(page)
  return items.find((p) => p.name === name) || null
}

async function createPriorityViaApi(page, data) {
  const resp = await page.request.post('/api/v4/admin/table/add/bookings_priority', {
    data,
  })
  if (!resp.ok()) {
    throw new Error(
      `createPriorityViaApi failed: ${resp.status()} ${await resp.text().catch(() => '')}`,
    )
  }
  // /admin/table/add returns 204 (EmptyResponse); look up the inserted
  // row by name to recover the generated id.
  const created = await findPriorityByName(page, data.name)
  if (!created) {
    throw new Error(`createPriorityViaApi: row "${data.name}" not visible after insert`)
  }
  return created
}

async function deletePriorityViaApi(page, id) {
  await page.request
    .delete(`/api/v4/item/booking/priority/${id}`)
    .catch(() => {})
}

async function trackPriorityId(testInfo, id) {
  testInfo.annotations.push({ type: 'priority-id', description: id })
}

function uniquePriorityName(testInfo, suffix = '') {
  return `e2e-prio-${testInfo.workerIndex}-${Date.now()}${suffix ? `-${suffix}` : ''}`
}

function uniqueRuleId(testInfo, suffix = '') {
  return `e2e-rule-${testInfo.workerIndex}-${Date.now()}${suffix ? `-${suffix}` : ''}`
}

async function gotoPriority(page) {
  await page.goto(PRIORITY_URL)
  await page
    .locator(
      '#bookings_priority ~ .dataTables_wrapper, .dataTables_wrapper:has(#bookings_priority)',
    )
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  await page
    .locator('#bookings_priority tbody tr:not(.dataTables_empty)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
}

async function clickPnotifyOk(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^ok$/i })
    .first()
    .click({ timeout: 5000 })
}

test.describe('Admin Bookables — Priority', () => {
  // Sweep leftovers from prior runs of *this* worker only — peer workers
  // may have in-flight rules with their own workerIndex prefix.
  test.beforeAll(async ({ authenticatedContext }, workerInfo) => {
    const page = await authenticatedContext.newPage()
    try {
      const prefix = `e2e-prio-${workerInfo.workerIndex}-`
      const stale = (await listPriorities(page)).filter(
        (p) => typeof p.name === 'string' && p.name.startsWith(prefix),
      )
      for (const p of stale) {
        await deletePriorityViaApi(page, p.id)
      }
    } finally {
      await page.close()
    }
  })

  test.afterEach(async ({ authenticatedPage: page }, testInfo) => {
    const ids = testInfo.annotations
      .filter((a) => a.type === 'priority-id')
      .map((a) => a.description)
    for (const id of ids) {
      await deletePriorityViaApi(page, id)
    }
  })

  // ---------------------------------------------------------------------
  // Scenario 1 — lists priority rules from the seed
  // ---------------------------------------------------------------------
  test('S1: lists priority rules from the seed', async ({ authenticatedPage: page }) => {
    const tableResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/table/bookings_priority') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await page.goto(PRIORITY_URL)
    expect((await tableResponse).status()).toBeLessThan(400)

    const items = await listPriorities(page)
    const ids = new Set(items.map((p) => p.id))
    expect(ids).toContain('default')
    expect(ids).toContain('default admins')
    expect(ids).toContain('test-low-forbid-time')

    await page
      .locator(
        '#bookings_priority ~ .dataTables_wrapper, .dataTables_wrapper:has(#bookings_priority)',
      )
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })

    for (const id of ['default', 'default admins', 'test-low-forbid-time']) {
      await expect(page.locator(`#bookings_priority tbody tr[id="${id}"]`))
        .toBeVisible({ timeout: 10000 })
    }
  })

  // ---------------------------------------------------------------------
  // Scenario 2 — creates a new rule via the modal
  // ---------------------------------------------------------------------
  test('S2: creates a new priority rule from the Add modal', async ({
    authenticatedPage: page,
  }, testInfo) => {
    const name = uniquePriorityName(testInfo, 's2')
    const ruleId = uniqueRuleId(testInfo, 's2')

    await gotoPriority(page)
    await page.locator('.add-new').first().click()
    const modal = page.locator('#modalAddPriority')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#modalAdd #name').fill(name)
    await modal.locator('#modalAdd #description').fill('s2 priority rule')
    await modal.locator('#modalAdd #rule_id').fill(ruleId)
    await modal.locator('#modalAdd #priority').fill('100')
    await modal.locator('#modalAdd #forbid_time').fill('30')
    await modal.locator('#modalAdd #max_time').fill('120')
    await modal.locator('#modalAdd #max_items').fill('3')

    const createResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/table/add/bookings_priority') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await createResponse
    expect(resp.status()).toBeLessThan(400)
    // /admin/table/add returns 204 with no body. Verify the post body
    // we sent had the numeric coercion applied.
    const body = resp.request().postDataJSON()
    expect(body.priority).toBe(100)
    expect(body.forbid_time).toBe(30)
    expect(body.max_time).toBe(120)
    expect(body.max_items).toBe(3)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    const created = await findPriorityByName(page, name)
    expect(created, 'newly created rule should be returned by /admin/table').not.toBeNull()
    await trackPriorityId(testInfo, created.id)

    await expect(page.locator(`#bookings_priority tbody tr[id="${created.id}"]`))
      .toBeVisible({ timeout: 10000 })
  })

  // ---------------------------------------------------------------------
  // Scenario 3 — edits a rule
  // ---------------------------------------------------------------------
  test('S3: edits an existing rule via the pencil icon', async ({
    authenticatedPage: page,
  }, testInfo) => {
    const name = uniquePriorityName(testInfo, 's3')
    const created = await createPriorityViaApi(page, {
      name,
      description: 's3 original',
      rule_id: uniqueRuleId(testInfo, 's3'),
      priority: 50,
      forbid_time: 30,
      max_time: 90,
      max_items: 2,
      allowed: { roles: false, categories: false, groups: false, users: false },
    })
    await trackPriorityId(testInfo, created.id)

    await gotoPriority(page)
    const row = page.locator(`#bookings_priority tbody tr[id="${created.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-edit').click()

    const modal = page.locator('#modalEditPriority')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#modalEdit #name')).toHaveValue(name)
    await expect(modal.locator('#modalEdit #max_items')).toHaveValue('2')

    const editedName = `${name}-edited`
    await modal.locator('#modalEdit #name').fill(editedName)
    await modal.locator('#modalEdit #max_items').fill('5')

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/table/update/bookings_priority') &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await editResponse
    expect(resp.status()).toBeLessThan(400)
    const body = resp.request().postDataJSON()
    expect(body.id).toBe(created.id)
    expect(body.max_items).toBe(5)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    const persisted = await findPriorityByName(page, editedName)
    expect(persisted).not.toBeNull()
    expect(persisted.max_items).toBe(5)
  })

  // ---------------------------------------------------------------------
  // Scenario 4 — deletes a rule with PNotify confirmation
  // ---------------------------------------------------------------------
  test('S4: deletes a user-created rule through the trash icon', async ({
    authenticatedPage: page,
  }, testInfo) => {
    const name = uniquePriorityName(testInfo, 's4')
    const created = await createPriorityViaApi(page, {
      name,
      description: 's4 to be deleted',
      rule_id: uniqueRuleId(testInfo, 's4'),
      priority: 100,
      forbid_time: 30,
      max_time: 120,
      max_items: 3,
      allowed: { roles: false, categories: false, groups: false, users: false },
    })
    await trackPriorityId(testInfo, created.id) // afterEach safety net

    await gotoPriority(page)
    const row = page.locator(`#bookings_priority tbody tr[id="${created.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-delete').click()

    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/booking/priority/${created.id}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    // After success, the JS calls `bookings_priority.ajax.reload()`
    // which re-fetches the table. Wait for that reload before asserting
    // visibility so we don't race a stale-DOM read.
    const reloadResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/table/bookings_priority') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await deleteResponse).status()).toBeLessThan(400)
    expect((await reloadResponse).status()).toBeLessThan(400)

    await expect(row).toBeHidden({ timeout: 10000 })
    expect(await findPriorityByName(page, name)).toBeNull()
  })

  // ---------------------------------------------------------------------
  // Scenario 5 — system rules are not deletable via UI
  // ---------------------------------------------------------------------
  test('S5: system rules `default` and `default admins` expose only the edit button', async ({
    authenticatedPage: page,
  }) => {
    await gotoPriority(page)

    for (const id of ['default', 'default admins']) {
      const row = page.locator(`#bookings_priority tbody tr[id="${id}"]`)
      await expect(row).toBeVisible({ timeout: 10000 })
      // The columnDef at target 12 renders only the edit button for
      // system rows. Both other action buttons must be absent.
      await expect(row.locator('button#btn-edit')).toHaveCount(1)
      await expect(row.locator('button#btn-delete')).toHaveCount(0)
      await expect(row.locator('button#btn-alloweds')).toHaveCount(0)
    }
  })

  // ---------------------------------------------------------------------
  // Scenario 6 — alloweds modal round-trips through /admin/allowed/update
  // ---------------------------------------------------------------------
  test('S6: alloweds modal saves and the new state hydrates on reopen', async ({
    authenticatedPage: page,
  }, testInfo) => {
    const created = await createPriorityViaApi(page, {
      name: uniquePriorityName(testInfo, 's6'),
      description: 's6 alloweds target',
      rule_id: uniqueRuleId(testInfo, 's6'),
      priority: 100,
      forbid_time: 30,
      max_time: 120,
      max_items: 3,
      allowed: { roles: ['user'], categories: false, groups: false, users: false },
    })
    await trackPriorityId(testInfo, created.id)

    await gotoPriority(page)
    const row = page.locator(`#bookings_priority tbody tr[id="${created.id}"]`)
    const modal = page.locator('#modalAlloweds')

    // iCheck syncs the (opacity:0) <input> async — poll it, not wrapper classes.
    const rolesCbChecked = () =>
      page.evaluate(() => document.querySelector('#a-roles-cb')?.checked)

    // --- First open: prefill reflects the API-seeded {roles: ['user']} ---
    const prefillRead1 = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/allowed/table/bookings_priority') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await row.locator('button#btn-alloweds').click()
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    expect((await prefillRead1).status()).toBeLessThan(400)
    await expect.poll(rolesCbChecked, { timeout: 5000 }).toBe(true)

    // The real <input> is hidden by iCheck — click the overlay helper.
    await modal
      .locator('#roles_pannel .iCheck-helper')
      .first()
      .click({ force: true })
    await expect.poll(rolesCbChecked, { timeout: 5000 }).toBe(false)

    const updateResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/allowed/update/bookings_priority') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const upd = await updateResponse
    expect(upd.status()).toBeLessThan(400)
    const body = upd.request().postDataJSON()
    expect(body.id).toBe(created.id)
    expect(body.table).toBe('bookings_priority')
    // parseAllowed() returns `false` (not []) when the wrapper checkbox is off.
    expect(body.allowed.roles).toBe(false)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /alloweds updated successfully/i }),
    ).toBeVisible({ timeout: 5000 })
    await modal.waitFor({ state: 'hidden', timeout: 5000 })

    // --- Reopen: the persisted state must rehydrate the form unchecked ---
    const prefillRead2 = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/allowed/table/bookings_priority') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await row.locator('button#btn-alloweds').click()
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    expect((await prefillRead2).status()).toBeLessThan(400)
    await expect.poll(rolesCbChecked, { timeout: 5000 }).toBe(false)
  })

  // ---------------------------------------------------------------------
  // Scenario 7 — alloweds viewer at the row detail
  // ---------------------------------------------------------------------
  test('S7: expanding a rule row renders the alloweds viewer', async ({
    authenticatedPage: page,
  }, testInfo) => {
    const created = await createPriorityViaApi(page, {
      name: uniquePriorityName(testInfo, 's7'),
      description: 's7 viewer target',
      rule_id: uniqueRuleId(testInfo, 's7'),
      priority: 100,
      forbid_time: 30,
      max_time: 120,
      max_items: 3,
      allowed: { roles: ['user'], categories: false, groups: false, users: false },
    })
    await trackPriorityId(testInfo, created.id)

    await gotoPriority(page)
    const row = page.locator(`#bookings_priority tbody tr[id="${created.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    const viewerResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/allowed/table/bookings_priority') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await row.locator('td.details-control button').first().click()
    expect((await viewerResponse).status()).toBeLessThan(400)

    const allowedsTable = page.locator(`#table-alloweds-${created.id}`)
    await expect(allowedsTable).toBeVisible({ timeout: 10000 })
    await expect(allowedsTable.locator('tbody tr').first()).toBeVisible({
      timeout: 5000,
    })
  })

  // ---------------------------------------------------------------------
  // Scenario 8 — Parsley blocks invalid create input
  // ---------------------------------------------------------------------
  test('S8: Parsley blocks creation when required fields are missing or invalid', async ({
    authenticatedPage: page,
  }) => {
    await gotoPriority(page)
    await page.locator('.add-new').first().click()
    const modal = page.locator('#modalAddPriority')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    let postFired = false
    page.on('request', (req) => {
      if (
        req.url().includes('/api/v4/admin/table/add/bookings_priority') &&
        req.method() === 'POST'
      ) {
        postFired = true
      }
    })

    // Case A — empty form, just submit.
    await modal.locator('#send').click()
    await expect(modal).toBeVisible()

    // Case B — invalid name pattern, the rest valid.
    await modal.locator('#modalAdd #name').fill('prio@1')
    await modal.locator('#modalAdd #description').fill('s8')
    await modal.locator('#modalAdd #rule_id').fill('s8-rule')
    await modal.locator('#modalAdd #priority').fill('100')
    await modal.locator('#modalAdd #forbid_time').fill('30')
    await modal.locator('#modalAdd #max_time').fill('120')
    await modal.locator('#modalAdd #max_items').fill('3')
    await modal.locator('#send').click()
    await expect(modal).toBeVisible()
    await expect(modal.locator('#modalAdd #name')).toHaveClass(/parsley-error/)

    // Case C — name too short.
    await modal.locator('#modalAdd #name').fill('ab')
    await modal.locator('#send').click()
    await expect(modal).toBeVisible()
    await expect(modal.locator('#modalAdd #name')).toHaveClass(/parsley-error/)

    expect(postFired, 'POST must not fire while Parsley flags the form').toBeFalsy()
  })

  // ---------------------------------------------------------------------
  // Scenario 9 — duplicate name returns 409
  // ---------------------------------------------------------------------
  test('S9: re-creating with an existing name returns a conflict', async ({
    authenticatedPage: page,
  }, testInfo) => {
    const name = uniquePriorityName(testInfo, 's9')
    const first = await createPriorityViaApi(page, {
      name,
      description: 'first',
      rule_id: uniqueRuleId(testInfo, 's9'),
      priority: 100,
      forbid_time: 30,
      max_time: 120,
      max_items: 3,
      allowed: { roles: false, categories: false, groups: false, users: false },
    })
    await trackPriorityId(testInfo, first.id)

    await gotoPriority(page)
    await page.locator('.add-new').first().click()
    const modal = page.locator('#modalAddPriority')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#modalAdd #name').fill(name)
    await modal.locator('#modalAdd #description').fill('duplicate attempt')
    await modal.locator('#modalAdd #rule_id').fill(uniqueRuleId(testInfo, 's9-dup'))
    await modal.locator('#modalAdd #priority').fill('100')
    await modal.locator('#modalAdd #forbid_time').fill('30')
    await modal.locator('#modalAdd #max_time').fill('120')
    await modal.locator('#modalAdd #max_items').fill('3')

    const createResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/table/add/bookings_priority') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await createResponse).status()).toBe(409)
    await expect(
      page.locator('.ui-pnotify-title', { hasText: /error creating priority/i }),
    ).toBeVisible({ timeout: 5000 })
    await expect(modal).toBeVisible()

    const items = (await listPriorities(page)).filter((p) => p.name === name)
    expect(items.length, 'only one rule should exist with this name').toBe(1)
  })

  // ---------------------------------------------------------------------
  // Scenario 10 — Compute users priorities for a selected rule_id
  // ---------------------------------------------------------------------
  test('S10: Compute populates the users-priorities table', async ({
    authenticatedPage: page,
  }) => {
    await gotoPriority(page)

    // The page populates the *Computed users priorities* dropdown on
    // init via /priority-rules. Scope to that <select> — the same `id`
    // is reused by `<input>` fields inside the Add/Edit modals.
    const computeSelect = page.locator('select#priority').first()
    await expect(computeSelect.locator('option[value="test-booking-rule"]'))
      .toHaveCount(1, { timeout: 10000 })
    await computeSelect.selectOption('test-booking-rule')

    await page.locator('.btn-compute').first().click()

    const computeResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/items/bookings/priorities') &&
        r.request().method() === 'POST',
      { timeout: 20000 },
    )
    await clickPnotifyOk(page)
    const resp = await computeResponse
    expect(resp.status()).toBeLessThan(400)
    const body = resp.request().postDataJSON()
    expect(body.rule_id).toBe('test-booking-rule')

    // Table must render at least one user row (seed has user01..03 etc).
    await expect(
      page.locator('#bookings_priority_computed tbody tr:not(.dataTables_empty)').first(),
    ).toBeVisible({ timeout: 10000 })
  })
})
