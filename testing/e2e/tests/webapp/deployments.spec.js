// Drives the Deployments admin flows on /isard-admin/admin/domains/render/Deployments.
// Mirrors testing/e2e/specs/webapp/deployments.md — each test(...) maps to a
// numbered scenario in that spec.
//
// Conventions:
//   - Deployments are created via createDeployment SDK call in each test that
//     needs one, with unique names scoped to this worker.
//   - Created deployment IDs are pushed to testInfo.annotations (type
//     "deployment-id") so afterEach can always clean up even on failure.
//   - sharedTemplateId is resolved once per worker in beforeAll and reused.

import { test, expect, apiv4ClientForPage, unwrap } from '../../fixtures/apiv4/index.js'
import {
  createDeployment,
  deleteDeployment,
  getDeploymentCoOwners,
  updateDeploymentCoOwners,
  adminSearchUsers,
  adminTableList,
} from '../../src/gen/apiv4/sdk.gen'
import { getFirstAllowedTemplate } from '../../fixtures/apiv4/desktops.js'

const DEPLOYMENTS_URL = '/isard-admin/admin/domains/render/Deployments'

// ─── pure helpers ────────────────────────────────────────────────────────────

function uniqueDeploymentName(testInfo, suffix = '') {
  return `e2e-dep-${testInfo.workerIndex}-${Date.now()}${suffix ? `-${suffix}` : ''}`
}

async function listAllDeployments(client) {
  const data = await unwrap(
    adminTableList({ client, path: { table: 'deployments' }, body: { order_by: 'name' } }),
  ).catch(() => [])
  return Array.isArray(data) ? data : []
}

async function createDeploymentViaApi(client, testInfo, templateId, name) {
  const result = await createDeployment({
    client,
    body: {
      name,
      description: 'e2e test deployment',
      // Use a non-existent group ID so the validator accepts the request
      // (non-empty list = truthy) but get_all returns zero users, meaning
      // no desktops are ever created. Combined with create_owner_desktop: false
      // this guarantees the deployment has zero domain rows.
      allowed: { users: false, groups: ['00000000-0000-0000-0000-000000000000'] },
      create_owner_desktop: false,
      desktops: [{ template_id: templateId, name: `desktop-${name}` }],
    },
  })
  if (result.error !== undefined && result.data === undefined) {
    throw new Error(`createDeployment failed: ${JSON.stringify(result.error)}`)
  }
  const id = result.data?.id
  if (!id) throw new Error('createDeployment: no id in response')
  testInfo.annotations.push({ type: 'deployment-id', description: id })
  return { id, name }
}

async function deleteDeploymentViaApi(client, deploymentId) {
  await deleteDeployment({
    client,
    path: { deployment_id: deploymentId },
    query: { permanent: true },
  }).catch(() => {})
}

// ─── page helpers ────────────────────────────────────────────────────────────

async function gotoDeployments(page) {
  await page.goto(DEPLOYMENTS_URL)
  await page
    .locator('.dataTables_wrapper:has(#deployments)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  await page
    .locator('#deployments tbody tr:not(.dataTables_empty)')
    .first()
    .waitFor({ state: 'visible', timeout: 20000 })
}

// Navigate (with retries) until the given deployment row is visible.
async function findDeploymentRow(page, deploymentId, maxAttempts = 3) {
  let lastError
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await gotoDeployments(page)
    const row = page.locator(`#deployments tbody tr[id="${deploymentId}"]`)
    try {
      await expect(row).toBeVisible({ timeout: 8000 })
      return row
    } catch (err) {
      lastError = err
    }
  }
  throw lastError
}

// Navigate until both rows are visible (used by bulk-delete scenarios).
async function findBothRows(page, id1, id2, maxAttempts = 3) {
  let lastError
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await gotoDeployments(page)
    try {
      await expect(page.locator(`#deployments tbody tr[id="${id1}"]`)).toBeVisible({ timeout: 8000 })
      await expect(page.locator(`#deployments tbody tr[id="${id2}"]`)).toBeVisible({ timeout: 8000 })
      return
    } catch (err) {
      lastError = err
    }
  }
  throw lastError
}

// Click the expand (+) button on a deployment row and wait for the detail
// panel to render.  Returns the detail panel locator.
async function expandDeploymentRow(page, deploymentId) {
  const expandBtn = page
    .locator(`#deployments tbody tr[id="${deploymentId}"] td.details-control button`)
    .first()
  await expandBtn.scrollIntoViewIfNeeded()
  await expandBtn.click()
  const detailPanel = page.locator(`[id="actions-${deploymentId}"]`)
  await detailPanel.waitFor({ state: 'visible', timeout: 10000 })
  return detailPanel
}

// Confirm a PNotify prompt by clicking the "Ok" action button.
async function clickPnotifyOk(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^ok$/i })
    .first()
    .click({ timeout: 5000 })
}

// ─── describe ────────────────────────────────────────────────────────────────

test.describe('Admin Deployments — webapp', () => {
  // One template ID per worker, resolved in beforeAll.
  let sharedTemplateId = null

  test.beforeAll(async ({ authenticatedContext }, workerInfo) => {
    const page = await authenticatedContext.newPage()
    try {
      const client = apiv4ClientForPage(page)
      // Delete stale e2e deployments left by aborted previous runs on this worker.
      const prefix = `e2e-dep-${workerInfo.workerIndex}-`
      const all = await listAllDeployments(client)
      for (const d of all.filter((dep) => dep.name?.startsWith(prefix))) {
        await deleteDeploymentViaApi(client, d.id)
      }
      // Cache the template ID so individual tests don't each need to fetch it.
      const template = await getFirstAllowedTemplate(client).catch(() => null)
      sharedTemplateId = template?.id ?? null
    } finally {
      await page.close()
    }
  })

  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    const ids = testInfo.annotations
      .filter((a) => a.type === 'deployment-id')
      .map((a) => a.description)
    for (const id of ids) {
      await deleteDeploymentViaApi(apiv4Admin, id)
    }
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S1 — admin sees the deployments table loaded
  // ──────────────────────────────────────────────────────────────────────────
  test('S1: deployments DataTable loads with columns and row controls', async ({
    authenticatedPage: page,
  }) => {
    const tableResponse = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/items/table/deployments'),
      { timeout: 15000 },
    )
    await page.goto(DEPLOYMENTS_URL)
    expect((await tableResponse).status()).toBeLessThan(400)

    await page
      .locator('.dataTables_wrapper:has(#deployments)')
      .waitFor({ state: 'visible', timeout: 15000 })
    await page
      .locator('#deployments tbody tr:not(.dataTables_empty)')
      .first()
      .waitFor({ state: 'visible', timeout: 20000 })

    // Expected column headers — use exact regex to avoid e.g. 'Name' matching 'Desktop Name'
    for (const col of ['Name', 'User(owner)', 'Co-owners', 'Desktops', 'Running']) {
      const exact = new RegExp('^' + col.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$')
      await expect(page.locator('#deployments thead th').filter({ hasText: exact })).toBeVisible()
    }

    // Every data row must have: expand button, delete button, select checkbox
    const firstRow = page.locator('#deployments tbody tr:not(.dataTables_empty)').first()
    await expect(firstRow.locator('td.details-control button')).toBeVisible()
    await expect(firstRow.locator('button#btn-delete')).toBeVisible()
    await expect(firstRow.locator('.select-checkbox input[type="checkbox"]')).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S2a — admin expands a deployment row and sees the detail panel
  // ──────────────────────────────────────────────────────────────────────────
  test('S2a: expanding a row shows Target users section and action buttons', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const name = uniqueDeploymentName(testInfo, 's2a')
    const dep = await createDeploymentViaApi(apiv4Admin, testInfo, sharedTemplateId, name)

    // Register the alloweds listener before the expand click triggers it.
    const allowedsResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/item/allowed/table/deployments') &&
        r.request().method() === 'POST',
      { timeout: 10000 },
    )

    await findDeploymentRow(page, dep.id)
    const detailPanel = await expandDeploymentRow(page, dep.id)
    await allowedsResponse

    await expect(detailPanel.locator('.btn-owner')).toBeVisible()
    await expect(detailPanel.locator('.btn-co-owners')).toBeVisible()

    const allowedsSection = page.locator(`#alloweds-${dep.id}`)
    await expect(allowedsSection.locator('h3', { hasText: /target users/i })).toBeVisible()
    await expect(
      allowedsSection.locator(`#table-alloweds-${dep.id} thead th`).filter({ hasText: /^type$/i }),
    ).toBeVisible()
    await expect(
      allowedsSection.locator(`#table-alloweds-${dep.id} thead th`).filter({ hasText: /^items$/i }),
    ).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S2b — admin expands a deployment row and sees the hardware panel
  // ──────────────────────────────────────────────────────────────────────────
  test('S2b: expanding a row shows hardware panel populated', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const name = uniqueDeploymentName(testInfo, 's2b')
    const dep = await createDeploymentViaApi(apiv4Admin, testInfo, sharedTemplateId, name)

    const hardwareResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/deployment/${dep.id}/hardware`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await findDeploymentRow(page, dep.id)
    await expandDeploymentRow(page, dep.id)

    expect((await hardwareResponse).status()).toBeLessThan(400)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S3 — admin deletes a deployment without started desktops
  // ──────────────────────────────────────────────────────────────────────────
  test('S3: deletes a deployment without started desktops', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const name = uniqueDeploymentName(testInfo, 's3')
    const dep = await createDeploymentViaApi(apiv4Admin, testInfo, sharedTemplateId, name)

    const row = await findDeploymentRow(page, dep.id)
    await row.locator('button#btn-delete').click()

    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/deployment/${dep.id}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await deleteResponse).status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /deleted/i }),
    ).toBeVisible({ timeout: 5000 })

    // Single delete is also async: poll with page reloads until the row is gone.
    await expect.poll(
      async () => {
        await page.goto(DEPLOYMENTS_URL)
        await page.locator('.dataTables_wrapper:has(#deployments)').waitFor({ state: 'visible', timeout: 10000 })
        await page.locator('#deployments tbody tr').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
        return page.locator(`#deployments tbody tr[id="${dep.id}"]`).isVisible()
      },
      { timeout: 20000, intervals: [2000, 3000, 5000] },
    ).toBe(false)

    const remaining = await listAllDeployments(apiv4Admin)
    expect(remaining.find((d) => d.id === dep.id)).toBeUndefined()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S5 — admin bulk-deletes deployments permanently
  // ──────────────────────────────────────────────────────────────────────────
  test('S5: bulk-deletes two deployments permanently', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const dep1 = await createDeploymentViaApi(apiv4Admin, testInfo, sharedTemplateId, uniqueDeploymentName(testInfo, 's5a'))
    const dep2 = await createDeploymentViaApi(apiv4Admin, testInfo, sharedTemplateId, uniqueDeploymentName(testInfo, 's5b'))

    await findBothRows(page, dep1.id, dep2.id)
    const row1 = page.locator(`#deployments tbody tr[id="${dep1.id}"]`)
    const row2 = page.locator(`#deployments tbody tr[id="${dep2.id}"]`)

    await row1.locator('.select-checkbox input[type="checkbox"]').check()
    await row2.locator('.select-checkbox input[type="checkbox"]').check()

    const deleteResponse = page.waitForResponse(
      (r) => r.url().includes('/api/v4/items/deployments') && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await page.locator('.btn-bulkdelete').click()
    await page.locator('.ui-pnotify-action-button', { hasText: /delete permanently/i }).click()

    const resp = await deleteResponse
    expect(resp.status()).toBeLessThan(400)

    const reqBody = JSON.parse(resp.request().postData() || '{}')
    expect(reqBody.permanent).toBe(true)
    expect(reqBody.ids).toContain(dep1.id)
    expect(reqBody.ids).toContain(dep2.id)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /deletion queued/i }),
    ).toBeVisible({ timeout: 5000 })

    // Bulk delete is async (202 Accepted): backend queues deletion and the
    // frontend reloads the table immediately — rows may still be visible right
    // after the response. Poll with page reloads until both rows are gone.
    await expect.poll(
      async () => {
        await page.goto(DEPLOYMENTS_URL)
        await page.locator('.dataTables_wrapper:has(#deployments)').waitFor({ state: 'visible', timeout: 10000 })
        await page.locator('#deployments tbody tr').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
        return (
          (await page.locator(`#deployments tbody tr[id="${dep1.id}"]`).isVisible()) ||
          (await page.locator(`#deployments tbody tr[id="${dep2.id}"]`).isVisible())
        )
      },
      { timeout: 20000, intervals: [2000, 3000, 5000] },
    ).toBe(false)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S6 — admin bulk-deletes deployments to recycle bin
  // ──────────────────────────────────────────────────────────────────────────
  test('S6: bulk-deletes two deployments to recycle bin', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const dep1 = await createDeploymentViaApi(apiv4Admin, testInfo, sharedTemplateId, uniqueDeploymentName(testInfo, 's6a'))
    const dep2 = await createDeploymentViaApi(apiv4Admin, testInfo, sharedTemplateId, uniqueDeploymentName(testInfo, 's6b'))

    await findBothRows(page, dep1.id, dep2.id)
    const row1 = page.locator(`#deployments tbody tr[id="${dep1.id}"]`)
    const row2 = page.locator(`#deployments tbody tr[id="${dep2.id}"]`)

    await row1.locator('.select-checkbox input[type="checkbox"]').check()
    await row2.locator('.select-checkbox input[type="checkbox"]').check()

    const deleteResponse = page.waitForResponse(
      (r) => r.url().includes('/api/v4/items/deployments') && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await page.locator('.btn-bulkdelete').click()
    await page.locator('.ui-pnotify-action-button', { hasText: /recycle bin/i }).click()

    const resp = await deleteResponse
    expect(resp.status()).toBeLessThan(400)

    const reqBody = JSON.parse(resp.request().postData() || '{}')
    expect(reqBody.permanent).toBe(false)
    expect(reqBody.ids).toContain(dep1.id)
    expect(reqBody.ids).toContain(dep2.id)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /deletion queued/i }),
    ).toBeVisible({ timeout: 5000 })

    await expect.poll(
      async () => {
        await page.goto(DEPLOYMENTS_URL)
        await page.locator('.dataTables_wrapper:has(#deployments)').waitFor({ state: 'visible', timeout: 10000 })
        await page.locator('#deployments tbody tr').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
        return (
          (await page.locator(`#deployments tbody tr[id="${dep1.id}"]`).isVisible()) ||
          (await page.locator(`#deployments tbody tr[id="${dep2.id}"]`).isVisible())
        )
      },
      { timeout: 20000, intervals: [2000, 3000, 5000] },
    ).toBe(false)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S7 — admin clicks Bulk Delete with no rows selected
  // ──────────────────────────────────────────────────────────────────────────
  test('S7: Bulk Delete with no selection shows a warning and fires no API call', async ({
    authenticatedPage: page,
  }) => {
    await gotoDeployments(page)

    let deleteFired = false
    page.on('request', (req) => {
      if (req.url().includes('/api/v4/items/deployments') && req.method() === 'DELETE') {
        deleteFired = true
      }
    })
    
    await page.locator('.btn-bulkdelete').click()

    await expect(
      page.locator('.ui-pnotify-text', { hasText: /select the deployments/i }),
    ).toBeVisible({ timeout: 5000 })
    expect(deleteFired, 'DELETE must not fire with no selection').toBeFalsy()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S8 — admin changes the owner of a deployment
  // ──────────────────────────────────────────────────────────────────────────
  test('S8: changes the owner of a deployment via the Change owner modal', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    // Resolve manager_e2e_01 user ID before navigating the page.
    const searchResults = await unwrap(
      adminSearchUsers({ client: apiv4Admin, body: { term: 'E2E Manager 01' } }),
    ).catch(() => [])
    const manager = Array.isArray(searchResults)
      ? searchResults.find((u) => u.uid === 'manager_e2e_01')
      : null
    test.skip(!manager, 'manager_e2e_01 not found via admin user search')

    const name = uniqueDeploymentName(testInfo, 's8')
    const dep = await createDeploymentViaApi(apiv4Admin, testInfo, sharedTemplateId, name)

    await findDeploymentRow(page, dep.id)
    const detailPanel = await expandDeploymentRow(page, dep.id)
    await detailPanel.locator('.btn-owner').click()

    const modal = page.locator('#modalChangeOwnerDomain')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Select2: open the dropdown and type the search term.
    await modal.locator('.select2-selection').click()
    await page.locator('.select2-search__field').last().fill('E2E Manager 01')
    const resultItem = page
      .locator('.select2-results__option', { hasText: /E2E Manager 01/i })
      .first()
    await resultItem.waitFor({ state: 'visible', timeout: 10000 })
    await resultItem.click()

    const putResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/deployment/${dep.id}/change-owner/`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await putResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /owner changed/i }),
    ).toBeVisible({ timeout: 5000 })

    // Verify the table row reflects the new owner.
    // The table refreshes asynchronously, so poll with page reloads.
    await expect.poll(
      async () => {
        await page.goto(DEPLOYMENTS_URL)
        await page.locator('.dataTables_wrapper:has(#deployments)').waitFor({ state: 'visible', timeout: 10000 })
        await page.locator('#deployments tbody tr').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
        const text = await page.locator(`#deployments tbody tr[id="${dep.id}"]`).textContent().catch(() => '')
        return text.includes('E2E Manager 01')
      },
      { timeout: 20000, intervals: [2000, 3000, 5000] },
    ).toBe(true)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S9 — admin changes the co-owners of a deployment
  // ──────────────────────────────────────────────────────────────────────────
  test('S9: changes the co-owners of a deployment via the Change co-owners modal', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const searchResults = await unwrap(
      adminSearchUsers({ client: apiv4Admin, body: { term: 'E2E Manager 01' } }),
    ).catch(() => [])
    const manager = Array.isArray(searchResults)
      ? searchResults.find((u) => u.uid === 'manager_e2e_01')
      : null
    test.skip(!manager, 'manager_e2e_01 not found via admin user search')

    const name = uniqueDeploymentName(testInfo, 's9')
    const dep = await createDeploymentViaApi(apiv4Admin, testInfo, sharedTemplateId, name)

    await findDeploymentRow(page, dep.id)
    const detailPanel = await expandDeploymentRow(page, dep.id)

    // Register the co-owners GET listener before the click that triggers it.
    const coOwnersGetResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/deployment/${dep.id}/co-owners`) &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await detailPanel.locator('.btn-co-owners').click()

    const modal = page.locator('#modalChangeCoOwnersDeployment')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await coOwnersGetResponse

    // Add manager_e2e_01 as co-owner.
    await modal.locator('.select2-selection').click()
    await page.locator('.select2-search__field').last().fill('E2E Manager 01')
    const resultItem = page
      .locator('.select2-results__option', { hasText: /E2E Manager 01/i })
      .first()
    await resultItem.waitFor({ state: 'visible', timeout: 10000 })
    await resultItem.click()

    const putResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/deployment/${dep.id}/co-owners`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await putResponse
    expect(resp.status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Verify the table row reflects the new co-owner.
    // The table refreshes asynchronously, so poll with page reloads.
    await expect.poll(
      async () => {
        await page.goto(DEPLOYMENTS_URL)
        await page.locator('.dataTables_wrapper:has(#deployments)').waitFor({ state: 'visible', timeout: 10000 })
        await page.locator('#deployments tbody tr').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
        const text = await page.locator(`#deployments tbody tr[id="${dep.id}"]`).textContent().catch(() => '')
        return text.includes('E2E Manager 01')
      },
      { timeout: 20000, intervals: [2000, 3000, 5000] },
    ).toBe(true)

    // Persist check via the API.
    const coOwners = await unwrap(
      getDeploymentCoOwners({ client: apiv4Admin, path: { deployment_id: dep.id } }),
    )
    expect(
      coOwners.co_owners.some((u) => u.id === manager.id),
      'manager_e2e_01 should appear in co_owners after save',
    ).toBeTruthy()
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S10 — admin removes all co-owners from a deployment
  // ──────────────────────────────────────────────────────────────────────────
  test('S10: removes all co-owners from a deployment', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const searchResults = await unwrap(
      adminSearchUsers({ client: apiv4Admin, body: { term: 'E2E Manager 01' } }),
    ).catch(() => [])
    const manager = Array.isArray(searchResults)
      ? searchResults.find((u) => u.uid === 'manager_e2e_01')
      : null
    test.skip(!manager, 'manager_e2e_01 not found via admin user search')

    const name = uniqueDeploymentName(testInfo, 's10')
    const dep = await createDeploymentViaApi(apiv4Admin, testInfo, sharedTemplateId, name)

    // Pre-set a co-owner via API so the modal has something to remove.
    await unwrap(
      updateDeploymentCoOwners({
        client: apiv4Admin,
        path: { deployment_id: dep.id },
        body: { co_owners: [manager.id] },
      }),
    )

    await findDeploymentRow(page, dep.id)
    const detailPanel = await expandDeploymentRow(page, dep.id)

    // Register the co-owners GET listener before the click that triggers it.
    const coOwnersGetResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/deployment/${dep.id}/co-owners`) &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await detailPanel.locator('.btn-co-owners').click()

    const modal = page.locator('#modalChangeCoOwnersDeployment')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await coOwnersGetResponse

    // Remove all selected co-owner tags by clicking each × button.
    const removeButtons = modal.locator('.select2-selection__choice__remove')
    const total = await removeButtons.count()
    for (let i = 0; i < total; i++) {
      await modal.locator('.select2-selection__choice__remove').first().click()
    }

    const putResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/deployment/${dep.id}/co-owners`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await putResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Verify the table row no longer shows the removed co-owner.
    // The table refreshes asynchronously, so poll with page reloads.
    await expect.poll(
      async () => {
        await page.goto(DEPLOYMENTS_URL)
        await page.locator('.dataTables_wrapper:has(#deployments)').waitFor({ state: 'visible', timeout: 10000 })
        await page.locator('#deployments tbody tr').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
        const text = await page.locator(`#deployments tbody tr[id="${dep.id}"]`).textContent().catch(() => '')
        return text.includes('E2E Manager 01')
      },
      { timeout: 20000, intervals: [2000, 3000, 5000] },
    ).toBe(false)

    // Persist check: co_owners should be empty.
    const coOwners = await unwrap(
      getDeploymentCoOwners({ client: apiv4Admin, path: { deployment_id: dep.id } }),
    )
    expect(coOwners.co_owners, 'co_owners should be empty after removal').toHaveLength(0)
  })

})
