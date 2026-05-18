// Drives the Bookables → Resources admin page. Mirrors
// testing/e2e/specs/webapp/bookables/resources.md — each test(...) maps to
// a numbered scenario in that spec.
//
// Conventions:
//   - This file mutates the shared seed bookable NVIDIA-T4-2Q. To avoid
//     races between parallel workers within the file, the describe block
//     runs in `serial` mode. Workers can still parallelize across other
//     spec files (Priority, Events, GPUs).
//   - The seed snapshot (name/description/priority_id + alloweds) is
//     captured once per worker in `beforeAll` and restored after every
//     test by `afterEach`, even on failure.

import { test, expect, apiv4ClientForPage, unwrap } from '../../../fixtures/apiv4/index.js'
import {
  adminAllowedUpdate,
  adminTableList,
  adminTableUpdate,
} from '../../../src/gen/apiv4/sdk.gen'

const TARGET_BOOKABLE_ID = 'NVIDIA-T4-2Q'
const RESOURCES_URL = '/isard-admin/admin/domains/render/Bookables'
const VALID_NAME_RE = /^[\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/

async function listBookables(client) {
  const data = await unwrap(
    adminTableList({ client, path: { table: 'reservables_vgpus' }, body: { order_by: 'name' } }),
  ).catch(() => [])
  return Array.isArray(data) ? data : []
}

async function fetchBookable(client, id) {
  const items = await listBookables(client)
  return items.find((b) => b.id === id) || null
}

async function fetchRawAllowed(client, id) {
  // The raw row holds canonical ids-only allowed; `/allowed/table` would enrich
  // it, and round-tripping that back through `/admin/allowed/update` corrupts the row.
  const row = await fetchBookable(client, id)
  return row?.allowed ?? null
}

async function updateBookable(client, payload) {
  return adminTableUpdate({ client, path: { table: 'reservables_vgpus' }, body: payload })
}

async function restoreBookable(client, id, original) {
  if (!original) return
  await updateBookable(client, {
    id,
    name: original.name,
    description: original.description ?? '',
    priority_id: original.priority_id,
  }).catch(() => {})
}

async function restoreAlloweds(client, id, original) {
  if (!original) return
  await adminAllowedUpdate({
    client,
    path: { table: 'reservables_vgpus' },
    body: { id, table: 'reservables_vgpus', allowed: original },
  }).catch(() => {})
}

async function gotoResources(page) {
  await page.goto(RESOURCES_URL)
  await page
    .locator(
      '#reservables_vgpus ~ .dataTables_wrapper, .dataTables_wrapper:has(#reservables_vgpus)',
    )
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  await page
    .locator('#reservables_vgpus tbody tr:not(.dataTables_empty)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
}

function uniqueBookableName(testInfo, suffix = '') {
  return `e2e-vgpu-${testInfo.workerIndex}-${Date.now()}${suffix ? `-${suffix}` : ''}`
}

test.describe.configure({ mode: 'serial' })

test.describe('Admin Bookables — Resources', () => {
  let originalSnapshot = null
  let originalAlloweds = null

  test.beforeAll(async ({ authenticatedContext }) => {
    const page = await authenticatedContext.newPage()
    const client = apiv4ClientForPage(page)
    originalSnapshot = await fetchBookable(client, TARGET_BOOKABLE_ID)
    originalAlloweds = await fetchRawAllowed(client, TARGET_BOOKABLE_ID)
    await page.close()
  })

  test.afterEach(async ({ apiv4Admin }) => {
    if (originalSnapshot) {
      await restoreBookable(apiv4Admin, TARGET_BOOKABLE_ID, originalSnapshot)
    }
    if (originalAlloweds) {
      await restoreAlloweds(apiv4Admin, TARGET_BOOKABLE_ID, originalAlloweds)
    }
  })

  // ---------------------------------------------------------------------
  // Scenario 1 — lists vGPU bookables from the seed
  // ---------------------------------------------------------------------
  test('S1: lists vGPU bookables from the seed', async ({ authenticatedPage: page, apiv4Admin }) => {
    const tableResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/table/reservables_vgpus') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await page.goto(RESOURCES_URL)
    const resp = await tableResponse
    expect(resp.status()).toBeLessThan(400)

    const items = await listBookables(apiv4Admin)
    const ids = new Set(items.map((b) => b.id))
    expect(ids).toContain('NVIDIA-A16-2Q')
    expect(ids).toContain('NVIDIA-A16-4Q')
    expect(ids).toContain('NVIDIA-T4-2Q')

    await page
      .locator(
        '#reservables_vgpus ~ .dataTables_wrapper, .dataTables_wrapper:has(#reservables_vgpus)',
      )
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })

    for (const id of ['NVIDIA-A16-2Q', 'NVIDIA-A16-4Q', 'NVIDIA-T4-2Q']) {
      await expect(page.locator(`#reservables_vgpus tbody tr[id="${id}"]`))
        .toBeVisible({ timeout: 10000 })
    }
  })

  // ---------------------------------------------------------------------
  // Scenario 2 — edits name and description
  // ---------------------------------------------------------------------
  test('S2: edits name and description via the pencil icon', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const newName = uniqueBookableName(testInfo, 's2')
    const newDescription = `e2e vGPU bookable updated at ${new Date().toISOString()}`
    expect(newName).toMatch(VALID_NAME_RE)

    await gotoResources(page)
    const row = page.locator(`#reservables_vgpus tbody tr[id="${TARGET_BOOKABLE_ID}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-edit').click()

    const modal = page.locator('#modalEditBookable')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#name')).toHaveValue(originalSnapshot.name)
    await expect(modal.locator('#description')).toHaveValue(
      originalSnapshot.description ?? '',
    )
    // Dropdown is populated async via /priority-rules — wait for the
    // current value to appear before submitting.
    await expect(
      modal.locator(`#priority option[value="${originalSnapshot.priority_id}"]`),
    ).toHaveCount(1, { timeout: 5000 })

    await modal.locator('#name').fill(newName)
    await modal.locator('#description').fill(newDescription)

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/table/update/reservables_vgpus') &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(row).toContainText(newName, { timeout: 10000 })
    await expect(row).toContainText(newDescription)

    const persisted = await fetchBookable(apiv4Admin, TARGET_BOOKABLE_ID)
    expect(persisted.name).toBe(newName)
    expect(persisted.description).toBe(newDescription)
  })

  // ---------------------------------------------------------------------
  // Scenario 3 — changes the priority rule
  // ---------------------------------------------------------------------
  test('S3: changes the priority rule via the dropdown', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    // T4-2Q starts on `test-booking-rule`; switching to `default` is the
    // smallest visible change without touching values we want to restore.
    expect(originalSnapshot.priority_id).toBe('test-booking-rule')

    await gotoResources(page)
    const row = page.locator(`#reservables_vgpus tbody tr[id="${TARGET_BOOKABLE_ID}"]`)
    await row.locator('button#btn-edit').click()

    const modal = page.locator('#modalEditBookable')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#priority option[value="default"]')).toHaveCount(1, {
      timeout: 5000,
    })
    await modal.locator('#priority').selectOption('default')

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/table/update/reservables_vgpus') &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await editResponse
    expect(resp.status()).toBeLessThan(400)
    const body = resp.request().postDataJSON()
    expect(body?.priority_id).toBe('default')
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(row.locator('td').nth(3)).toHaveText('default', { timeout: 10000 })

    const persisted = await fetchBookable(apiv4Admin, TARGET_BOOKABLE_ID)
    expect(persisted.priority_id).toBe('default')
  })

  // ---------------------------------------------------------------------
  // Scenario 4 — manages alloweds for a bookable
  // ---------------------------------------------------------------------
  test('S4: alloweds modal saves and the new state hydrates on reopen', async ({
    authenticatedPage: page,
  }) => {
    await gotoResources(page)
    const row = page.locator(`#reservables_vgpus tbody tr[id="${TARGET_BOOKABLE_ID}"]`)
    const modal = page.locator('#modalAlloweds')

    // iCheck syncs the (opacity:0) <input> async — poll it, not wrapper classes.
    const rolesCbChecked = () =>
      page.evaluate(() => document.querySelector('#a-roles-cb')?.checked ?? null)

    const openModal = async () => {
      const prefill = page.waitForResponse(
        (r) =>
          r.url().includes('/api/v4/allowed/table/reservables_vgpus') &&
          r.request().method() === 'POST',
        { timeout: 15000 },
      )
      await row.locator('button#btn-alloweds').click()
      await modal.waitFor({ state: 'visible', timeout: 10000 })
      const resp = await prefill
      expect(resp.status()).toBeLessThan(400)
      return resp
    }

    // --- First open: derive expected state from the response, then flip ---
    const initialResp = await openModal()
    const initialBody = await initialResp.json().catch(() => ({}))
    // Mirrors `if(value)` in modalAllowedsFormShow — `[]` is truthy in JS too.
    const initialChecked = Boolean(initialBody.roles)
    await expect.poll(rolesCbChecked, { timeout: 5000 }).toBe(initialChecked)

    // The real <input> is hidden by iCheck — click the overlay helper.
    await modal
      .locator('#roles_pannel .iCheck-helper')
      .first()
      .click({ force: true })
    await expect.poll(rolesCbChecked, { timeout: 5000 }).toBe(!initialChecked)

    const updateResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/allowed/update/reservables_vgpus') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const upd = await updateResponse
    expect(upd.status()).toBeLessThan(400)
    const body = upd.request().postDataJSON()
    expect(body.id).toBe(TARGET_BOOKABLE_ID)
    expect(body.table).toBe('reservables_vgpus')

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /alloweds updated successfully/i }),
    ).toBeVisible({ timeout: 5000 })
    await modal.waitFor({ state: 'hidden', timeout: 5000 })

    // --- Reopen: the persisted state must rehydrate flipped ---
    await openModal()
    await expect.poll(rolesCbChecked, { timeout: 5000 }).toBe(!initialChecked)
  })

  // ---------------------------------------------------------------------
  // Scenario 5 — alloweds viewer at the row detail
  // ---------------------------------------------------------------------
  test('S5: expanding a row renders the alloweds viewer', async ({
    authenticatedPage: page,
  }) => {
    // NVIDIA-A16-2Q has roles=[admin] in the seed — gives the viewer
    // something concrete to render instead of the "Everyone" branch.
    const ID = 'NVIDIA-A16-2Q'

    await gotoResources(page)
    const row = page.locator(`#reservables_vgpus tbody tr[id="${ID}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    const viewerResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/allowed/table/reservables_vgpus') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await row.locator('td.details-control button').first().click()
    expect((await viewerResponse).status()).toBeLessThan(400)

    const allowedsTable = page.locator(`#table-alloweds-${ID}`)
    await expect(allowedsTable).toBeVisible({ timeout: 10000 })
    await expect(allowedsTable.locator('tbody tr').first()).toBeVisible({
      timeout: 5000,
    })
  })

  // ---------------------------------------------------------------------
  // Scenario 6 — Parsley blocks invalid names on edit
  // ---------------------------------------------------------------------
  test('S6: Parsley blocks the edit when the name is invalid', async ({
    authenticatedPage: page,
  }) => {
    await gotoResources(page)
    const row = page.locator(`#reservables_vgpus tbody tr[id="${TARGET_BOOKABLE_ID}"]`)
    await row.locator('button#btn-edit').click()
    const modal = page.locator('#modalEditBookable')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    // Wait for the priority dropdown to be ready before the user could
    // actually attempt to submit.
    await expect(modal.locator('#priority option').first()).toHaveCount(1, {
      timeout: 5000,
    })

    let putFired = false
    page.on('request', (req) => {
      if (
        req.url().includes('/api/v4/admin/table/update/reservables_vgpus') &&
        req.method() === 'PUT'
      ) {
        putFired = true
      }
    })

    // 50-char maxlength on the input means "too long" can't be exercised
    // through fill(); cover the other three invalid branches.
    const cases = ['abc', 'vgpu@1', 'my/vgpu', '']
    for (const candidate of cases) {
      await modal.locator('#name').fill(candidate)
      await modal.locator('#send').click()
      await expect(modal).toBeVisible()
      await expect(modal.locator('#name')).toHaveClass(/parsley-error/)
    }
    expect(putFired, 'PUT must not fire when the name is invalid').toBeFalsy()
  })

  // ---------------------------------------------------------------------
  // Scenario 7 — empty list when no bookables exist
  // ---------------------------------------------------------------------
  test.skip('S7: shows an empty table when no bookables exist', async () => {
    // The shared seed always provides three bookables; this branch only
    // makes sense against a freshly-initialised dev DB with no GPUs
    // configured. Left as a placeholder so the scenario number matches
    // the spec.
  })

  // ---------------------------------------------------------------------
  // Scenario 8 — Bookables ↔ GPUs cross-check (delegated)
  // ---------------------------------------------------------------------
  test.skip('S8: cross-check with Hypervisors → GPUs (covered by gpus.spec.js)', async () => {
    // Delegated to testing/e2e/tests/webapp/gpus.spec.js (Scenario 13).
    // Kept here as a skipped placeholder so the spec/test mapping stays
    // 1:1 with resources.md.
  })
})
