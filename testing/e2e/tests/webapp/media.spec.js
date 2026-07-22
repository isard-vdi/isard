// Drives the media admin flows on /isard-admin/admin/isard-admin/media.
// Mirrors testing/e2e/specs/webapp/media.md — each test(...) corresponds
// to a numbered scenario in that spec.
//
// Conventions:
//   - mode: serial — tests run in order so non-destructive C scenarios
//     all complete before C2 (delete) touches the seeded "Empty ISO"
//     fixture that the other C tests depend on.
//   - Media created by B7 is tracked via testInfo.annotations (type
//     "media-id") and deleted in afterEach; cleanup errors are silenced.
//   - Scenarios that need Downloaded ISO media skip when none exists.
//   - D scenarios skip when no non-Downloaded status has any media.
//   - B7 queries the IsardVDI repository catalogue (GET /api/v4/admin/items/downloads/media)
//     and skips when REPO_MEDIA_NAME is not found (e.g. CI without network or repo access).

import { test, expect, apiv4ClientForPage, unwrap } from '../../fixtures/apiv4/index.js'
import {
  adminDownloadsKind,
  adminMediaByStatus,
  adminMediaList,
  adminMediaStatus,
  createMedia,
  deleteMedia,
  getMedia,
} from '../../src/gen/apiv4/sdk.gen'

// ── API helpers ────────────────────────────────────────────────────────────

async function listDownloadedMedia(client) {
  const data = await unwrap(
    adminMediaByStatus({ client, path: { status: 'Downloaded' } }),
  ).catch(() => [])
  const all = Array.isArray(data) ? data : []
  // Exclude the C2 fixture so C6 and other C tests never accidentally check or
  // operate on it — preserving its Downloaded state for C2's delete flow.
  return all.filter((m) => m.id !== 'e2e-delete-target')
}

async function getStatuses(client) {
  const data = await unwrap(adminMediaStatus({ client })).catch(() => [])
  return Array.isArray(data) ? data : []
}

async function deleteMediaViaApi(client, mediaId) {
  await deleteMedia({ client, path: { media_id: mediaId } }).catch(() => {})
}

// Name of the media used in B7 to test a real download from the repository.
// When a small dedicated media (e.g. DSL Linux) is published in the IsardVDI
// repository, update this constant to its exact catalogue name.
const REPO_MEDIA_NAME = 'Virtio ISO drivers Windows 0.1.164'

// Fetches the download URL for REPO_MEDIA_NAME from the IsardVDI repository.
// The config fixture must have a valid resources.code.
// Returns null if the item is not found in the catalogue.
async function getRepoMediaUrl(client) {
  const items = await unwrap(
    adminDownloadsKind({ client, path: { kind: 'media' } }),
  ).catch(() => [])
  const item = Array.isArray(items)
    ? items.find((i) => i.name === REPO_MEDIA_NAME)
    : null
  return item?.['url-web'] ?? null
}

// Creates a media via API and polls until it reaches Downloaded status.
// Throws if the download fails or does not complete within timeoutMs.
async function createAndAwaitDownloaded(client, name, url, timeoutMs = 120000) {
  const { id } = await unwrap(
    createMedia({
      client,
      body: {
        name,
        url,
        kind: 'iso',
        description: 'e2e test media',
        allowed: { roles: false, categories: false, groups: false, users: false },
        hypervisors_pools: ['default'],
      },
    }),
  )
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 3000))
    const media = await unwrap(getMedia({ client, path: { media_id: id } })).catch(() => null)
    if (media?.status === 'Downloaded') return { id, ...media }
    if (media?.status?.startsWith('DownloadFailed')) {
      throw new Error(`Media download failed with status: ${media.status}`)
    }
  }
  throw new Error(`Media did not reach Downloaded state within ${timeoutMs}ms`)
}

function trackMediaId(testInfo, id) {
  testInfo.annotations.push({ type: 'media-id', description: id })
}

function uniqueMediaName(testInfo) {
  return `e2e-media-${testInfo.workerIndex}-${Date.now()}`
}

// ── Page helpers ────────────────────────────────────────────────────────────

// Navigate to the media admin page and wait for the static #status select
// to be visible (it is always present in the rendered Flask template, so
// its presence proves the admin page was served — not a login redirect).
async function gotoMedia(page) {
  await page.goto('/isard-admin/admin/isard-admin/media')
  await page.locator('#status').waitFor({ state: 'visible', timeout: 15000 })
}

// Waits until the #media DataTable has rendered at least one row (real row
// or the .dataTables_empty placeholder — both prove the AJAX completed).
async function waitForDownloadedTable(page) {
  await page
    .locator('#media tbody tr')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
    .catch(() => {})
}

async function clickPnotifyOk(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^ok$/i })
    .first()
    .click({ timeout: 5000 })
}

// Selects the first non-Downloaded status that has at least one media item,
// waits for #mediaOtherTable to load, and returns context. Returns null if
// no such status exists or the table stays empty.
async function loadOtherTable(page, client) {
  const statuses = await getStatuses(client)
  const candidate = statuses.find((s) => s.status !== 'Downloaded' && s.status !== 'deleted' && s.count > 0)
  if (!candidate) return null

  await gotoMedia(page)
  await expect(page.locator('#status')).not.toBeDisabled({ timeout: 15000 })

  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/items/media/${candidate.status}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    ),
    page.locator('#status').selectOption(candidate.status),
  ])

  const table = page.locator('#mediaOtherTable')
  await expect(table).toBeVisible({ timeout: 10000 })

  const firstRow = table.locator('tbody tr:not(.dataTables_empty)').first()
  const hasRow = await firstRow
    .waitFor({ state: 'visible', timeout: 10000 })
    .then(() => true)
    .catch(() => false)
  if (!hasRow) return null

  return { table, firstRow, status: candidate.status }
}

// ── Suite ──────────────────────────────────────────────────────────────────

test.describe('Admin Media — webapp', () => {
  test.describe.configure({ mode: 'serial' })

  // Remove stale e2e-media-<workerIndex>-* leftovers from aborted runs.
  // adminMediaList covers non-Downloaded statuses; adminMediaByStatus('Downloaded')
  // covers completed downloads. Both are needed because the two endpoints are separate.
  test.beforeAll(async ({ authenticatedContext }, workerInfo) => {
    const page = await authenticatedContext.newPage()
    try {
      const client = apiv4ClientForPage(page)
      const prefix = `e2e-media-${workerInfo.workerIndex}-`

      const [nonDl, dl] = await Promise.all([
        unwrap(adminMediaList({ client })).catch(() => []),
        unwrap(adminMediaByStatus({ client, path: { status: 'Downloaded' } })).catch(() => []),
      ])
      const all = [...(Array.isArray(nonDl) ? nonDl : []), ...(Array.isArray(dl) ? dl : [])]
      for (const m of all) {
        if (typeof m.name === 'string' && m.name.startsWith(prefix)) {
          await deleteMediaViaApi(client, m.id)
        }
      }
    } finally {
      await page.close()
    }
  })

  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    const ids = testInfo.annotations
      .filter((a) => a.type === 'media-id')
      .map((a) => a.description)
    for (const id of ids) {
      await deleteMediaViaApi(apiv4Admin, id)
    }
  })

  // ── SECTION A — Page load and status filtering ─────────────────────────

  test('A1: Downloaded media table loads on page visit', async ({ authenticatedPage: page }) => {
    // page.on('response') captures AJAX fired during navigation (DataTables
    // fires its XHR in $(document).ready before the load event). This is
    // more reliable than waitForResponse which can miss navigation-time XHR.
    let downloadedStatus = null
    page.on('response', (resp) => {
      if (
        resp.url().includes('/api/v4/admin/items/media/Downloaded') &&
        resp.request().method() === 'GET'
      ) {
        downloadedStatus = resp.status()
      }
    })

    await gotoMedia(page)
    // waitForDownloadedTable ensures DataTables rendered, proving the XHR completed.
    await waitForDownloadedTable(page)

    expect(downloadedStatus, 'GET /api/v4/admin/items/media/Downloaded was not called').not.toBeNull()
    expect(downloadedStatus).toBeLessThan(400)

    await expect(page.locator('table#media')).toBeVisible()
    await expect(page.locator('table#media thead tr').first()).toBeVisible()

    await expect(page.locator('#status')).toBeVisible()
  })

  test('A2: status dropdown populates with non-Downloaded statuses', async ({ authenticatedPage: page }) => {
    let statusHttpStatus = null
    page.on('response', (resp) => {
      if (
        resp.url().includes('/api/v4/admin/item/media/status') &&
        resp.request().method() === 'GET'
      ) {
        statusHttpStatus = resp.status()
      }
    })

    await gotoMedia(page)

    const statusDrop = page.locator('#status')
    // Wait for at least one non-placeholder option — proves the AJAX completed and JS rendered the options.
    await expect(statusDrop.locator('option:not([value="none"])').first()).toBeAttached({ timeout: 15000 })

    expect(statusHttpStatus, 'GET /api/v4/admin/item/media/status was not called').not.toBeNull()
    expect(statusHttpStatus).toBeLessThan(400)

    const count = await statusDrop.locator('option').count()
    expect(count, 'dropdown should have placeholder + at least one status').toBeGreaterThanOrEqual(2)

    const texts = await statusDrop.locator('option').allTextContents()
    expect(
      texts.some((t) => t.trim() === 'Downloaded'),
      '"Downloaded" must be filtered out of the dropdown',
    ).toBeFalsy()
  })

  test('A3: selecting a status in the dropdown loads #mediaOtherTable', async ({ authenticatedPage: page, apiv4Admin }) => {
    const statuses = await getStatuses(apiv4Admin)
    const nonDownloaded = statuses.filter((s) => s.status !== 'Downloaded')
    test.skip(nonDownloaded.length === 0, 'no non-Downloaded statuses returned by API')

    const pick = nonDownloaded[0].status
    await gotoMedia(page)
    await expect(page.locator('#status')).not.toBeDisabled({ timeout: 10000 })

    const [otherResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/api/v4/admin/items/media/${pick}`) &&
          r.request().method() === 'GET',
        { timeout: 15000 },
      ),
      page.locator('#status').selectOption(pick),
    ])
    expect(otherResp.status()).toBeLessThan(400)

    await expect(page.locator('#mediaOtherTable')).toBeVisible({ timeout: 10000 })
  })

  // ── SECTION B — Upload from URL ────────────────────────────────────────

  test('B1: "Upload from URL" button opens the add modal', async ({ authenticatedPage: page }) => {
    await gotoMedia(page)
    await page.locator('.btn-new').click()

    const modal = page.locator('#modalAddMedia')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await expect(modal.locator('#url')).toBeEmpty()
    await expect(modal.locator('#name')).toBeEmpty()
    await expect(modal.locator('#kind')).toHaveValue('')
    await expect(modal.locator('#send')).toBeVisible()
  })

  test('B2: Parsley blocks submission when URL uses http://', async ({ authenticatedPage: page }) => {
    await gotoMedia(page)
    await page.locator('.btn-new').click()
    const modal = page.locator('#modalAddMedia')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#name').fill('valid-name-b2')
    await modal.locator('#kind').selectOption('iso')
    await modal.locator('#url').fill('http://example.com/test.iso')

    let postFired = false
    page.on('request', (req) => {
      if (req.url().includes('/api/v4/item/media') && req.method() === 'POST') postFired = true
    })

    await modal.locator('#send').click()
    await expect(modal.locator('#url')).toHaveClass(/parsley-error/, { timeout: 5000 })
    await expect(modal).toBeVisible()
    expect(postFired, 'POST must not fire when URL uses http://').toBeFalsy()
  })

  test('B3: Name auto-fills with URL filename when the field is focused while empty', async ({ authenticatedPage: page }) => {
    // The media.js focus handler fills #name with the filename extracted from
    // the URL whenever #name is focused and empty while #url has a value.
    // This makes "empty name + non-empty URL" impossible in normal use, so we
    // test the auto-fill itself rather than a "empty name is blocked" scenario.
    await gotoMedia(page)
    await page.locator('.btn-new').click()
    const modal = page.locator('#modalAddMedia')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#url').fill('https://example.com/test.iso')
    // Focusing #name (while empty) should trigger the auto-fill.
    await modal.locator('#name').click()

    await expect(modal.locator('#name')).toHaveValue('test.iso')
  })

  test('B4: Parsley blocks submission when Name is shorter than 4 characters', async ({ authenticatedPage: page }) => {
    await gotoMedia(page)
    await page.locator('.btn-new').click()
    const modal = page.locator('#modalAddMedia')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Fill #name BEFORE #url so the auto-fill handler doesn't fire (#url is still empty).
    await modal.locator('#name').fill('abc')
    await modal.locator('#url').fill('https://example.com/test.iso')
    await modal.locator('#kind').selectOption('iso')

    let postFired = false
    page.on('request', (req) => {
      if (req.url().includes('/api/v4/item/media') && req.method() === 'POST') postFired = true
    })

    await modal.locator('#send').click()
    await expect(modal.locator('#name')).toHaveClass(/parsley-error/, { timeout: 5000 })
    await expect(modal).toBeVisible()
    expect(postFired, 'POST must not fire when name is too short').toBeFalsy()
  })

  test('B5: Parsley blocks submission when Name exceeds 60 characters', async ({ authenticatedPage: page }) => {
    await gotoMedia(page)
    await page.locator('.btn-new').click()
    const modal = page.locator('#modalAddMedia')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Fill #name BEFORE #url so the auto-fill handler doesn't fire (#url is still empty).
    await modal.locator('#name').fill('a'.repeat(61))
    await modal.locator('#url').fill('https://example.com/test.iso')
    await modal.locator('#kind').selectOption('iso')

    let postFired = false
    page.on('request', (req) => {
      if (req.url().includes('/api/v4/item/media') && req.method() === 'POST') postFired = true
    })

    await modal.locator('#send').click()
    await expect(modal.locator('#name')).toHaveClass(/parsley-error/, { timeout: 5000 })
    await expect(modal).toBeVisible()
    expect(postFired, 'POST must not fire when name is too long').toBeFalsy()
  })

  test('B6: Parsley blocks submission when Type is not selected', async ({ authenticatedPage: page }) => {
    await gotoMedia(page)
    await page.locator('.btn-new').click()
    const modal = page.locator('#modalAddMedia')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#url').fill('https://example.com/test.iso')
    await modal.locator('#name').fill('valid-name-b6')
    // leave #kind on "Choose.." (value="")

    let postFired = false
    page.on('request', (req) => {
      if (req.url().includes('/api/v4/item/media') && req.method() === 'POST') postFired = true
    })

    await modal.locator('#send').click()
    await expect(modal.locator('#kind')).toHaveClass(/parsley-error/, { timeout: 5000 })
    await expect(modal).toBeVisible()
    expect(postFired, 'POST must not fire when type is not selected').toBeFalsy()
  })

  test('B7: submitting a valid form fires POST and closes the modal', async ({ authenticatedPage: page, apiv4Admin }, testInfo) => {
    const testUrl = await getRepoMediaUrl(apiv4Admin)
    test.skip(!testUrl, `"${REPO_MEDIA_NAME}" not found in repository catalogue — skipping network-dependent upload test`)

    const mediaName = uniqueMediaName(testInfo)
    await gotoMedia(page)
    await page.locator('.btn-new').click()
    const modal = page.locator('#modalAddMedia')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#url').fill(testUrl)
    await modal.locator('#name').fill(mediaName)
    await modal.locator('#kind').selectOption('iso')

    const createResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/item/media') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await createResp
    expect(resp.status()).toBeLessThan(400)

    const body = await resp.json().catch(() => ({}))
    if (body?.id) trackMediaId(testInfo, body.id)

    await modal.waitFor({ state: 'hidden', timeout: 10000 })
    await expect(
      page.locator('.ui-pnotify-title', { hasText: /created/i }),
    ).toBeVisible({ timeout: 5000 })
  })

  // ── SECTION C — Downloaded media row actions ───────────────────────────
  // C2 placed last so all non-destructive C scenarios run first.

  test('C1: expanding a row shows the domains detail table', async ({ authenticatedPage: page, apiv4Admin }) => {
    const media = await listDownloadedMedia(apiv4Admin)
    test.skip(media.length === 0, 'no Downloaded media in the system')

    const first = media[0]
    await gotoMedia(page)
    await waitForDownloadedTable(page)

    const row = page.locator(`#media tbody tr[id="${first.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    const domainsResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/items/media/domains/${first.id}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await row.locator('button#btn-details').click()
    expect((await domainsResp).status()).toBeLessThan(400)

    const child = page.locator(`[id="cl${first.id}"]`)
    await expect(child).toBeVisible({ timeout: 10000 })

    await row.locator('button#btn-details').click()
    await expect(child).toBeHidden({ timeout: 5000 })
  })

  test('C3: "Create desktop from media" opens the creation modal pre-filled', async ({ authenticatedPage: page, apiv4Admin }) => {
    const media = await listDownloadedMedia(apiv4Admin)
    const iso = media.find((m) => m.kind && !m.kind.startsWith('qcow'))
    test.skip(!iso, 'no Downloaded ISO (non-qcow) media in the system')

    await gotoMedia(page)
    await waitForDownloadedTable(page)

    const row = page.locator(`#media tbody tr[id="${iso.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    const installsResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/items/media/installs') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await row.locator('button#btn-createfromiso').click()
    const modal = page.locator('#modalAddFromMedia')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await installsResp

    await expect(modal.locator('input#media[type="hidden"]')).toHaveValue(iso.id)
    await expect(modal.locator('#media_name')).toContainText(iso.name)
    await expect(modal.locator('#modal_add_install')).toBeVisible()
  })

  test('C4: Alloweds button opens the alloweds modal', async ({ authenticatedPage: page, apiv4Admin }) => {
    const media = await listDownloadedMedia(apiv4Admin)
    const iso = media.find((m) => m.kind && !m.kind.startsWith('qcow'))
    test.skip(!iso, 'no Downloaded ISO (non-qcow) media in the system')

    await gotoMedia(page)
    await waitForDownloadedTable(page)

    const row = page.locator(`#media tbody tr[id="${iso.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    // modalAllowedsFormShow opens #modalAlloweds synchronously and then fires
    // POST /api/v4/item/allowed/table/media to load the current alloweds. Waiting
    // for that response proves the handler ran and the modal is already open.
    const allowedsResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/item/allowed/table/media') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await row.locator('button#btn-alloweds').click()
    expect((await allowedsResp).status()).toBeLessThan(400)

    await expect(page.locator('#modalAlloweds')).toBeVisible({ timeout: 10000 })
  })

  test('C5: Change owner modal opens and Select2 search returns results', async ({ authenticatedPage: page, apiv4Admin }) => {
    const media = await listDownloadedMedia(apiv4Admin)
    const iso = media.find((m) => m.kind && !m.kind.startsWith('qcow'))
    test.skip(!iso, 'no Downloaded ISO (non-qcow) media in the system')

    await gotoMedia(page)
    await waitForDownloadedTable(page)

    const row = page.locator(`#media tbody tr[id="${iso.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-owner').click()

    const modal = page.locator('#modalChangeOwnerMedia')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Select2: open the dropdown, then type to trigger the AJAX lookup.
    await modal.locator('.select2-selection').click()
    const searchBox = page.locator('.select2-dropdown .select2-search__field')
    await searchBox.waitFor({ state: 'visible', timeout: 5000 })

    const allowedResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/items/alloweds/term/users') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    // 'ad' matches 'admin', which always exists since the test runs as admin.
    await searchBox.fill('ad')
    expect((await allowedResp).status()).toBeLessThan(400)

    // role="option" and aria-selected are only present on real selectable
    // results. Status messages ("Searching...", "No results found") use
    // role="alert" instead, so this filter correctly rejects them.
    await expect(
      page.locator('.select2-results__option[role="option"]').first(),
    ).toBeVisible({ timeout: 10000 })
  })

  test('C7: Show last task info fetches task and shows PNotify', async ({ authenticatedPage: page, apiv4Admin }) => {
    const media = await listDownloadedMedia(apiv4Admin)
    const isoWithTask = media.find(
      (m) =>
        m.kind &&
        !m.kind.startsWith('qcow') &&
        m.task &&
        m.task !== 'None' &&
        m.task !== 'null' &&
        m.task !== 'undefined',
    )
    test.skip(!isoWithTask, 'no Downloaded ISO media with a task id in the system')

    await gotoMedia(page)
    await waitForDownloadedTable(page)

    const row = page.locator(`#media tbody tr[id="${isoWithTask.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    const taskResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/task/${isoWithTask.task}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await row.locator('button#btn-task').click()
    expect((await taskResp).status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /last task info/i }),
    ).toBeVisible({ timeout: 5000 })
  })

  // C6 runs after all other read-only C tests because PUT /check sets the
  // media status to 'deleted' when no physical file exists (test environment).
  // Any test that needs Downloaded ISO media must run before C6.
  test('C6: Check media status opens confirmation and calls check endpoint', async ({ authenticatedPage: page, apiv4Admin }) => {
    const media = await listDownloadedMedia(apiv4Admin)
    const iso = media.find((m) => m.kind && !m.kind.startsWith('qcow'))
    test.skip(!iso, 'no Downloaded ISO (non-qcow) media in the system')

    await gotoMedia(page)
    await waitForDownloadedTable(page)

    const row = page.locator(`#media tbody tr[id="${iso.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-check').click()

    await expect(
      page.locator('.ui-pnotify-text', { hasText: /update the media status/i }),
    ).toBeVisible({ timeout: 5000 })

    const checkResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/media/${iso.id}/check`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    // The PUT check may return a non-2xx status in environments without a real
    // hypervisor (e.g. 428 when no worker is available to enqueue the task).
    // We only assert the request fired — the UI interaction is what C6 tests.
    await checkResp
  })

  // C2 targets 'e2e-delete-target' — a dedicated fixture excluded from
  // listDownloadedMedia so C6 and other C tests never touch it, guaranteeing
  // it stays in Downloaded state regardless of what the check endpoint does
  // to empty-iso (which C6 may transition to 'deleted' via the RQ task).
  test('C2: delete a Downloaded media shows confirmation modal and removes the row', async ({ authenticatedPage: page }) => {
    const target = { id: 'e2e-delete-target' }

    await gotoMedia(page)
    await waitForDownloadedTable(page)

    // Filter the DataTable so e2e-delete-target is visible regardless of how
    // many other rows exist (accumulated e2e-media-* can push it off page 1).
    await page.locator('#media_filter input').fill('E2E Delete Target')
    await page.waitForTimeout(400)

    const row = page.locator(`#media tbody tr[id="${target.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    const desktopsResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/media/${target.id}/get-desktops`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await row.locator('button#btn-delete').click()
    await desktopsResp

    const modal = page.locator('#modalDeleteMedia')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    const deleteResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/media/${target.id}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await deleteResp).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // The success handler hides the modal but does NOT remove the row from the
    // DataTable client-side (it relies on a WebSocket event). Navigate back and
    // do a fresh page load to verify the deletion is reflected in the API response.
    await gotoMedia(page)
    await waitForDownloadedTable(page)
    await expect(
      page.locator(`#media tbody tr[id="${target.id}"]`),
    ).not.toBeAttached({ timeout: 10000 })
  })

  // ── SECTION D — Secondary table (#mediaOtherTable) row actions ─────────

  test('D1: expanding a row in the secondary table shows domains detail', async ({ authenticatedPage: page, apiv4Admin }) => {
    const ctx = await loadOtherTable(page, apiv4Admin)
    test.skip(!ctx, 'no non-Downloaded status with media items found')

    const { firstRow } = ctx
    const mediaId = await firstRow.getAttribute('id')
    test.skip(!mediaId, 'first row has no id attribute')

    const domainsResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/items/media/domains/${mediaId}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await firstRow.locator('button#btn-details').click()
    expect((await domainsResp).status()).toBeLessThan(400)

    const child = page.locator(`[id="cl${mediaId}"]`)
    await expect(child).toBeVisible({ timeout: 10000 })

    await firstRow.locator('button#btn-details').click()
    await expect(child).toBeHidden({ timeout: 5000 })
  })

  test('D2: Check media status from the secondary table', async ({ authenticatedPage: page, apiv4Admin }) => {
    const ctx = await loadOtherTable(page, apiv4Admin)
    test.skip(!ctx, 'no non-Downloaded status with media items found')

    // Not all rows have btn-check (qcow2 in Stopped/Downloaded status omits it).
    const rowWithCheck = ctx.table
      .locator('tbody tr')
      .filter({ has: page.locator('button#btn-check') })
      .first()
    const hasRow = await rowWithCheck
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasRow, 'no row in secondary table has a btn-check button')

    const mediaId = await rowWithCheck.getAttribute('id')

    await rowWithCheck.locator('button#btn-check').click()

    await expect(
      page.locator('.ui-pnotify-text', { hasText: /update the media status/i }),
    ).toBeVisible({ timeout: 5000 })

    const checkResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/media/${mediaId}/check`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    // The PUT check may return a non-2xx status in environments without a real
    // hypervisor (e.g. 428 when no worker is available to enqueue the task).
    // We only assert the request fired — the UI interaction is what D2 tests.
    await checkResp
  })

  test('D3: Show last task info from the secondary table', async ({ authenticatedPage: page, apiv4Admin }) => {
    const ctx = await loadOtherTable(page, apiv4Admin)
    test.skip(!ctx, 'no non-Downloaded status with media items found')

    // Find the first row that actually has a task id — not necessarily the first row.
    const rowWithTask = ctx.table
      .locator('tbody tr')
      .filter({
        has: page.locator(
          'button#btn-task[data-task]:not([data-task="undefined"]):not([data-task="null"])',
        ),
      })
      .first()
    const hasRow = await rowWithTask
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasRow, 'no row in secondary table has a task id')

    const taskId = await rowWithTask.locator('button#btn-task').getAttribute('data-task')

    const taskResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/task/${taskId}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await rowWithTask.locator('button#btn-task').click()
    expect((await taskResp).status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /last task info/i }),
    ).toBeVisible({ timeout: 5000 })
  })
})
