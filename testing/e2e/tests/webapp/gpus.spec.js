// Drives the GPU admin flows on /isard-admin/admin/hypervisors and the
// Bookables admin page. Mirrors testing/e2e/specs/webapp/gpus.md — each
// `test(...)` corresponds to a numbered scenario in that spec.
//
// Conventions:
//   - GPU names go through `testInfo.annotations` (type "gpu-name") so
//     the afterEach can reach them even if the test failed mid-flow.
//     Multiple annotations are supported by tests that create more than
//     one GPU (e.g. the Bookables cross-check).
//   - Scenarios that need a desktop+plan+booking+deployment all tied to
//     the SAME GPU (4, 12) are still skipped — the seed only ships the
//     desktops half of that fixture. S7 covers the disable-with-deps
//     branch using the seeded GPU A16 + NVIDIA-A16-4Q pair and exits via
//     Cancel so parallel workers don't race on the shared profile state.
//   - Scenarios that depend on a real GPU profile being available skip
//     gracefully when the dev DB has none, so the file is safe to run
//     against a hypervisor-less environment.

import { test, expect } from '../../fixtures/login.js'

// Matches the Parsley pattern on #modalAddGpu #name and stays under
// the 50-char ceiling.
const VALID_NAME_RE = /^[\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$/

async function listGpus(page) {
  const resp = await page.request.get('/api/v4/items/reservables/gpus')
  if (!resp.ok()) return []
  const body = await resp.json().catch(() => null)
  return body?.items ?? []
}

async function findGpuByName(page, name) {
  const items = await listGpus(page)
  return items.find((g) => g.name === name) || null
}

async function listAvailableProfiles(page) {
  const resp = await page.request.get('/api/v4/items/reservables/profiles/gpus')
  if (!resp.ok()) return []
  // The endpoint is rendered into a DataTable as `dataSrc: ""`, so the
  // response is the raw array.
  return (await resp.json().catch(() => [])) || []
}

async function getGpuProfiles(page, gpuId) {
  const resp = await page.request.get(`/api/v4/items/reservables/gpus/${gpuId}`)
  if (!resp.ok()) return []
  return (await resp.json().catch(() => [])) || []
}

async function createGpuViaApi(page, { name, description, bookable }) {
  const resp = await page.request.post('/api/v4/item/reservable/gpus', {
    data: { name, description, reservable_type: 'gpus', bookable },
  })
  if (!resp.ok()) {
    throw new Error(
      `createGpuViaApi failed: ${resp.status()} ${await resp.text().catch(() => '')}`,
    )
  }
  // apiv4 returns SimpleResponse(id=<new_gpu_id>) — use it directly.
  const body = await resp.json().catch(() => ({}))
  if (!body?.id) {
    throw new Error(
      `createGpuViaApi: POST response missing 'id' for "${name}": ${JSON.stringify(body)}`,
    )
  }
  return { id: body.id, name, description }
}

async function deleteGpuViaApi(page, gpuId, notifyUser = false) {
  const url = `/api/v4/item/reservable/gpus/${gpuId}` + (notifyUser ? '?notify_user=true' : '')
  await page.request.delete(url).catch(() => {})
}

async function setProfileEnabledViaApi(page, gpuId, profileId, enabled) {
  const resp = await page.request.put(
    `/api/v4/item/reservable/enable/gpus/${gpuId}/${profileId}`,
    { data: { enabled } },
  )
  const body = await resp.text().catch(() => '')
  if (!resp.ok()) {
    throw new Error(`enable ${gpuId}/${profileId}=${enabled} failed: ${resp.status()} ${body}`)
  }
  console.log(`[enable] ${gpuId}/${profileId}=${enabled} → ${resp.status()} ${body}`)
}

async function trackGpuName(testInfo, name) {
  testInfo.annotations.push({ type: 'gpu-name', description: name })
}

function uniqueGpuName(testInfo, suffix = '') {
  // Names must match the Parsley pattern (no `:` or `@`); keep it boring.
  return `e2e-gpu-${testInfo.workerIndex}-${Date.now()}${suffix ? `-${suffix}` : ''}`
}

async function gotoHypervisors(page) {
  await page.goto('/isard-admin/admin/hypervisors')
  await page
    .locator('#table-gpus ~ .dataTables_wrapper, .dataTables_wrapper:has(#table-gpus)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  // Wait for a real data row (not the loading placeholder) so the
  // page.len(-1) below doesn't fire on an empty table.
  await page
    .locator('#table-gpus tbody tr:not(.dataTables_empty)')
    .first()
    .waitFor({ state: 'visible', timeout: 20000 })
  // Collapse pagination so id-based row lookups can't miss rows beyond
  // page 1 — DataTables uses deferRender, so off-page rows aren't in DOM.
  await page.evaluate(() => {
    // eslint-disable-next-line no-undef
    const t = $('#table-gpus').DataTable()
    if (t && t.page && typeof t.page.len === 'function') {
      t.page.len(-1).draw(false)
    }
  })
}

// Retries the navigate-and-locate cycle to absorb the occasional race
// between an API insert commit and the table's next GET.
async function findGpuRowAfterNavigation(page, gpuId, maxAttempts = 3) {
  let lastError
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    await gotoHypervisors(page)
    const row = page.locator(`#table-gpus tbody tr[id="${gpuId}"]`)
    try {
      await expect(row).toBeVisible({ timeout: 8000 })
      return row
    } catch (err) {
      lastError = err
    }
  }
  throw lastError
}

// Waits for the POST /admin/table/gpus that GpuEnabledProfilesDropdown
// fires when the force-profile modal opens.
function waitForGpuAdminTableLookup(page) {
  return page.waitForResponse(
    (r) =>
      r.url().includes('/api/v4/admin/table/gpus') &&
      r.request().method() === 'POST',
    { timeout: 15000 },
  )
}

async function expandGpuRow(page, gpuId) {
  // The expand toggle lives in the first cell of the GPU's row.
  const toggle = page.locator(`#table-gpus tbody tr[id="${gpuId}"] td.details-control button`).first()
  await toggle.scrollIntoViewIfNeeded()
  await toggle.click()
  // Child DataTable id pattern: cl<gpu_id>.
  const childTable = page.locator(`[id="cl${gpuId}"]`)
  await childTable.waitFor({ state: 'visible', timeout: 10000 })
  await childTable
    .locator('tbody tr:not(.dataTables_empty)')
    .first()
    .waitFor({ state: 'visible', timeout: 10000 })
  return childTable
}

async function clickPnotifyOk(page) {
  // PNotify renders confirm buttons inside .ui-pnotify-action-bar with
  // class .ui-pnotify-action-button. The first one ("Ok") is what we
  // need to confirm a delete prompt.
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^ok$/i })
    .first()
    .click({ timeout: 5000 })
}

test.describe('Admin GPUs — webapp', () => {
  // Drop this worker's own e2e-gpu-<workerIndex>-* leftovers from
  // aborted previous runs. Scoped to ``workerIndex`` so a worker's
  // beforeAll never deletes a peer worker's in-flight test GPU
  // (different worker processes start at slightly different times).
  test.beforeAll(async ({ authenticatedContext }, workerInfo) => {
    const page = await authenticatedContext.newPage()
    try {
      const prefix = `e2e-gpu-${workerInfo.workerIndex}-`
      const stale = (await listGpus(page)).filter(
        (g) => typeof g.name === 'string' && g.name.startsWith(prefix),
      )
      for (const gpu of stale) {
        await deleteGpuViaApi(page, gpu.id)
      }
    } finally {
      await page.close()
    }
  })

  test.afterEach(async ({ authenticatedPage: page }, testInfo) => {
    const names = testInfo.annotations
      .filter((a) => a.type === 'gpu-name')
      .map((a) => a.description)
    for (const name of names) {
      const gpu = await findGpuByName(page, name).catch(() => null)
      if (gpu) await deleteGpuViaApi(page, gpu.id)
    }
  })

  // ---------------------------------------------------------------------
  // Scenario 1 — admin creates a GPU and sees it listed
  // ---------------------------------------------------------------------
  test('S1: creates a GPU and lists it in #table-gpus', async ({ authenticatedPage: page }, testInfo) => {
    const gpuName = uniqueGpuName(testInfo)
    const gpuDescription = `e2e GPU created at ${new Date().toISOString()}`
    expect(gpuName).toMatch(VALID_NAME_RE)
    await trackGpuName(testInfo, gpuName)

    await gotoHypervisors(page)

    await page.locator('.btn-new-gpu[data-panel="gpus"]').first().click()
    const modal = page.locator('#modalAddGpu')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#name').fill(gpuName)
    await modal.locator('#description').fill(gpuDescription)

    const profileRow = page.locator('#modal_add_gpu tbody tr:not(.dataTables_empty)').first()
    await profileRow.waitFor({ state: 'visible', timeout: 15000 })
    await profileRow.click()
    await expect(modal.locator('#bookable')).not.toHaveValue('')

    const createResponse = page.waitForResponse(
      (r) => r.url().includes('/api/v4/item/reservable/gpus') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const createResp = await createResponse
    expect(createResp.status()).toBeLessThan(400)
    // apiv4 returns SimpleResponse(id=<new_gpu_id>); the webapp drops the
    // body but downstream automation can use it to skip the lookup-by-name.
    const createBody = await createResp.json().catch(() => ({}))
    expect(createBody?.id, 'POST should return SimpleResponse with new id').toBeTruthy()
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    const newRow = page.locator(`#table-gpus tbody tr:has-text("${gpuName}")`).first()
    await expect(newRow).toBeVisible({ timeout: 10000 })
    await expect(newRow).toContainText(gpuDescription)

    const apiGpu = await findGpuByName(page, gpuName)
    expect(apiGpu, 'GPU not returned by /api/v4/items/reservables/gpus').not.toBeNull()
    expect(apiGpu.id).toBe(createBody.id)
    expect(apiGpu.description).toBe(gpuDescription)
  })

  // ---------------------------------------------------------------------
  // Scenario 2 — admin edits name and description
  // ---------------------------------------------------------------------
  test('S2: edits name and description via the pencil icon', async ({ authenticatedPage: page }, testInfo) => {
    const profiles = await listAvailableProfiles(page)
    test.skip(profiles.length === 0, 'no GPU profiles available in the dev DB')

    const original = uniqueGpuName(testInfo)
    const edited = `${original}-edited`
    await trackGpuName(testInfo, edited)
    // Track the original too — if the PUT fails mid-flow we still want
    // the row gone after the test.
    await trackGpuName(testInfo, original)
    const gpu = await createGpuViaApi(page, {
      name: original,
      description: 'pre-edit description',
      bookable: profiles[0].id,
    })

    const row = await findGpuRowAfterNavigation(page, gpu.id)
    await row.locator('button#btn-edit').click()

    const modal = page.locator('#modalEditGpu')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#name')).toHaveValue(original)
    await expect(modal.locator('#description')).toHaveValue('pre-edit description')

    await modal.locator('#name').fill(edited)
    await modal.locator('#description').fill('post-edit description')

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/reservables/gpus/${gpu.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const editResp = await editResponse
    expect(editResp.status()).toBeLessThan(400)
    // apiv4 returns SimpleResponse(id=<item_id>) on edit.
    const editBody = await editResp.json().catch(() => ({}))
    expect(editBody?.id, 'PUT should echo the edited GPU id').toBe(gpu.id)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(row).toContainText(edited, { timeout: 10000 })
    await expect(row).toContainText('post-edit description')

    const fresh = await findGpuByName(page, edited)
    expect(fresh, 'edited GPU not returned by API').not.toBeNull()
    expect(fresh.description).toBe('post-edit description')
  })

  // ---------------------------------------------------------------------
  // Scenario 3 — admin deletes a GPU without dependencies
  // ---------------------------------------------------------------------
  test('S3: deletes a dependency-free GPU through the trash icon', async ({ authenticatedPage: page }, testInfo) => {
    const profiles = await listAvailableProfiles(page)
    test.skip(profiles.length === 0, 'no GPU profiles available in the dev DB')

    const name = uniqueGpuName(testInfo)
    await trackGpuName(testInfo, name) // afterEach cleans up if delete fails
    const gpu = await createGpuViaApi(page, {
      name,
      description: 'to be deleted',
      bookable: profiles[0].id,
    })

    const row = await findGpuRowAfterNavigation(page, gpu.id)
    await row.locator('button#btn-delete').click()

    // PNotify confirm — must say "Ok" before the DELETE fires.
    const checkLast = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/reservable/check-last/gpus/${gpu.id}`) &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/reservable/gpus/${gpu.id}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await checkLast).status()).toBeLessThan(400)
    expect((await deleteResponse).status()).toBeLessThan(400)

    // Without dependencies the secondary modal must NOT show.
    await expect(page.locator('#modalDeleteGPU')).toBeHidden({ timeout: 5000 })
    await expect(row).toBeHidden({ timeout: 10000 })

    expect(await findGpuByName(page, name)).toBeNull()
  })

  // ---------------------------------------------------------------------
  // Scenario 4 — admin deletes a GPU with dependencies and notifies users
  // ---------------------------------------------------------------------
  //TODO: Implement the full delete-with-deps flow and unskip this test.
  test.skip('S4: deletes a GPU with dependencies and notifies affected users', async () => {
    // Requires a GPU with at least one desktop / plan / booking /
    // deployment attached. The e2e environment doesn't ship that
    // fixture and synthesising it requires booking + deployment APIs
    // outside the scope of this spec.
  })

  // ---------------------------------------------------------------------
  // Scenario 5 — admin enables a profile of a GPU
  // ---------------------------------------------------------------------
  test('S5: enabling a profile checkbox toggles profiles_enabled', async ({ authenticatedPage: page }, testInfo) => {
    const profiles = await listAvailableProfiles(page)
    test.skip(profiles.length === 0, 'no GPU profiles available in the dev DB')

    const name = uniqueGpuName(testInfo, 's5')
    await trackGpuName(testInfo, name)
    const gpu = await createGpuViaApi(page, {
      name,
      description: 's5',
      bookable: profiles[0].id,
    })

    const initialProfile = (await getGpuProfiles(page, gpu.id))[0]
    test.skip(!initialProfile, 'no profiles returned for the freshly-created GPU')

    await findGpuRowAfterNavigation(page, gpu.id)
    const child = await expandGpuRow(page, gpu.id)
    const row = child.locator(`tbody tr[data-subitemid="${initialProfile.id}"]`)
    const checkbox = row.locator('input#chk-enabled')
    await expect(checkbox).not.toBeChecked()

    const enableResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/reservable/enable/gpus/${gpu.id}/${initialProfile.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await checkbox.click()
    const enableResp = await enableResponse
    expect(enableResp.status()).toBeLessThan(400)
    // apiv4 returns SimpleResponse(id=<gpu_id>) on enable/disable.
    const enableBody = await enableResp.json().catch(() => ({}))
    expect(enableBody?.id, 'PUT enable should echo the GPU id').toBe(gpu.id)

    // Persistence check via the admin table endpoint that the JS uses
    // to populate the forced-profile dropdown.
    const persisted = await page.request.post('/api/v4/admin/table/gpus', {
      data: { id: gpu.id },
    })
    expect(persisted.ok()).toBeTruthy()
    const body = await persisted.json()
    expect(body.profiles_enabled).toContain(initialProfile.id)
  })

  // ---------------------------------------------------------------------
  // Scenario 6 — admin disables a profile of a GPU without dependencies
  // ---------------------------------------------------------------------
  test('S6: disabling a profile without dependencies skips the deps modal', async ({
    authenticatedPage: page,
  }, testInfo) => {
    const profiles = await listAvailableProfiles(page)
    test.skip(profiles.length === 0, 'no GPU profiles available in the dev DB')

    const name = uniqueGpuName(testInfo, 's6')
    await trackGpuName(testInfo, name)
    const gpu = await createGpuViaApi(page, {
      name,
      description: 's6',
      bookable: profiles[0].id,
    })
    const initialProfile = (await getGpuProfiles(page, gpu.id))[0]
    test.skip(!initialProfile, 'no profiles returned for the freshly-created GPU')
    // Newly-created GPUs start with profiles_enabled=[]; enable one via API
    // so the UI starts in the "checked" state we want to drive into "off".
    await setProfileEnabledViaApi(page, gpu.id, initialProfile.id, true)

    await findGpuRowAfterNavigation(page, gpu.id)
    const child = await expandGpuRow(page, gpu.id)
    const row = child.locator(`tbody tr[data-subitemid="${initialProfile.id}"]`)
    const checkbox = row.locator('input#chk-enabled')
    await expect(checkbox).toBeChecked()

    const checkLast = page.waitForResponse(
      (r) =>
        r
          .url()
          .includes(
            `/api/v4/item/reservable/check-last/gpus/${initialProfile.id}/${gpu.id}`,
          ) && r.request().method() === 'GET',
      { timeout: 15000 },
    )
    const disableResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/reservable/enable/gpus/${gpu.id}/${initialProfile.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await checkbox.click()
    expect((await checkLast).status()).toBeLessThan(400)
    expect((await disableResponse).status()).toBeLessThan(400)

    await expect(page.locator('#modalDeleteGPU')).toBeHidden({ timeout: 5000 })

    const persisted = await page.request.post('/api/v4/admin/table/gpus', {
      data: { id: gpu.id },
    })
    const body = await persisted.json()
    expect(body.profiles_enabled).not.toContain(initialProfile.id)
  })

  // ---------------------------------------------------------------------
  // Scenario 7 — admin disables a profile with dependencies and notifies
  // ---------------------------------------------------------------------
  test('S7: disabling a profile with dependencies opens the notify modal', async ({
    authenticatedPage: page,
  }, testInfo) => {
    // Driven against the seeded (GPU A16, NVIDIA-A16-4Q) pair:
    //   - gpus.json: e2e8b73f-… has NVIDIA-A16-4Q enabled
    //   - domains.json: desktops reference NVIDIA-A16-4Q
    //   - no other seeded GPU enables NVIDIA-A16-4Q → ``last=[true]``
    // Uses the Cancel path so parallel workers don't race on the shared
    // ``gpus.profiles_enabled`` state. The actual disable + notify-user
    // fan-out is covered by apiv4 unit tests.
    const SEED_GPU_ID = 'e2e8b73f-b989-47b4-9864-9e0da97f7b21'
    const SEED_PROFILE_ID = 'NVIDIA-A16-4Q'

    const gpu = (await listGpus(page)).find((g) => g.id === SEED_GPU_ID)
    expect(gpu, `seeded GPU ${SEED_GPU_ID} not found`).toBeTruthy()
    expect(gpu.profiles_enabled).toContain(SEED_PROFILE_ID)

    let putFired = false
    page.on('request', (req) => {
      if (
        req.url().includes(`/api/v4/item/reservable/enable/gpus/${SEED_GPU_ID}/${SEED_PROFILE_ID}`) &&
        req.method() === 'PUT'
      ) {
        putFired = true
      }
    })

    await gotoHypervisors(page)
    const child = await expandGpuRow(page, SEED_GPU_ID)
    const row = child.locator(`tbody tr[data-subitemid="${SEED_PROFILE_ID}"]`)
    const checkbox = row.locator('input#chk-enabled')
    await expect(checkbox).toBeChecked()

    const checkLast = page.waitForResponse(
      (r) =>
        r
          .url()
          .includes(
            `/api/v4/item/reservable/check-last/gpus/${SEED_PROFILE_ID}/${SEED_GPU_ID}`,
          ) && r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await checkbox.click()
    const checkLastResp = await checkLast
    expect(checkLastResp.status()).toBeLessThan(400)
    const body = await checkLastResp.json()
    expect(body.last, 'A16-4Q should be the last GPU enabling this profile')
      .toContain(true)
    expect(
      body.desktops.length,
      'seeded desktops referencing A16-4Q expected',
    ).toBeGreaterThan(0)

    const modal = page.locator('#modalDeleteGPU')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#title')).toHaveText(/Disable profile/i)
    await expect(modal.locator('#desktops_table tbody tr').first()).toBeVisible()
    await expect(modal.locator('#desktops_table tbody')).not.toContainText(/no items/i)

    // Cancel — verify the disable PUT never fires and the seeded state
    // is untouched.
    await modal.locator('#cancel').click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })
    await expect(checkbox).toBeChecked()
    expect(putFired, 'enable PUT must NOT fire when the modal is cancelled')
      .toBeFalsy()

    const after = (await listGpus(page)).find((g) => g.id === SEED_GPU_ID)
    expect(after.profiles_enabled).toContain(SEED_PROFILE_ID)
  })

  // ---------------------------------------------------------------------
  // Scenario 8 — admin forces the active profile
  // ---------------------------------------------------------------------
  test('S8a: force-profile button warns when no profiles are enabled', async ({
    authenticatedPage: page,
  }, testInfo) => {
    const profiles = await listAvailableProfiles(page)
    test.skip(profiles.length === 0, 'no GPU profiles available in the dev DB')

    const name = uniqueGpuName(testInfo, 's8a')
    await trackGpuName(testInfo, name)
    const gpu = await createGpuViaApi(page, {
      name,
      description: 's8a',
      bookable: profiles[0].id,
    })
    // Fresh navigation so the click-handler reads the just-created GPU
    // from gpus_table.row.data() instead of a stale in-memory snapshot.
    const row = await findGpuRowAfterNavigation(page, gpu.id)
    await row.locator('button#btn-force_active_profile').click()

    // The JS short-circuits with a PNotify warning instead of opening the modal.
    await expect(page.locator('.ui-pnotify-title', { hasText: /no profiles enabled/i }))
      .toBeVisible({ timeout: 5000 })
    await expect(page.locator('#modalForcedProfile')).toBeHidden({ timeout: 2000 })
  })

  test('S8b: forcing the same profile that is already active is rejected', async ({
    authenticatedPage: page,
  }, testInfo) => {
    // Driven against the seeded ``e2e-gpu-force-a40`` GPU (gpus.json +
    // vgpus.json) — that's the only fixture in the e2e DB with
    // ``physical_device`` + ``active_profile`` populated. Creating one
    // via API leaves both null, so this test must use the seed.
    const SEED_GPU_ID = 'e2e-gpu-force-a40'
    const SEED_ACTIVE_PROFILE_ID = 'NVIDIA-A40-2Q'
    const SEED_ACTIVE_PROFILE_TEXT = '2Q'

    const gpu = (await listGpus(page)).find((g) => g.id === SEED_GPU_ID)
    expect(gpu, `seeded GPU ${SEED_GPU_ID} not found`).toBeTruthy()
    expect(gpu.physical_device).toBeTruthy()
    expect(gpu.active_profile).toBe(SEED_ACTIVE_PROFILE_TEXT)

    await gotoHypervisors(page)
    const row = page.locator(`#table-gpus tbody tr[id="${SEED_GPU_ID}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    let engineCalled = false
    page.on('request', (req) => {
      if (req.url().includes('/engine/profile/gpu/')) engineCalled = true
    })

    // Listen for the dropdown lookup before the click that triggers it.
    const dropdownResponse = waitForGpuAdminTableLookup(page)
    await row.locator('button#btn-force_active_profile').click()
    const modal = page.locator('#modalForcedProfile')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await dropdownResponse

    const select = modal.locator('#forced_active_profile')
    await expect(select.locator(`option[value="${SEED_ACTIVE_PROFILE_ID}"]`))
      .toHaveCount(1, { timeout: 10000 })
    await select.selectOption(SEED_ACTIVE_PROFILE_ID)

    // The click-handler bails out with the "already the active profile"
    // PNotify and never calls /engine/profile/gpu.
    await modal.locator('#send').click()
    await expect(
      page.locator('.ui-pnotify-text', { hasText: /already the active profile/i }),
    ).toBeVisible({ timeout: 5000 })
    expect(engineCalled, 'engine endpoint must NOT be hit').toBeFalsy()
  })

  // ---------------------------------------------------------------------
  // Scenario 9 — invalid name validation (Parsley)
  // ---------------------------------------------------------------------
  test('S9: Parsley blocks creation when the name is invalid', async ({ authenticatedPage: page }, testInfo) => {
    const profiles = await listAvailableProfiles(page)
    test.skip(profiles.length === 0, 'no GPU profiles available in the dev DB')

    await gotoHypervisors(page)
    await page.locator('.btn-new-gpu[data-panel="gpus"]').first().click()
    const modal = page.locator('#modalAddGpu')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Pick a profile up front so the only thing wrong is the name.
    const profileRow = page.locator('#modal_add_gpu tbody tr:not(.dataTables_empty)').first()
    await profileRow.waitFor({ state: 'visible', timeout: 15000 })
    await profileRow.click()
    await expect(modal.locator('#bookable')).not.toHaveValue('')

    let postFired = false
    page.on('request', (req) => {
      if (
        req.url().includes('/api/v4/item/reservable/gpus') &&
        req.method() === 'POST'
      ) {
        postFired = true
      }
    })

    // The maxlength="50" attribute on the input clamps the typed value,
    // so we can't actually drive the "too long" branch through fill();
    // we cover the other three cases (too short, bad chars, empty).
    const reuseDescription = `e2e invalid-name probe ${Date.now()}`
    await modal.locator('#description').fill(reuseDescription)

    const cases = ['abc', 'gpu@1', 'my/gpu', '名字', '']
    for (const candidate of cases) {
      await modal.locator('#name').fill(candidate)
      await modal.locator('#send').click()
      // The form must stay open and Parsley must mark the name as invalid.
      await expect(modal).toBeVisible()
      await expect(modal.locator('#name')).toHaveClass(/parsley-error/)
    }
    expect(postFired, 'POST must not be fired with an invalid name').toBeFalsy()
    // Description should still be there from the first fill.
    await expect(modal.locator('#description')).toHaveValue(reuseDescription)
  })

  // ---------------------------------------------------------------------
  // Scenario 10 — Send pressed without selecting a profile
  // ---------------------------------------------------------------------
  test('S10: Send is blocked when no profile row is selected', async ({ authenticatedPage: page }, testInfo) => {
    await gotoHypervisors(page)
    await page.locator('.btn-new-gpu[data-panel="gpus"]').first().click()
    const modal = page.locator('#modalAddGpu')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    const candidateName = uniqueGpuName(testInfo, 's10')
    await trackGpuName(testInfo, candidateName) // safety net
    await modal.locator('#name').fill(candidateName)
    await modal.locator('#description').fill('s10 desc')
    // Make sure no profile row is selected.
    await expect(modal.locator('#bookable')).toHaveValue('')

    let postFired = false
    page.on('request', (req) => {
      if (
        req.url().includes('/api/v4/item/reservable/gpus') &&
        req.method() === 'POST'
      ) {
        postFired = true
      }
    })

    await modal.locator('#send').click()
    await expect(modal.locator('#datatables-error-status')).toContainText(
      /no bookable selected/i,
      { timeout: 5000 },
    )
    await expect(modal).toBeVisible()
    await expect(modal.locator('#name')).toHaveValue(candidateName)
    await expect(modal.locator('#description')).toHaveValue('s10 desc')
    expect(postFired, 'POST must not fire without a bookable').toBeFalsy()
  })

  // ---------------------------------------------------------------------
  // Scenario 11 — duplicate name
  // ---------------------------------------------------------------------
  test('S11: re-creating with an existing name returns 409', async ({ authenticatedPage: page }, testInfo) => {
    const profiles = await listAvailableProfiles(page)
    test.skip(profiles.length === 0, 'no GPU profiles available in the dev DB')

    const name = uniqueGpuName(testInfo, 's11')
    await trackGpuName(testInfo, name)
    await createGpuViaApi(page, {
      name,
      description: 'first',
      bookable: profiles[0].id,
    })

    await gotoHypervisors(page)
    await page.locator('.btn-new-gpu[data-panel="gpus"]').first().click()
    const modal = page.locator('#modalAddGpu')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('#name').fill(name)
    await modal.locator('#description').fill('duplicate attempt')
    const profileRow = page.locator('#modal_add_gpu tbody tr:not(.dataTables_empty)').first()
    await profileRow.waitFor({ state: 'visible', timeout: 15000 })
    await profileRow.click()

    const createResponse = page.waitForResponse(
      (r) => r.url().includes('/api/v4/item/reservable/gpus') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const status = (await createResponse).status()
    expect(status, 'duplicate-name POST should return 409').toBe(409)

    // The AJAX error handler should surface the API description in a
    // PNotify error toast and leave the modal open with the row count
    // unchanged.
    await expect(
      page.locator('.ui-pnotify-title', { hasText: /error creating gpu/i }),
    ).toBeVisible({ timeout: 5000 })
    await expect(
      page.locator('.ui-pnotify-text', { hasText: new RegExp(`already exists`, 'i') }),
    ).toBeVisible({ timeout: 5000 })
    await expect(modal).toBeVisible()

    const items = (await listGpus(page)).filter((g) => g.name === name)
    expect(items.length, 'only one GPU should exist with this name').toBe(1)
    await expect(
      page.locator(`#table-gpus tbody tr:has-text("${name}")`),
    ).toHaveCount(1)
  })

  // ---------------------------------------------------------------------
  // Scenario 12 — full delete-with-deps integration
  // ---------------------------------------------------------------------
  //TODO: Implement the full delete-with-deps flow and unskip this test.
  test.skip('S12: deletes a GPU with desktops/plans and verifies cleanup', async () => {
    // Extends S4. Same fixture blocker — needs seeded desktops + plans
    // + bookings + deployments tied to the GPU. Skipped until the e2e
    // harness can reach the booking/deployment APIs end-to-end.
  })

  // ---------------------------------------------------------------------
  // Scenario 13 — Bookables UI cross-check
  // ---------------------------------------------------------------------
  test('S13: enabling a profile from the GPU details surfaces it in Bookables', async ({
    authenticatedPage: page,
  }, testInfo) => {
    const catalog = await listAvailableProfiles(page)
    const allGpus = await listGpus(page)
    const enabledProfiles = new Set(
      allGpus.flatMap((g) => g.profiles_enabled ?? []),
    )
    // Pick a free (model, profile) keyed by workerIndex so parallel
    // workers never enable the same profile and race the precondition.
    const freeCandidates = []
    for (const m of catalog) {
      if (!Array.isArray(m.profiles)) continue
      for (const p of m.profiles) {
        if (!enabledProfiles.has(p.id)) {
          freeCandidates.push({ model: m, profile: p })
        }
      }
    }
    test.skip(
      freeCandidates.length === 0,
      'no GPU profile available without an existing reservables_vgpus row',
    )
    const pick = freeCandidates[testInfo.workerIndex % freeCandidates.length]
    const model = pick.model
    const subProfileId = pick.profile.id

    // The Bookables row id is generated server-side and equals the
    // sub-profile id.
    const reservableRow = page.locator(`#reservables_vgpus tbody tr[id="${subProfileId}"]`)

    const name = uniqueGpuName(testInfo, 's13')
    await trackGpuName(testInfo, name)
    const gpu = await createGpuViaApi(page, {
      name,
      description: 's13',
      bookable: model.id,
    })

    // Precondition: Bookables shows nothing for this profile yet.
    await page.goto('/isard-admin/admin/domains/render/Bookables')
    await page
      .locator('#reservables_vgpus ~ .dataTables_wrapper, .dataTables_wrapper:has(#reservables_vgpus)')
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })
    await expect(reservableRow).toHaveCount(0)

    // Drive the enable from the Hypervisors page: expand the row, click
    // the checkbox, wait for the PNotify success toast.
    await findGpuRowAfterNavigation(page, gpu.id)
    const child = await expandGpuRow(page, gpu.id)
    const checkbox = child.locator(
      `tbody tr[data-subitemid="${subProfileId}"] input#chk-enabled`,
    )
    await expect(checkbox).not.toBeChecked()

    const enableResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/reservable/enable/gpus/${gpu.id}/${subProfileId}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await checkbox.click()
    expect((await enableResp).status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /gpu profile enabled/i }),
    ).toBeVisible({ timeout: 5000 })

    const persisted = await page.request.post('/api/v4/admin/table/gpus', {
      data: { id: gpu.id },
    })
    expect(persisted.ok()).toBeTruthy()
    const body = await persisted.json()
    expect(body.profiles_enabled).toContain(subProfileId)

    // Now navigate to Bookables and verify the entry showed up.
    await page.goto('/isard-admin/admin/domains/render/Bookables')
    await page
      .locator('#reservables_vgpus ~ .dataTables_wrapper, .dataTables_wrapper:has(#reservables_vgpus)')
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })
    await expect(reservableRow).toBeVisible({ timeout: 10000 })
  })
})
