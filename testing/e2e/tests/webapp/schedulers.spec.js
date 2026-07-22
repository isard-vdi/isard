import { test, expect, unwrap } from '../../fixtures/apiv4/index.js'
import {
  adminSchedulerJobsSystem,
  adminTableDelete,
  adminTableList,
} from '../../src/gen/apiv4/sdk.gen'

const SCHEDULERS_URL = '/isard-admin/admin/schedulers'

async function gotoSchedulers(page) {
  await page.goto(SCHEDULERS_URL)
  await page
    .locator('#desktops_priority ~ .dataTables_wrapper, .dataTables_wrapper:has(#desktops_priority)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  await page
    .locator('#table-scheduler ~ .dataTables_wrapper, .dataTables_wrapper:has(#table-scheduler)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  await page
    .locator('#desktops_priority tbody tr:not(.dataTables_empty)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
}

async function clickPnotifyOk(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^ok$/i })
    .first()
    .click({ timeout: 5000 })
}

async function listDesktopTimeouts(client) {
  const data = await unwrap(
    adminTableList({ client, path: { table: 'desktops_priority' }, body: { order_by: 'name' } }),
  ).catch(() => [])
  return Array.isArray(data) ? data : []
}

async function findDesktopTimeoutByName(client, name) {
  const rows = await listDesktopTimeouts(client)
  return rows.find((r) => r.name === name) || null
}

async function listSystemJobs(client) {
  const jobs = await unwrap(adminSchedulerJobsSystem({ client })).catch(() => [])
  return Array.isArray(jobs) ? jobs : []
}

async function deleteTimeoutViaUi(page, id) {
  const row = page.locator(`#desktops_priority tbody tr[id="${id}"]`)
  await expect(row).toHaveCount(1)

  await row.locator('button#btn-delete').click()

  const delResp = page.waitForResponse(
    (r) =>
      r.url().includes(`/api/v4/admin/item/table/desktops_priority/${id}`) &&
      r.request().method() === 'DELETE',
    { timeout: 15000 },
  )
  await clickPnotifyOk(page)
  expect((await delResp).status()).toBeLessThan(400)
  await expect(row).toBeHidden({ timeout: 10000 })
}

// Best-effort backend cleanup for use in finally blocks — does not assert,
// so a failing UI delete in the test body still surfaces as the real failure.
async function cleanupTimeout(client, id) {
  if (!id) return
  await adminTableDelete({
    client,
    path: { table: 'desktops_priority', item_id: id },
  }).catch(() => {})
}

async function createJobViaUi(page, apiv4Admin) {
  const before = await listSystemJobs(apiv4Admin)
  const beforeIds = new Set(before.map((j) => j.id))

  const actionsResp = page.waitForResponse(
    (r) => r.url().includes('/scheduler/actions') && r.request().method() === 'GET',
    { timeout: 15000 },
  )
  await page.locator('.btn-scheduler').first().click()
  const modal = page.locator('#modalScheduler')
  await modal.waitFor({ state: 'visible', timeout: 10000 })
  expect((await actionsResp).status()).toBeLessThan(400)

  // Wait until scheduler actions are loaded.
  await expect
    .poll(async () => await modal.locator('#action option:not([value=""])').count(), { timeout: 15000 })
    .toBeGreaterThan(0)

  await modal.locator('#kind').selectOption('interval')
  await expect(modal.locator('#kind')).toHaveValue('interval')
  await modal.locator('#hour').selectOption('01')
  await expect(modal.locator('#hour')).toHaveValue('01')
  await modal.locator('#minute').selectOption('05')
  await expect(modal.locator('#minute')).toHaveValue('05')

  const firstActionValue = await modal.locator('#action').evaluate((el) => {
    const option = Array.from(el.options).find((opt) => opt.value)
    return option ? option.value : null
  })
  expect(firstActionValue).toBeTruthy()

  const actionSchemaResp = page.waitForResponse(
    (r) => r.url().includes(`/scheduler/action/${firstActionValue}`) && r.request().method() === 'GET',
    { timeout: 15000 },
  )
  await modal.locator('#action').selectOption(firstActionValue)
  expect((await actionSchemaResp).status()).toBeLessThan(400)
  await expect(modal.locator('#action')).toHaveValue(firstActionValue)

  const createResp = page.waitForResponse(
    (r) => r.url().includes('/scheduler/system/') && r.request().method() === 'POST',
    { timeout: 15000 },
  )
  await modal.locator('#send').click()

  expect((await createResp).status()).toBeLessThan(400)
  await modal.waitFor({ state: 'hidden', timeout: 10000 })

  await expect.poll(async () => {
    const after = await listSystemJobs(apiv4Admin)
    const created = after.find((j) => !beforeIds.has(j.id))
    return created?.id ?? null
  }, { timeout: 15000 }).not.toBeNull()

  const after = await listSystemJobs(apiv4Admin)
  return after.find((j) => !beforeIds.has(j.id))
}

async function createJobViaApi(page, apiv4Admin) {
  const before = await listSystemJobs(apiv4Admin)
  const beforeIds = new Set(before.map((j) => j.id))

  const actionsResp = await page.request.get('/scheduler/actions')
  expect(actionsResp.status()).toBeLessThan(400)
  const actions = await actionsResp.json().catch(() => [])
  const action = Array.isArray(actions) ? actions.find((a) => a?.id) : null
  expect(action?.id).toBeTruthy()

  const createResp = await page.request.post(`/scheduler/system/interval/${action.id}/01/05`, {
    data: { kwargs: {} },
  })
  expect(createResp.status()).toBeLessThan(400)

  await expect
    .poll(async () => {
      const after = await listSystemJobs(apiv4Admin)
      const created = after.find((j) => !beforeIds.has(j.id))
      return created?.id ?? null
    }, { timeout: 15000 })
    .not.toBeNull()

  const after = await listSystemJobs(apiv4Admin)
  return after.find((j) => !beforeIds.has(j.id))
}

async function deleteJobViaUi(page, jobId) {
  const row = page.locator(`#table-scheduler tbody tr[id="${jobId}"]`)
  await expect(row).toBeVisible({ timeout: 10000 })
  await row.locator('button#btn-scheduler-delete').click()

  const delResp = page.waitForResponse(
    (r) => r.url().includes(`/scheduler/${jobId}`) && r.request().method() === 'DELETE',
    { timeout: 15000 },
  )
  await clickPnotifyOk(page)
  expect((await delResp).status()).toBeLessThan(400)
  await expect(row).toBeHidden({ timeout: 10000 })
}

test.describe('Config — Schedulers (admin webapp)', () => {
  test.describe.configure({ mode: 'serial' })

  test('A1: initial load of Schedulers page', async ({ authenticatedPage: page }) => {
    const timeoutResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/items/table/desktops_priority') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    const jobsResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/items/scheduler/jobs/system') && r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await gotoSchedulers(page)

    expect((await timeoutResp).status()).toBeLessThan(400)
    expect((await jobsResp).status()).toBeLessThan(400)

    await expect(page.getByRole('heading', { name: /desktops timeouts/i })).toBeVisible()
    await expect(page.getByRole('heading', { name: /job scheduler/i })).toBeVisible()
  })

  test('A2: create timeout rule (desktops priority)', async ({ authenticatedPage: page, apiv4Admin }) => {
    const name = `e2e-timeout-${Date.now()}`
    let createdId = null

    try {
      await gotoSchedulers(page)

      await page.locator('.add-new').first().click()
      const modal = page.locator('#modalAddPriority')
      await modal.waitFor({ state: 'visible', timeout: 10000 })

      await modal.locator('#modalAdd #name').fill(name)
      await modal.locator('#modalAdd #description').fill('e2e timeout create')
      await modal.locator('#modalAdd #priority').fill('111')
      await modal.locator('#modalAdd #max_time').fill('210')
      await modal.locator('#modalAdd #warning_time').fill('-20')
      await modal.locator('#modalAdd #danger_time').fill('-10')

      const createResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/table/add/desktops_priority') && r.request().method() === 'POST',
        { timeout: 15000 },
      )
      await modal.locator('#send').click()

      expect((await createResp).status()).toBeLessThan(400)
      await modal.waitFor({ state: 'hidden', timeout: 10000 })

      const created = await findDesktopTimeoutByName(apiv4Admin, name)
      expect(created).not.toBeNull()
      createdId = created.id

      await expect(page.locator(`#desktops_priority tbody tr[id="${created.id}"]`)).toBeVisible({ timeout: 10000 })
    } finally {
      await cleanupTimeout(apiv4Admin, createdId)
    }
  })

  test('A3: edit timeout rule', async ({ authenticatedPage: page, apiv4Admin }) => {
    const name = `e2e-timeout-edit-${Date.now()}`
    let createdId = null

    try {
      await gotoSchedulers(page)
      await page.locator('.add-new').first().click()
      const addModal = page.locator('#modalAddPriority')
      await addModal.waitFor({ state: 'visible', timeout: 10000 })

      await addModal.locator('#modalAdd #name').fill(name)
      await addModal.locator('#modalAdd #description').fill('before edit')
      await addModal.locator('#modalAdd #priority').fill('112')
      await addModal.locator('#modalAdd #max_time').fill('220')
      await addModal.locator('#modalAdd #warning_time').fill('-20')
      await addModal.locator('#modalAdd #danger_time').fill('-10')

      const createResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/table/add/desktops_priority') && r.request().method() === 'POST',
        { timeout: 15000 },
      )
      await addModal.locator('#send').click()
      expect((await createResp).status()).toBeLessThan(400)
      await addModal.waitFor({ state: 'hidden', timeout: 10000 })

      const created = await findDesktopTimeoutByName(apiv4Admin, name)
      expect(created).not.toBeNull()
      createdId = created.id

      const row = page.locator(`#desktops_priority tbody tr[id="${created.id}"]`)
      await expect(row).toBeVisible({ timeout: 10000 })
      await row.locator('button#btn-edit').click()

      const editModal = page.locator('#modalEditPriority')
      await editModal.waitFor({ state: 'visible', timeout: 10000 })

      await editModal.locator('#modalEdit #description').fill('after edit')
      await editModal.locator('#modalEdit #priority').fill('113')

      const updateResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/table/update/desktops_priority') && r.request().method() === 'PUT',
        { timeout: 15000 },
      )
      await editModal.locator('#send').click()

      expect((await updateResp).status()).toBeLessThan(400)
      await editModal.waitFor({ state: 'hidden', timeout: 10000 })

      const persisted = await findDesktopTimeoutByName(apiv4Admin, name)
      expect(persisted?.description).toBe('after edit')
      expect(Number(persisted?.priority)).toBe(113)
    } finally {
      await cleanupTimeout(apiv4Admin, createdId)
    }
  })

  test('A4: update alloweds for timeout rule', async ({ authenticatedPage: page, apiv4Admin }) => {
    const name = `e2e-timeout-alloweds-${Date.now()}`
    let createdId = null

    try {
      // Create target via UI first.
      await gotoSchedulers(page)
      await page.locator('.add-new').first().click()
      const addModal = page.locator('#modalAddPriority')
      await addModal.waitFor({ state: 'visible', timeout: 10000 })

      await addModal.locator('#modalAdd #name').fill(name)
      await addModal.locator('#modalAdd #description').fill('alloweds target')
      await addModal.locator('#modalAdd #priority').fill('114')
      await addModal.locator('#modalAdd #max_time').fill('210')
      await addModal.locator('#modalAdd #warning_time').fill('-20')
      await addModal.locator('#modalAdd #danger_time').fill('-10')

      const createResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/table/add/desktops_priority') && r.request().method() === 'POST',
        { timeout: 15000 },
      )
      await addModal.locator('#send').click()
      expect((await createResp).status()).toBeLessThan(400)
      await addModal.waitFor({ state: 'hidden', timeout: 10000 })

      const created = await findDesktopTimeoutByName(apiv4Admin, name)
      expect(created).not.toBeNull()
      createdId = created.id

      const prefill = page.waitForResponse(
        (r) => r.url().includes('/api/v4/item/allowed/table/desktops_priority') && r.request().method() === 'POST',
        { timeout: 15000 },
      )
      const row = page.locator(`#desktops_priority tbody tr[id="${created.id}"]`)
      await row.locator('button#btn-alloweds').click()

      const modal = page.locator('#modalAlloweds')
      await modal.waitFor({ state: 'visible', timeout: 10000 })

      expect((await prefill).status()).toBeLessThan(400)

      const saveResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/item/allowed/update/desktops_priority') && r.request().method() === 'POST',
        { timeout: 15000 },
      )
      await modal.locator('#send').click()
      expect((await saveResp).status()).toBeLessThan(400)
      await modal.waitFor({ state: 'hidden', timeout: 10000 })

      // Verify roundtrip read endpoint is still healthy after save.
      const verifyResp = await page.request.post('/api/v4/item/allowed/table/desktops_priority', {
        data: { id: created.id },
      })
      expect(verifyResp.status()).toBeLessThan(400)
    } finally {
      await cleanupTimeout(apiv4Admin, createdId)
    }
  })

  test('A5: delete timeout rule', async ({ authenticatedPage: page, apiv4Admin }) => {
    const name = `e2e-timeout-delete-${Date.now()}`
    let createdId = null

    try {
      await gotoSchedulers(page)
      await page.locator('.add-new').first().click()

      const addModal = page.locator('#modalAddPriority')
      await addModal.waitFor({ state: 'visible', timeout: 10000 })
      await addModal.locator('#modalAdd #name').fill(name)
      await addModal.locator('#modalAdd #description').fill('to delete')
      await addModal.locator('#modalAdd #priority').fill('115')
      await addModal.locator('#modalAdd #max_time').fill('210')
      await addModal.locator('#modalAdd #warning_time').fill('-20')
      await addModal.locator('#modalAdd #danger_time').fill('-10')

      const createResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/table/add/desktops_priority') && r.request().method() === 'POST',
        { timeout: 15000 },
      )
      await addModal.locator('#send').click()
      expect((await createResp).status()).toBeLessThan(400)
      await addModal.waitFor({ state: 'hidden', timeout: 10000 })

      const created = await findDesktopTimeoutByName(apiv4Admin, name)
      expect(created).not.toBeNull()
      createdId = created.id

      await deleteTimeoutViaUi(page, created.id)
      expect(await findDesktopTimeoutByName(apiv4Admin, name)).toBeNull()
      createdId = null
    } finally {
      await cleanupTimeout(apiv4Admin, createdId)
    }
  })

  test('A6: create scheduler job', async ({ authenticatedPage: page, apiv4Admin }) => {
    await gotoSchedulers(page)

    const actionsHealth = await page.request.get('/scheduler/actions').catch(() => null)
    const actionsStatus = actionsHealth?.status?.() ?? 0
    test.skip(
      !actionsHealth || actionsStatus >= 500,
      `Scheduler actions endpoint unavailable in this environment (${actionsStatus || 'no response'})`,
    )

    const createdJob = await createJobViaUi(page, apiv4Admin)
    expect(createdJob?.id).toBeTruthy()

    // Cleanup to avoid global cross-test pollution.
    await deleteJobViaUi(page, createdJob.id)
  })

  test('A7: delete scheduler job', async ({ authenticatedPage: page, apiv4Admin }) => {
    await gotoSchedulers(page)

    const actionsHealth = await page.request.get('/scheduler/actions').catch(() => null)
    const actionsStatus = actionsHealth?.status?.() ?? 0
    test.skip(
      !actionsHealth || actionsStatus >= 500,
      `Scheduler actions endpoint unavailable in this environment (${actionsStatus || 'no response'})`,
    )

    const createdJob = await createJobViaApi(page, apiv4Admin)
    expect(createdJob?.id).toBeTruthy()

    await deleteJobViaUi(page, createdJob.id)

    const jobsAfter = await listSystemJobs(apiv4Admin)
    expect(jobsAfter.find((j) => j.id === createdJob.id)).toBeUndefined()
  })
})
