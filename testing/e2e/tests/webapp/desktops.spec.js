// Drives the Desktops admin flows on /isard-admin/admin/domains/render/Desktops.
// Mirrors testing/e2e/specs/webapp/desktops.md — each test(...) maps to a
// numbered scenario in that spec.
//
// Conventions:
//   - Seeded desktops are referenced by ID (SEEDED.test, SEEDED.started, etc.).
//   - Dynamically created desktops are tracked via testInfo.annotations
//     (type 'desktop-name') so afterEach cleans them up even on failure.
//   - State mutations on seeded desktops are cleaned up via real API calls that
//     go through the engine and hypervisor; tests wait for the async transition
//     to complete before asserting.

import { test, expect, apiv4ClientForPage, unwrap } from '../../fixtures/apiv4/index.js'
import {
  adminListDomains,
  adminMultipleActions,
  deleteDesktop,
  editDesktop,
  deleteTemplate,
  bulkCreatePersistentDesktops,
  createDesktopFromMedia,
  createTemplate,
  getMediaInstalls,
  updateShareLink,
  startDesktop,
  stopDesktop,
  getDesktopDetails,
  getUserAllowedTemplatesFlat,
} from '../../src/gen/apiv4/sdk.gen'

const DESKTOPS_URL = '/isard-admin/admin/domains/render/Desktops'

// ─── seeded desktop constants ────────────────────────────────────────────────

const SEEDED = {
  test: { id: 'dae8fee5-93d6-4f80-ae0c-121d304910e4', name: 'Desktop with storage' },
  started: { id: '9a8b7c6d-5e4f-3a2b-1c9d-8e7f6a5b4c3d', name: 'Test started desktop' },
  failed: { id: '8b7c6d5e-4f3a-2b1c-9d8e-7f6a5b4c3d2e', name: 'Failed desktop' },
  maintenance: { id: '1f2e3d4c-5b6a-7c8d-9e0f-a1b2c3d4e5f6', name: 'Test maintenance desktop' },
  // Has create_dict.reservables.vgpus: ["NVIDIA-A16-2Q"] and booking_id: false.
  // Clicking Start triggers the "non-booked desktop" PNotify warning (S2 GPU sub-case).
  gpu: { id: '3c6b1eaa-2d4f-4f43-9f87-2b1ac2c3d4e5', name: 'Test desktop with GPU' },
  // Dedicated to S16 only — no other test touches this desktop, so PUT /increase
  // never races with S2's PUT /start (both share SEEDED.test under fullyParallel).
  s16: { id: '238b6c50-fc3f-40b9-8dc5-2f331c00c925', name: 'Desktop S16 storage' },
}

// The e2e-owned seed template (testing/db/data/domains.json → "Template Test Frontend").
// Used as the create-from source for every create-based test. We pick it explicitly
// instead of "first allowed template": the base demo "Slax" template that also ships
// in the dev DB carries forced_hyp/favourite_hyp as lists, which DesktopFromTemplate
// rejects ("invalid_desktop_data"), so blindly taking list[0] is non-deterministic and
// can yield an uncreatable template.
const SEEDED_TEMPLATE_ID = 'template-test-001'

// Seeded, already-Downloaded local ISO (testing/db/data/media.json → "empty-iso").
// Building a desktop from it makes the storage worker carve a real qcow2, so a
// template snapshotted from that desktop is disk-backed and its clones can boot —
// unlike the pure-DB seed template, whose desktops have no disk.
const BOOTABLE_MEDIA_ID = 'empty-iso'

// ─── state helpers ───────────────────────────────────────────────────────────

// Stop a desktop via API and wait for it to reach Stopped or Failed.
// Retries the stop every 3s to handle transitional states (e.g. Starting → Started)
// where the engine rejects the stop until the VM settles.
async function ensureDesktopStopped(client, domainId, { timeoutMs = 90000 } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const result = await getDesktopDetails({ client, path: { desktop_id: domainId } }).catch(() => null)
    const status = result?.data?.status
    if (status === 'Stopped' || status === 'Failed') return status
    await stopDesktop({ client, path: { desktop_id: domainId } }).catch(() => {})
    await new Promise((res) => setTimeout(res, 3000))
  }
  throw new Error(`desktop ${domainId} did not reach Stopped within ${timeoutMs}ms`)
}

// Start a desktop via API and wait for it to reach Started. The hypervisor boots
// it for real; retry the start if the engine is momentarily busy.
async function ensureDesktopStarted(client, domainId, { timeoutMs = 120000 } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const result = await getDesktopDetails({ client, path: { desktop_id: domainId } }).catch(() => null)
    const status = result?.data?.status
    if (status === 'Started') return status
    if (status === 'Stopped' || status === 'Failed') {
      await startDesktop({ client, path: { desktop_id: domainId } }).catch(() => {})
    }
    await new Promise((res) => setTimeout(res, 3000))
  }
  throw new Error(`desktop ${domainId} did not reach Started within ${timeoutMs}ms`)
}

// Passive wait (no stop issued): poll until the desktop settles to Stopped/Failed.
// Used while a freshly created desktop's disk is still being carved. Returns the
// final status, or null on timeout — never throws (callers treat it as best-effort).
async function waitForDesktopStopped(client, domainId, { timeoutMs = 180000 } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const result = await getDesktopDetails({ client, path: { desktop_id: domainId } }).catch(() => null)
    const status = result?.data?.status
    if (status === 'Stopped' || status === 'Failed') return status
    await new Promise((res) => setTimeout(res, 3000))
  }
  return null
}

// Statuses from which a template can't yet be cloned — bulkCreate rejects with
// 428 template_not_ready (see common lib desktops.py). A finished template
// settles to 'Stopped'.
const UNUSABLE_TEMPLATE_STATUSES = new Set([
  'CreatingTemplate',
  'Failed',
  'Maintenance',
  'DownloadStarting',
  'Downloading',
])

// Poll until a freshly snapshotted template's disk-copy chain finishes and its
// status leaves the unusable set, so clones can derive from it. Returns the
// ready status, or null on timeout (best-effort — never throws).
async function waitForTemplateReady(client, templateId, { timeoutMs = 180000 } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    // Query by id (get_by_ids plucks status); the kind:'template' list omits it.
    const rows = await unwrap(
      adminListDomains({ client, body: { domain_ids: [templateId] } }),
    ).catch(() => [])
    const tpl = Array.isArray(rows) ? rows.find((t) => t.id === templateId) : null
    // Require a concrete status string — a missing one keeps polling rather than
    // reading undefined as ready.
    if (tpl && typeof tpl.status === 'string' && !UNUSABLE_TEMPLATE_STATUSES.has(tpl.status)) {
      return tpl.status
    }
    await new Promise((res) => setTimeout(res, 3000))
  }
  return null
}

function uniqueDesktopName(testInfo, suffix = '') {
  return `e2e-desktop-${testInfo.workerIndex}-${Date.now()}${suffix ? `-${suffix}` : ''}`
}

function trackDesktopName(testInfo, name) {
  testInfo.annotations.push({ type: 'desktop-name', description: name })
}

async function listDesktopsViaApi(client) {
  const data = await unwrap(
    adminListDomains({ client, body: { kind: 'desktop' } }),
  ).catch(() => [])
  return Array.isArray(data) ? data : []
}

async function deleteDesktopViaApi(client, desktopId) {
  await deleteDesktop({ client, path: { desktop_id: desktopId } }).catch(() => {})
}

// ─── page helpers ────────────────────────────────────────────────────────────

async function gotoDesktops(page) {
  await page.goto(DESKTOPS_URL)
  await page
    .locator('.dataTables_wrapper:has(#domains), #domains_wrapper')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  await page
    .locator('#domains tbody tr:not(.dataTables_empty)')
    .first()
    .waitFor({ state: 'visible', timeout: 20000 })
  await page.locator('#domains_length select').selectOption('100')
}

function waitForTableRow(page, desktopId) {
  return page.locator(`#domains tbody tr[id="${desktopId}"]`)
}

async function findDesktopRow(page, desktopId, maxAttempts = 3) {
  let lastError
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await gotoDesktops(page)
    const row = waitForTableRow(page, desktopId)
    try {
      await expect(row).toBeVisible({ timeout: 8000 })
      return row
    } catch (err) {
      lastError = err
    }
  }
  throw lastError
}

async function findBothDesktopRows(page, id1, id2, maxAttempts = 3) {
  let lastError
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await gotoDesktops(page)
    try {
      await expect(waitForTableRow(page, id1)).toBeVisible({ timeout: 8000 })
      await expect(waitForTableRow(page, id2)).toBeVisible({ timeout: 8000 })
      return
    } catch (err) {
      lastError = err
    }
  }
  throw lastError
}

async function expandRowDetail(page, desktopId) {
  const expandBtn = page
    .locator(`#domains tbody tr[id="${desktopId}"] td.details-control button`)
    .first()
  await expandBtn.click()
  const detailPanel = page.locator(`[id="actions-${desktopId}"]`)
  await detailPanel.waitFor({ state: 'visible', timeout: 10000 })
  return detailPanel
}

async function clickPnotifyConfirm(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^(ok|yes|confirm)$/i })
    .first()
    .click({ timeout: 8000 })
}

// Select the admin user in the #alloweds-block users Select2.
// Used by S9 and S21-C once the bulk-create 500 bug is fixed.
// Done programmatically: Select2 v4 keeps select2-container--disabled even after
// iCheck fires ifChecked, so the search field stays invisible via UI interaction.
async function selectAdminUserInAlloweds(page) {
  await page.evaluate(() => {
    $('#alloweds-block #a-users-cb').iCheck('check')
    const $sel = $('#alloweds-block #a-users')
    $sel.prop('disabled', false)
    if (!$sel.find('option[value="local-default-admin-admin"]').length) {
      $sel.append(new Option('Administrator', 'local-default-admin-admin', true, true))
    }
    $sel.val(['local-default-admin-admin']).trigger('change')
  })
}

// ─── describe ────────────────────────────────────────────────────────────────

test.describe('Admin Desktops — webapp', () => {
  // Run the whole describe on a single worker, in file order. The seeded desktops
  // (SEEDED.test in particular) are shared across many tests; under fullyParallel
  // their WebSocket status events re-render the DataTable mid-click (element
  // detachment) and racing lifecycle mutations corrupt shared state. Serial mode
  // removes both classes of flakiness at the cost of wall-clock time — acceptable
  // for an integration suite that drives the real engine + hypervisor.
  test.describe.configure({ mode: 'serial' })

  // `sharedTemplateId` is the template the create tests clone from. `beforeAll`
  // prefers the disk-backed bootable template it builds (so clones can boot); if that
  // build fails it falls back to the diskless seed template. `bootableTemplateId` is
  // set ONLY when the real build succeeded — lifecycle tests gate on it.
  let sharedTemplateId = null
  let bootableTemplateId = null
  let bootableSourceDesktopId = null

  // Create a throwaway persistent desktop from `sharedTemplateId` and track it for
  // afterEach cleanup. When the bootable template is in use the clone inherits a real
  // qcow2 and can boot on the hypervisor; the diskless seeds never can. Every
  // start/stop/retry lifecycle test must use one (gated on `bootableTemplateId`).
  async function createDisposableDesktop(client, testInfo, suffix, templateId = sharedTemplateId) {
    const name = uniqueDesktopName(testInfo, suffix)
    trackDesktopName(testInfo, name)
    const created = await unwrap(
      bulkCreatePersistentDesktops({
        client,
        body: {
          name,
          description: `e2e ${suffix} target`,
          template_id: templateId,
          allowed: { roles: false, categories: false, groups: false, users: ['local-default-admin-admin'] },
        },
      }),
    )
    return { id: created?.ids?.[0] ?? null, name }
  }

  test.beforeAll(async ({ authenticatedContext }, workerInfo) => {
    // Beyond restoring the seeds, beforeAll builds a real disk-backed template
    // (media → desktop → template), which involves two storage-worker disk
    // operations. Allow plenty of headroom.
    test.setTimeout(600000)
    const page = await authenticatedContext.newPage()
    try {
      const client = apiv4ClientForPage(page)
      // Clean stale e2e-desktop-<workerIndex>-* leftovers from aborted runs.
      const prefix = `e2e-desktop-${workerInfo.workerIndex}-`
      const all = await listDesktopsViaApi(client)
      for (const d of all.filter((desktop) => desktop.name?.startsWith(prefix))) {
        await deleteDesktopViaApi(client, d.id)
      }
      // Restore seeded desktops to their expected initial state via the real API.
      // Transitions are processed asynchronously by the engine+hypervisor; we poll
      // until each desktop reaches the target status.
      // SEEDED.started (Started), SEEDED.failed (Failed) and SEEDED.maintenance
      // (Maintenance+current_action:increase) are guaranteed by populate_test_db.py —
      // those states cannot be recreated via API (no bootable disk image / engine-only transitions).
      //
      // Best-effort: a desktop wedged in `Starting` from a prior aborted run cannot be
      // recovered via API (stop is rejected from `Starting`). Don't let that hard-fail
      // beforeAll for the whole suite — only the few tests that strictly need Stopped
      // will surface it. The normal path (tests never start these seeds) keeps them Stopped.
      for (const id of [SEEDED.test.id, SEEDED.gpu.id, SEEDED.s16.id]) {
        await ensureDesktopStopped(client, id).catch((err) => {
          console.warn(`beforeAll: could not confirm ${id} Stopped — ${err.message}`)
        })
      }
      // Cache a template ID so individual tests don't each need to fetch it.
      // Prefer the e2e seed template (creatable); fall back to the first allowed
      // template only if it isn't present in this DB.
      const allowed = await unwrap(
        getUserAllowedTemplatesFlat({ client, path: { kind: 'all' } }),
      ).catch(() => [])
      const list = Array.isArray(allowed) ? allowed : []
      sharedTemplateId =
        list.find((t) => t.id === SEEDED_TEMPLATE_ID)?.id ?? list[0]?.id ?? null

      // ── Build a real, disk-backed template for the lifecycle tests ──────────
      // Seed desktops/templates have no qcow2, so their clones can't boot. Create a
      // desktop from the seeded (already-Downloaded) empty.iso media — the storage
      // worker carves a real disk — let it settle, then snapshot it into a template.
      // Desktops cloned from THIS template inherit a real disk and boot. Best-effort:
      // on any failure we keep the seed template (creation-only tests still run) and
      // the lifecycle tests skip on `!bootableTemplateId`.
      try {
        // /items/media/installs returns { installs: [...] }; the os_template must be a
        // real virt_install id — a bogus one wedges the desktop in CreatingDomain forever
        // (engine creating_and_test_xml_start: table('virt_install').get(id) → None → crash).
        const installsResp = await unwrap(getMediaInstalls({ client })).catch(() => null)
        const installs = Array.isArray(installsResp?.installs) ? installsResp.installs : []
        const osTemplate = installs[0]?.id
        if (!osTemplate) throw new Error('no virt_install os_template available — skipping bootable template build')
        const stamp = `${workerInfo.workerIndex}-${Date.now()}`
        const fromMedia = await unwrap(
          createDesktopFromMedia({
            client,
            body: {
              media_id: BOOTABLE_MEDIA_ID,
              kind: 'iso',
              os_template: osTemplate,
              name: `e2e-bootable-src-${stamp}`,
              description: 'e2e bootable template source',
              guest_properties: { viewers: { browser_vnc: { options: null } } },
              hardware: {
                boot_order: ['disk'],
                disk_bus: 'default',
                disk_size: 10,
                interfaces: ['default'],
                memory: 1.0,
                vcpus: 1,
                videos: ['default'],
                reservables: { vgpus: null },
              },
            },
          }),
        )
        bootableSourceDesktopId = fromMedia?.id ?? null
        if (bootableSourceDesktopId && (await waitForDesktopStopped(client, bootableSourceDesktopId)) === 'Stopped') {
          const tpl = await unwrap(
            createTemplate({
              client,
              body: {
                desktop_id: bootableSourceDesktopId,
                name: `e2e-bootable-tpl-${stamp}`,
                description: 'e2e bootable template',
                allowed: { groups: false, users: false },
                enabled: true,
              },
            }),
          )
          const newTemplateId = tpl?.id ?? null
          if (newTemplateId) {
            // The snapshot is registered immediately but stays 'CreatingTemplate'
            // until its disk-copy chain finishes — cloning before that fails with
            // 428 template_not_ready. Gate on the real status, not list membership
            // (the template is listed as allowed while still building).
            if (await waitForTemplateReady(client, newTemplateId)) {
              bootableTemplateId = newTemplateId
              sharedTemplateId = newTemplateId
              // Belt-and-suspenders: also wait until it surfaces in the allowed list.
              const tdeadline = Date.now() + 60000
              while (Date.now() < tdeadline) {
                const tl = await unwrap(
                  getUserAllowedTemplatesFlat({ client, path: { kind: 'all' } }),
                ).catch(() => [])
                if (Array.isArray(tl) && tl.some((t) => t.id === newTemplateId)) break
                await new Promise((res) => setTimeout(res, 3000))
              }
            } else {
              // Never became usable — keep the seed template so creation-only tests
              // run, leave bootableTemplateId null so lifecycle tests skip, and clean
              // up the half-built template.
              console.warn(`beforeAll: bootable template ${newTemplateId} never became ready`)
              await deleteTemplate({ client, path: { template_id: newTemplateId } }).catch(() => {})
            }
          }
        }
      } catch (err) {
        console.warn(`beforeAll: could not build bootable template — ${err.message}`)
      }
    } finally {
      await page.close()
    }
  })

  test.afterAll(async ({ authenticatedContext }) => {
    if (!bootableTemplateId && !bootableSourceDesktopId) return
    const page = await authenticatedContext.newPage()
    try {
      const client = apiv4ClientForPage(page)
      // Delete the source desktop first (it derives from the template), then the
      // template. Best-effort — leftovers are cleaned by the next run's prefix sweep.
      if (bootableSourceDesktopId) await deleteDesktopViaApi(client, bootableSourceDesktopId)
      if (bootableTemplateId) {
        await deleteTemplate({ client, path: { template_id: bootableTemplateId } }).catch(() => {})
      }
    } finally {
      await page.close()
    }
  })

  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    const names = testInfo.annotations
      .filter((a) => a.type === 'desktop-name')
      .map((a) => a.description)
    if (names.length > 0) {
      const all = await listDesktopsViaApi(apiv4Admin)
      for (const name of names) {
        const found = all.find((d) => d.name === name)
        if (found) await deleteDesktopViaApi(apiv4Admin, found.id)
      }
    }

    // Clean up template annotations from S8.
    const templateIds = testInfo.annotations
      .filter((a) => a.type === 'template-id')
      .map((a) => a.description)
    for (const tid of templateIds) {
      await deleteTemplate({ client: apiv4Admin, path: { template_id: tid } }).catch(() => {})
    }
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S1 — admin loads the desktops table and sees seeded desktops
  // ──────────────────────────────────────────────────────────────────────────
  test('S1: desktops DataTable loads with seeded desktop visible and status Stopped', async ({
    authenticatedPage: page,
  }) => {
    const tableResponse = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/items/domains') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await page.goto(DESKTOPS_URL)
    expect((await tableResponse).status()).toBeLessThan(400)

    await page
      .locator('.dataTables_wrapper:has(#domains), #domains_wrapper')
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })
    await page
      .locator('#domains tbody tr:not(.dataTables_empty)')
      .first()
      .waitFor({ state: 'visible', timeout: 20000 })
    await page.locator('#domains_length select').selectOption('100')

    const row = waitForTableRow(page, SEEDED.test.id)
    await expect(row).toBeVisible({ timeout: 10000 })

    // Status column shows Stopped.
    await expect(row.locator('td').filter({ hasText: /Stopped/i }).first()).toBeVisible({ timeout: 10000 })
    // Start button is present.
    await expect(row.locator('#btn-play')).toBeVisible({ timeout: 10000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S2 — admin starts a stopped desktop
  // ──────────────────────────────────────────────────────────────────────────
  test('S2: clicking Start on a Stopped desktop fires PUT /start and the desktop boots', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!bootableTemplateId, 'no bootable template available (media→desktop→template build failed)')
    test.setTimeout(180000)

    // The seeds have no qcow2 and can't boot — create a real desktop for the start.
    const { id } = await createDisposableDesktop(apiv4Admin, testInfo, 's2')
    if (!id) test.skip(true, 'bulk-create did not return an id')
    await ensureDesktopStopped(apiv4Admin, id)

    const row = await findDesktopRow(page, id)
    await expect(row.locator('td').filter({ hasText: /^Stopped$/i }).first()).toBeVisible({ timeout: 10000 })
    await expect(row.locator('#btn-play')).toBeVisible({ timeout: 10000 })

    const startResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${id}/start`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await row.locator('#btn-play').click()
    expect((await startResponse).status()).toBeLessThan(400)

    // The single UI click fires one PUT /start with no retry; confirm the real boot
    // via the API (which re-issues start if the engine is momentarily busy) before
    // asserting the row's Start button has given way to Stop.
    await ensureDesktopStarted(apiv4Admin, id)
    await expect(row.locator('#btn-stop')).toBeVisible({ timeout: 30000 })

    // Stop it so afterEach can delete it.
    await ensureDesktopStopped(apiv4Admin, id)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S2 (GPU sub-case) — Start on a desktop with GPU reservables shows the
  // "non-booked desktop" PNotify warning; Cancel aborts, Confirm fires PUT /start
  // ──────────────────────────────────────────────────────────────────────────
  // Confirm-fires-PUT/start is deliberately NOT asserted here: the hypervisor isn't
  // guaranteed to expose the vGPU reservable (NVIDIA-A16-2Q) this seed requires, so a
  // confirmed start could legitimately fail to schedule. The GPU-specific behaviour
  // under test is the non-booked warning gate, which the Cancel path fully exercises
  // (it confirms Confirm vs Cancel are wired and that Cancel suppresses start). The
  // real Start path itself is covered by S2 and S18.
  test('S2 (GPU): Start on GPU desktop shows non-booked warning; Cancel aborts without firing PUT /start', async ({
    authenticatedPage: page,
  }) => {
    await ensureDesktopStopped(apiv4ClientForPage(page), SEEDED.gpu.id)

    const row = await findDesktopRow(page, SEEDED.gpu.id)
    await expect(row.locator('#btn-play')).toBeVisible({ timeout: 10000 })

    // viewer_data GET fires first; the response feeds checkReservablesAndStart,
    // which shows the PNotify when reservables.vgpus is non-empty and booking_id is falsy.
    const viewerDataResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/domain/${SEEDED.gpu.id}/viewer_data`) &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await row.locator('#btn-play').click()
    expect((await viewerDataResponse).status()).toBeLessThan(400)

    const warning = page.locator('.ui-pnotify').filter({ hasText: /non-booked desktop/i }).first()
    await warning.waitFor({ state: 'visible', timeout: 8000 })

    // The warning must offer both Cancel and a confirm (OK/Yes/Confirm) action.
    await expect(
      warning.locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^cancel$/i }),
    ).toBeVisible({ timeout: 5000 })
    await expect(
      warning.locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^(ok|yes|confirm)$/i }),
    ).toBeVisible({ timeout: 5000 })

    // Register listener before Cancel click so no timing gap.
    const unexpectedStart = page
      .waitForResponse(
        (r) =>
          r.url().includes(`/api/v4/item/desktop/${SEEDED.gpu.id}/start`) &&
          r.request().method() === 'PUT',
        { timeout: 1500 },
      )
      .then(() => true)
      .catch(() => false)

    await warning
      .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^cancel$/i })
      .click()

    expect(await unexpectedStart, 'Cancel must not fire PUT /start').toBe(false)
    // Row must still show the Start button — status unchanged (no wedge on the seed).
    await expect(row.locator('#btn-play')).toBeVisible({ timeout: 5000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S3 — admin stops a running desktop
  // ──────────────────────────────────────────────────────────────────────────
  test('S3: clicking Stop on a Started desktop fires PUT /stop and the desktop reaches Stopped', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!bootableTemplateId, 'no bootable template available (media→desktop→template build failed)')
    test.setTimeout(240000)

    // Seeds can't boot (no qcow2): create a real desktop and start it for real.
    const { id } = await createDisposableDesktop(apiv4Admin, testInfo, 's3')
    if (!id) test.skip(true, 'bulk-create did not return an id')
    await ensureDesktopStarted(apiv4Admin, id)

    const row = await findDesktopRow(page, id)
    await expect(row.locator('#btn-stop')).toBeVisible({ timeout: 10000 })

    const stopResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${id}/stop`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await row.locator('#btn-stop').click()
    expect((await stopResponse).status()).toBeLessThan(400)

    // The hypervisor shuts the VM down (Shutting-down → Stopped) and the row's
    // Start button returns in place via the WebSocket status event.
    await expect(row.locator('#btn-play')).toBeVisible({ timeout: 120000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S3 (force-stop sub-case) — Force stop on a Shutting-down desktop fires PUT /stop
  // ──────────────────────────────────────────────────────────────────────────
  test('S3 (force-stop): Force stop button on Shutting-down desktop fires PUT /stop', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!bootableTemplateId, 'no bootable template available (media→desktop→template build failed)')
    test.setTimeout(240000)

    // Use a disposable desktop so the shutdown lifecycle never touches a shared seed.
    const name = uniqueDesktopName(testInfo, 's3force')
    trackDesktopName(testInfo, name)
    const created = await unwrap(
      bulkCreatePersistentDesktops({
        client: apiv4Admin,
        body: {
          name,
          description: 'e2e force-stop target',
          template_id: sharedTemplateId,
          allowed: { roles: false, categories: false, groups: false, users: ['local-default-admin-admin'] },
        },
      }),
    )
    const desktopId = created?.ids?.[0]
    if (!desktopId) test.skip(true, 'bulk-create did not return an id')

    // Boot it on the hypervisor, then issue a graceful stop so it enters Shutting-down.
    await ensureDesktopStarted(apiv4Admin, desktopId)

    const row = await findDesktopRow(page, desktopId)
    await expect(row.locator('#btn-stop')).toBeVisible({ timeout: 10000 })

    // First click: graceful Stop → engine moves the desktop to Shutting-down, at which
    // point the same #btn-stop button relabels to "Force stop".
    const stopResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${desktopId}/stop`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await row.locator('#btn-stop').click()
    expect((await stopResponse).status()).toBeLessThan(400)

    // Wait for the Force stop button (Shutting-down). A guest that powers off quickly
    // may skip straight to Stopped — skip rather than fail if the window is missed.
    const forceStopBtn = row.locator('#btn-stop:has-text("Force stop")')
    try {
      await forceStopBtn.waitFor({ state: 'visible', timeout: 30000 })
    } catch {
      test.skip(true, 'desktop reached Stopped before the Shutting-down window could be observed')
    }

    // Second click: Force stop on a Shutting-down desktop fires PUT /stop again.
    const forceStopResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${desktopId}/stop`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await forceStopBtn.click()
    expect((await forceStopResponse).status()).toBeLessThan(400)

    await ensureDesktopStopped(apiv4Admin, desktopId)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S4 — admin retries a failed desktop
  // ──────────────────────────────────────────────────────────────────────────
  test('S4: clicking Retry on a Failed desktop fires PUT /retry and the desktop leaves Failed', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')
    test.setTimeout(180000)

    // Drive a desktop to Failed deterministically. force_failed can't fail a Stopped
    // desktop (the engine rejects Stopped/Started/Downloading/Shutting-down), and a
    // disk-backed desktop has no stable force_failable state. A clone of the diskless
    // seed template never gets a qcow2 and hangs in CreatingDisk — a force_failable
    // state — so force_failed moves it to Failed.
    const { id } = await createDisposableDesktop(apiv4Admin, testInfo, 's4', SEEDED_TEMPLATE_ID)
    if (!id) test.skip(true, 'bulk-create did not return an id')

    // Retry force_failed until it lands: the clone passes briefly through Creating, then
    // settles in CreatingDisk (no parent disk to overlay) — both accept force_failed.
    await expect
      .poll(
        async () => {
          await adminMultipleActions({
            client: apiv4Admin,
            body: { ids: [id], action: 'force_failed' },
          }).catch(() => {})
          const r = await getDesktopDetails({ client: apiv4Admin, path: { desktop_id: id } }).catch(() => null)
          return r?.data?.status
        },
        { timeout: 90000, intervals: [2000, 3000] },
      )
      .toBe('Failed')

    const row = await findDesktopRow(page, id)
    await expect(row.locator('#btn-update')).toBeVisible({ timeout: 10000 })

    const retryResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${id}/retry`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await row.locator('#btn-update').click()
    expect((await retryResponse).status()).toBeLessThan(400)

    // Retry re-launches the desktop: the status leaves Failed (→ Starting). The diskless
    // clone re-fails afterwards (no qcow2), so assert the transient departure from Failed
    // via the API rather than a permanent Started. It settles back to Failed for afterEach.
    await expect
      .poll(
        async () => {
          const r = await getDesktopDetails({ client: apiv4Admin, path: { desktop_id: id } }).catch(() => null)
          return r?.data?.status
        },
        { timeout: 60000, intervals: [500] },
      )
      .not.toBe('Failed')
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S5 — admin cancels a storage operation on a maintenance desktop
  // ──────────────────────────────────────────────────────────────────────────
  test('S5: Cancel task on Maintenance desktop calls abort-operations and shows success PNotify', async ({
    authenticatedPage: page,
  }) => {
    const row = await findDesktopRow(page, SEEDED.maintenance.id)
    await expect(row.locator('#btn-cancel')).toBeVisible({ timeout: 10000 })

    // The btn-cancel handler fires GET /domain/storage AFTER the PNotify confirm to retrieve
    // storage IDs, then PUT /abort-operations for each. Register both listeners first.
    const storageGetResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/domain/storage/${SEEDED.maintenance.id}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    const abortResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/item/storage/') &&
        r.url().includes('/abort-operations') &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )

    await row.locator('#btn-cancel').click()
    // PNotify confirmation dialog.
    await clickPnotifyConfirm(page)

    expect((await storageGetResponse).status()).toBeLessThan(400)
    expect((await abortResponse).status()).toBeLessThan(400)

    // Success PNotify title is "Cancelling current storage operation...".
    // Match on "Cancelling" (not "cancel") to avoid strict-mode violation when
    // the confirmation PNotify ("Are you sure you want to cancel…") is still visible.
    await expect(
      page.locator('.ui-pnotify-title').filter({ hasText: /cancelling/i }).first(),
    ).toBeVisible({ timeout: 8000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S6 — admin edits a desktop's name and description
  // ──────────────────────────────────────────────────────────────────────────
  test('S6: editing description via row detail modal fires PUT /edit and table refreshes', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    test.setTimeout(120000)
    // PUT /edit returns 428 unless the desktop is Stopped. No lifecycle test starts
    // SEEDED.test (they use disposable desktops with a real qcow2), so this is a
    // defensive no-op that also guards against manual interference.
    await ensureDesktopStopped(apiv4Admin, SEEDED.test.id)

    const row = await findDesktopRow(page, SEEDED.test.id)
    const detailPanel = await expandRowDetail(page, SEEDED.test.id)

    await detailPanel.locator('.btn-edit').click()
    const modal = page.locator('#modalEditDesktop')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Wait for setHardwareDomainIdDefaults AJAX to populate the form before submitting.
    const descInput = modal.locator('#description')
    await expect(descInput).not.toBeEmpty({ timeout: 8000 })

    const newDescription = `e2e edited at ${Date.now()}`
    await descInput.clear()
    await descInput.fill(newDescription)

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${SEEDED.test.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResponse).status()).toBeLessThan(400)

    await modal.waitFor({ state: 'hidden', timeout: 10000 })
    // The success callback updates a live PNotify with title "Updated", text "Domain updated successfully".
    await expect(
      page.locator('.ui-pnotify-text').filter({ hasText: /domain updated successfully/i }).first(),
    ).toBeVisible({ timeout: 5000 })
    // Row should still be visible after the reload.
    await expect(row).toBeVisible({ timeout: 10000 })

    // Restore seed description so S23 ("Base desktop" assertion) is not
    // order-dependent on whether S6 ran first in the same suite run.
    await editDesktop({
      client: apiv4Admin,
      path: { desktop_id: SEEDED.test.id },
      body: { description: 'Base desktop' },
    }).catch(() => {})
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S7 — admin deletes a desktop via the row detail panel
  // ──────────────────────────────────────────────────────────────────────────
  test('S7: delete desktop via row detail confirms PNotify and row disappears', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const name = uniqueDesktopName(testInfo, 's7')
    trackDesktopName(testInfo, name)

    // Create a desktop via API so we have a throwaway target.
    const created = await unwrap(
      bulkCreatePersistentDesktops({
        client: apiv4Admin,
        body: {
          name,
          description: 'e2e delete target',
          template_id: sharedTemplateId,
          allowed: { roles: false, categories: false, groups: false, users: ['local-default-admin-admin'] },
        },
      }),
    )
    const desktopId = created?.ids?.[0]
    if (!desktopId) test.skip(true, 'bulk-create did not return an id')

    await findDesktopRow(page, desktopId)
    const detailPanel = await expandRowDetail(page, desktopId)

    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${desktopId}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await detailPanel.locator('.btn-delete').click()
    await clickPnotifyConfirm(page)
    expect((await deleteResponse).status()).toBeLessThan(400)

    // Row should eventually disappear.
    await expect.poll(
      async () => {
        await page.goto(DESKTOPS_URL)
        await page
          .locator('#domains tbody tr')
          .first()
          .waitFor({ state: 'visible', timeout: 5000 })
          .catch(() => {})
        return page.locator(`#domains tbody tr[id="${desktopId}"]`).isVisible()
      },
      { timeout: 20000, intervals: [2000, 3000, 5000] },
    ).toBe(false)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S8 — admin creates a template from a desktop
  // ──────────────────────────────────────────────────────────────────────────
  test('S8: create template from desktop fires POST /template and modal closes', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!bootableTemplateId, 'no bootable template available (media→desktop→template build failed)')
    test.setTimeout(180000)

    // Create the template from a disposable desktop, not SEEDED.test: this keeps the
    // shared seed pristine and avoids the storage_pending_task idempotency trap (the
    // disposable is deleted in afterEach). The storage worker completes the queued
    // task against real storage.
    const name = uniqueDesktopName(testInfo, 's8')
    trackDesktopName(testInfo, name)
    const created = await unwrap(
      bulkCreatePersistentDesktops({
        client: apiv4Admin,
        body: {
          name,
          description: 'e2e template source',
          template_id: sharedTemplateId,
          allowed: { roles: false, categories: false, groups: false, users: ['local-default-admin-admin'] },
        },
      }),
    )
    const desktopId = created?.ids?.[0]
    if (!desktopId) test.skip(true, 'bulk-create did not return an id')

    // Template creation requires the source desktop Stopped.
    await ensureDesktopStopped(apiv4Admin, desktopId)

    await findDesktopRow(page, desktopId)
    const detailPanel = await expandRowDetail(page, desktopId)

    await detailPanel.locator('.btn-template').click()
    const modal = page.locator('#modalTemplateDesktop')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Enable the visibility checkbox.
    const enabledCheckbox = modal.locator('#enabled')
    const isChecked = await enabledCheckbox.isChecked()
    if (!isChecked) {
      await enabledCheckbox.click()
    }

    const templateResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/item/template') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await templateResponse
    expect(resp.status()).toBeLessThan(400)

    // Track template for cleanup in afterEach.
    const respBody = await resp.json().catch(() => ({}))
    if (respBody?.id) {
      testInfo.annotations.push({ type: 'template-id', description: respBody.id })
    }

    await modal.waitFor({ state: 'hidden', timeout: 10000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S9 — admin bulk-creates desktops from a template
  // ──────────────────────────────────────────────────────────────────────────
  test('S9: bulk-create desktop from modal fires POST /bulk-create and row appears', async ({
    authenticatedPage: page,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const name = uniqueDesktopName(testInfo, 's9')
    trackDesktopName(testInfo, name)

    await gotoDesktops(page)

    await page.locator('.btn-add-desktop').first().click()
    const modal = page.locator('#modalAddDesktop').first()
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#name').fill(name)

    // Select the e2e seed template row by id (the modal table sets rowId=id). Not
    // .first(): the table is ordered by name, so the first row is the base demo
    // "Slax" template whose forced_hyp/favourite_hyp are lists — bulk-create rejects
    // it with invalid_desktop_data. template-test-001 is the creatable seed template.
    const templateRow = page.locator(`#modal_add_desktops tbody tr[id="${SEEDED_TEMPLATE_ID}"]`)
    await templateRow.waitFor({ state: 'visible', timeout: 15000 })
    await templateRow.click()

    await selectAdminUserInAlloweds(page)

    const createResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/items/desktops/bulk-create') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await createResponse).status()).toBeLessThan(400)

    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // New row should appear (via WS or reload).
    await expect.poll(
      async () => {
        await page.goto(DESKTOPS_URL)
        await page
          .locator('#domains tbody tr')
          .first()
          .waitFor({ state: 'visible', timeout: 5000 })
          .catch(() => {})
        return page.locator(`#domains tbody tr:has-text("${name}")`).isVisible()
      },
      { timeout: 20000, intervals: [2000, 3000, 5000] },
    ).toBe(true)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S10 — admin bulk-edits hardware on multiple desktops
  // ──────────────────────────────────────────────────────────────────────────
  test('S10: bulk-edit hardware on two desktops fires PUT /bulk-edit', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const name1 = uniqueDesktopName(testInfo, 's10a')
    const name2 = uniqueDesktopName(testInfo, 's10b')
    trackDesktopName(testInfo, name1)
    trackDesktopName(testInfo, name2)

    const d1 = await unwrap(
      bulkCreatePersistentDesktops({
        client: apiv4Admin,
        body: {
          name: name1,
          description: 'e2e bulk-edit target 1',
          template_id: sharedTemplateId,
          allowed: { roles: false, categories: false, groups: false, users: ['local-default-admin-admin'] },
        },
      }),
    )
    const d2 = await unwrap(
      bulkCreatePersistentDesktops({
        client: apiv4Admin,
        body: {
          name: name2,
          description: 'e2e bulk-edit target 2',
          template_id: sharedTemplateId,
          allowed: { roles: false, categories: false, groups: false, users: ['local-default-admin-admin'] },
        },
      }),
    )
    const id1 = d1?.ids?.[0]
    const id2 = d2?.ids?.[0]
    if (!id1 || !id2) test.skip(true, 'bulk-create did not return ids')

    await findBothDesktopRows(page, id1, id2)

    const row1 = waitForTableRow(page, id1)
    const row2 = waitForTableRow(page, id2)

    await row1.locator('input[type="checkbox"]').first().check()
    await row2.locator('input[type="checkbox"]').first().check()

    await page.locator('.btn-bulk-edit-desktops').click()
    const modal = page.locator('#modalBulkEdit')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Change vCPUs to 2.
    // #hardware-vcpus is a <select> populated async by setHardwareOptions (AJAX).
    // Wait for option value="2" to be attached before selecting.
    const vcpusSelect = modal.locator('#hardware-vcpus')
    await expect(vcpusSelect.locator('option[value="2"]')).toBeAttached({ timeout: 10000 })
    await vcpusSelect.selectOption('2')

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/items/desktops/bulk-edit') &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResponse).status()).toBeLessThan(400)

    await modal.waitFor({ state: 'hidden', timeout: 10000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S11 — admin bulk-deletes selected desktops via multiple_actions
  // ──────────────────────────────────────────────────────────────────────────
  test('S11: multiple_actions delete on two selected desktops calls POST /multiple_actions', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const name1 = uniqueDesktopName(testInfo, 's11a')
    const name2 = uniqueDesktopName(testInfo, 's11b')
    trackDesktopName(testInfo, name1)
    trackDesktopName(testInfo, name2)

    const d1 = await unwrap(
      bulkCreatePersistentDesktops({
        client: apiv4Admin,
        body: {
          name: name1,
          description: 'e2e bulk-delete target 1',
          template_id: sharedTemplateId,
          allowed: { roles: false, categories: false, groups: false, users: ['local-default-admin-admin'] },
        },
      }),
    )
    const d2 = await unwrap(
      bulkCreatePersistentDesktops({
        client: apiv4Admin,
        body: {
          name: name2,
          description: 'e2e bulk-delete target 2',
          template_id: sharedTemplateId,
          allowed: { roles: false, categories: false, groups: false, users: ['local-default-admin-admin'] },
        },
      }),
    )
    const id1 = d1?.ids?.[0]
    const id2 = d2?.ids?.[0]
    if (!id1 || !id2) test.skip(true, 'bulk-create did not return ids')

    await findBothDesktopRows(page, id1, id2)

    const row1 = waitForTableRow(page, id1)
    const row2 = waitForTableRow(page, id2)

    await row1.locator('input[type="checkbox"]').first().check()
    await row2.locator('input[type="checkbox"]').first().check()

    const multiResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/multiple_actions') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )

    await page.locator('#mactions').selectOption({ value: 'delete' })
    await clickPnotifyConfirm(page)

    expect((await multiResponse).status()).toBeLessThan(400)

    // Rows should eventually disappear.
    await expect.poll(
      async () => {
        await page.goto(DESKTOPS_URL)
        await page
          .locator('#domains tbody tr')
          .first()
          .waitFor({ state: 'visible', timeout: 5000 })
          .catch(() => {})
        return (
          (await page.locator(`#domains tbody tr[id="${id1}"]`).isVisible()) ||
          (await page.locator(`#domains tbody tr[id="${id2}"]`).isVisible())
        )
      },
      { timeout: 25000, intervals: [2000, 3000, 5000] },
    ).toBe(false)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S12 — admin applies force_failed to all desktops (requires "I'm aware")
  // ──────────────────────────────────────────────────────────────────────────
  test('S12: force_failed with wrong phrase shows Cancelled; correct phrase fires POST /multiple_actions', async ({
    authenticatedPage: page,
  }) => {
    await gotoDesktops(page)

    const rowCount = await page.locator('#domains tbody tr:not(.dataTables_empty)').count()
    test.skip(rowCount < 1, 'no desktops in table — skipping destructive test')

    let apiFired = false
    page.on('request', (req) => {
      if (
        req.url().includes('/api/v4/admin/items/multiple_actions') &&
        req.method() === 'POST'
      ) {
        apiFired = true
      }
    })

    // Open the force_failed prompt (one prompt, reused for both attempts).
    await page.locator('#mactions').selectOption({ value: 'force_failed' })

    const promptPnotify = page.locator('.ui-pnotify').filter({ has: page.locator('input[type="text"]') }).first()
    const promptInput = promptPnotify.locator('input[type="text"]')
    const promptOk = promptPnotify.locator('.ui-pnotify-action-button', { hasText: /^ok$/i })

    await promptInput.waitFor({ state: 'visible', timeout: 8000 })

    // First attempt: wrong phrase — prompt stays open, "Cancelled" PNotify appears.
    await promptInput.fill('yes')
    await promptOk.click()
    await expect(
      page.locator('.ui-pnotify-text, .ui-pnotify-title').filter({ hasText: /cancelled/i }),
    ).toBeVisible({ timeout: 5000 })
    expect(apiFired, 'API must NOT fire with wrong phrase').toBeFalsy()

    // Second attempt: correct phrase in the same prompt still open.
    await promptInput.clear()
    await promptInput.fill("I'm aware")

    const multiResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/multiple_actions') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )

    await promptOk.click()

    expect((await multiResponse).status()).toBeLessThan(400)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S13 — admin changes the owner of a desktop
  // ──────────────────────────────────────────────────────────────────────────
  test('S13: change owner via modal fires PUT /change-owner and User column updates', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!sharedTemplateId, 'no template available in the dev DB')

    const name = uniqueDesktopName(testInfo, 's13')
    trackDesktopName(testInfo, name)

    const created = await unwrap(
      bulkCreatePersistentDesktops({
        client: apiv4Admin,
        body: {
          name,
          description: 'e2e owner change target',
          template_id: sharedTemplateId,
          allowed: { roles: false, categories: false, groups: false, users: ['local-default-admin-admin'] },
        },
      }),
    )
    const desktopId = created?.ids?.[0]
    if (!desktopId) test.skip(true, 'bulk-create did not return an id')

    await findDesktopRow(page, desktopId)
    const detailPanel = await expandRowDetail(page, desktopId)

    await detailPanel.locator('.btn-owner').click()
    const modal = page.locator('#modalChangeOwnerDomain')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Select2 value set programmatically (same pattern as selectAdminUserInAlloweds):
    // UI interaction with Select2 AJAX dropdowns is unreliable in headless Playwright.
    await page.evaluate(async () => {
      await new Promise((resolve, reject) => {
        $.ajax({
          type: 'POST',
          url: '/api/v4/items/alloweds/term/users',
          dataType: 'json',
          contentType: 'application/json',
          data: JSON.stringify({ term: 'User Default', pluck: ['id', 'name'] }),
          success(data) {
            const user = data.find((u) => u.uid === 'user01') || data[0]
            if (!user) return reject(new Error('user01 not found in alloweds response (searched name="User Default")'))
            const $sel = $('#new_owner')
            if (!$sel.find(`option[value="${user.id}"]`).length) {
              $sel.append(new Option(user.name, user.id, true, true))
            }
            $sel.val([user.id]).trigger('change')
            resolve()
          },
          error(_, status, err) {
            reject(new Error(`alloweds AJAX failed: ${status} ${err}`))
          },
        })
      })
    })

    const ownerResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${desktopId}/change-owner/`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await ownerResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // User column in table should update.
    // gotoDesktops sets page size to 100 so the row is in the DOM regardless of position.
    await expect.poll(
      async () => {
        await gotoDesktops(page)
        const text = await page
          .locator(`#domains tbody tr[id="${desktopId}"]`)
          .textContent()
          .catch(() => '')
        return text.toLowerCase().includes('user default')
      },
      { timeout: 30000, intervals: [3000, 5000, 7000] },
    ).toBe(true)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S14 — admin enables and disables the share link (jump URL)
  // ──────────────────────────────────────────────────────────────────────────
  test('S14: enable share link via modal fires PUT update-share-link {enabled:true}, then disable', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await findDesktopRow(page, SEEDED.test.id)
    const detailPanel = await expandRowDetail(page, SEEDED.test.id)

    await detailPanel.locator('.btn-jumperurl').click()
    const modal = page.locator('#modalJumperurl').first()
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Enable share link — #jumperurl-check is an iCheck widget; click via jQuery API.
    const enableResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${SEEDED.test.id}/update-share-link`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await page.evaluate(() => $('#jumperurl-check').iCheck('check'))
    expect((await enableResponse).status()).toBeLessThan(400)

    // The URL field should be visible and contain a non-empty URL.
    await expect(modal.locator('#jumperurl')).toBeVisible({ timeout: 5000 })
    await expect(modal.locator('#jumperurl')).not.toHaveValue('', { timeout: 5000 })
    // Copy button must also be visible.
    await expect(modal.locator('.btn-copy-jumperurl')).toBeVisible({ timeout: 5000 })

    // Disable share link.
    const disableResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${SEEDED.test.id}/update-share-link`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await page.evaluate(() => $('#jumperurl-check').iCheck('uncheck'))
    // PNotify confirmation dialog for disable.
    await clickPnotifyConfirm(page)
    expect((await disableResponse).status()).toBeLessThan(400)

    // URL field and Copy button must both be hidden.
    await expect(modal.locator('#jumperurl')).toBeHidden({ timeout: 5000 })
    await expect(modal.locator('.btn-copy-jumperurl')).toBeHidden({ timeout: 5000 })

    // Cleanup: ensure share link is disabled.
    await updateShareLink({
      client: apiv4Admin,
      path: { desktop_id: SEEDED.test.id },
      body: { enabled: false },
    }).catch(() => {})
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S15 — admin sets and clears forced hypervisor
  // ──────────────────────────────────────────────────────────────────────────
  test('S15: set forced hypervisor fires PUT /edit {forced_hyp:[...]}, clear fires PUT {forced_hyp:false}', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    // Defensive reset: a previous run that failed before its own cleanup (or manual
    // interference) may have left forced_hyp set, causing the checkbox to start
    // checked and the assertion at line 1071 to fail on the next run.
    await editDesktop({
      client: apiv4Admin,
      path: { desktop_id: SEEDED.test.id },
      body: { forced_hyp: false },
    }).catch(() => {})

    await findDesktopRow(page, SEEDED.test.id)
    const detailPanel = await expandRowDetail(page, SEEDED.test.id)

    await detailPanel.locator('.btn-forcedhyp').click()
    const modal = page.locator('#modalForcedhyp')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    const checkbox = modal.locator('#forcedhyp-check')
    await expect(checkbox).not.toBeChecked()

    // Enable forced hyp — iCheck widget: use iCheck API so ifChecked fires.
    await page.evaluate(() => $('#forcedhyp-check').iCheck('check'))
    const hypDropdown = modal.locator('#forced_hyp')
    await hypDropdown.waitFor({ state: 'visible', timeout: 10000 })
    // AJAX populates options asynchronously after the select appears; wait before skipping.
    await hypDropdown.locator('option:not([value=""])').first()
      .waitFor({ state: 'attached', timeout: 5000 })
      .catch(() => {})

    // Select first hypervisor option (if any).
    const options = await hypDropdown.locator('option:not([value=""])').all()
    if (options.length === 0) {
      test.skip(true, 'no hypervisors registered in dev DB')
    }
    await hypDropdown.selectOption({ index: 0 })
    const selectedHypId = await hypDropdown.locator('option:checked').getAttribute('value')

    const setResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${SEEDED.test.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await setResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Reload and verify Forced Hyper column shows the chosen hypervisor ID.
    await gotoDesktops(page)
    const row2 = await findDesktopRow(page, SEEDED.test.id)
    await expect(row2.locator('td').filter({ hasText: selectedHypId }).first()).toBeVisible()
    const detailPanel2 = await expandRowDetail(page, SEEDED.test.id)

    await detailPanel2.locator('.btn-forcedhyp').click()
    const modal2 = page.locator('#modalForcedhyp')
    await modal2.waitFor({ state: 'visible', timeout: 10000 })

    const checkbox2 = modal2.locator('#forcedhyp-check')
    await expect(checkbox2).toBeChecked()
    await page.evaluate(() => $('#forcedhyp-check').iCheck('uncheck'))

    const clearResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${SEEDED.test.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal2.locator('#send').click()
    expect((await clearResponse).status()).toBeLessThan(400)
    await modal2.waitFor({ state: 'hidden', timeout: 10000 })

    // Reload and verify Forced Hyper column reverts to '-'.
    await gotoDesktops(page)
    await findDesktopRow(page, SEEDED.test.id)
    const forcedHypAfterClear = await page.evaluate((id) => {
      const d = window.domains_table?.row(`#${id}`)?.data()
      return d ? (d.forced_hyp && d.forced_hyp.length > 0 ? d.forced_hyp.join(',') : '-') : null
    }, SEEDED.test.id)
    expect(forcedHypAfterClear, 'Forced Hyper column must revert to "-" after clear').toBe('-')

    // Cleanup via API.
    await editDesktop({
      client: apiv4Admin,
      path: { desktop_id: SEEDED.test.id },
      body: { forced_hyp: false },
    }).catch(() => {})
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S16 — admin views storage and increases disk size
  //       Includes a Cancel sub-case (no API call) and a valid-increment happy path.
  //       The Increase button now opens #modalIncreaseStorage instead of window.prompt;
  //       validation is handled by Parsley on the form's #new-size number input.
  // ──────────────────────────────────────────────────────────────────────────
  test('S16: storage modal opens; Cancel aborts without API call; valid new size calls PUT /increase', async ({
    authenticatedPage: page,
  }) => {
    test.setTimeout(120000)
    // Use SEEDED.s16 — a desktop dedicated to this test only — so it never races
    // with S2's PUT /start (both previously shared SEEDED.test under fullyParallel).
    // Ensure Stopped and let the storage worker finish any pending task from a
    // previous run before the next PUT /increase call.
    await ensureDesktopStopped(apiv4ClientForPage(page), SEEDED.s16.id)

    const row = await findDesktopRow(page, SEEDED.s16.id)
    await expect(row.locator('#btn-storage')).toBeVisible({ timeout: 10000 })

    const storageGetResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/domain/storage/${SEEDED.s16.id}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await row.locator('#btn-storage').click()
    const storageModal = page.locator('#modalDesktopStorage')
    await storageModal.waitFor({ state: 'visible', timeout: 10000 })

    expect((await storageGetResponse).status()).toBeLessThan(400)

    // The Increase button now delegates to the shared .btn-increase handler
    // (storage_increase.js) instead of using window.prompt.
    const increaseBtn = storageModal.locator('.btn-increase').first()
    await increaseBtn.waitFor({ state: 'visible', timeout: 10000 })

    const increaseModal = page.locator('#modalIncreaseStorage')

    // ── Cancel path ───────────────────────────────────────────────────────
    // Clicking Increase fires three AJAXs (storage info, has-derivatives,
    // appliedquota), then closes #modalDesktopStorage and opens
    // #modalIncreaseStorage. Clicking Cancel must not fire PUT /increase.
    const unexpectedIncrease = page
      .waitForResponse(
        (r) =>
          r.url().includes('/api/v4/item/storage/') &&
          r.url().includes('/increase/') &&
          r.request().method() === 'PUT',
        { timeout: 1500 },
      )
      .then(() => true)
      .catch(() => false)

    await increaseBtn.click()
    await storageModal.waitFor({ state: 'hidden', timeout: 15000 })
    await increaseModal.waitFor({ state: 'visible', timeout: 15000 })

    await increaseModal.locator('button').filter({ hasText: /^cancel$/i }).click()
    expect(await unexpectedIncrease, 'Cancel must not call PUT /increase').toBe(false)
    await increaseModal.waitFor({ state: 'hidden', timeout: 5000 })

    // ── Happy path: valid new size → PUT /increase ────────────────────────
    await row.locator('#btn-storage').click()
    await storageModal.waitFor({ state: 'visible', timeout: 10000 })
    await increaseBtn.waitFor({ state: 'visible', timeout: 10000 })

    await increaseBtn.click()
    await storageModal.waitFor({ state: 'hidden', timeout: 15000 })
    await increaseModal.waitFor({ state: 'visible', timeout: 15000 })

    // The modal pre-fills #new-size with virtual_size (10 GB) and sets
    // min = virtual_size + 1 = 11. Add 1 to satisfy the Parsley min constraint.
    const currentSizeRaw = await page.locator('#modalIncreaseStorage #current_size').inputValue()
    const currentSizeGb = parseFloat(currentSizeRaw) || 0
    const newSizeGb = Math.ceil(currentSizeGb) + 1

    const increaseResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/item/storage/') &&
        r.url().includes('/increase/') &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )

    // Use jQuery to set the value and trigger change so Parsley re-validates
    // #new-size before the #send click fires the delegated handler.
    await page.evaluate((v) => {
      $('#modalIncreaseStorage #new-size').val(v).trigger('change')
      $('#modalIncreaseStorage #send').trigger('click')
    }, newSizeGb)

    expect((await increaseResponse).status()).toBeLessThan(400)

    // performStorageOperation shows "Task created successfully" on success
    // and hides all modals via $('.modal').modal('hide').
    await expect(
      page.locator('.ui-pnotify-title').filter({ hasText: /task created successfully/i }).first(),
    ).toBeVisible({ timeout: 5000 })
    await expect(increaseModal).toBeHidden({ timeout: 5000 })

    // Clean up: wait for the storage worker to finish the increase task and the
    // desktop to return to Stopped before the next run.
    await ensureDesktopStopped(apiv4ClientForPage(page), SEEDED.s16.id)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S17 — admin enables server mode with autostart
  // ──────────────────────────────────────────────────────────────────────────
  test('S17: enable server mode + autostart fires PUT /edit {server:true,server_autostart:true}; disable restores', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await findDesktopRow(page, SEEDED.test.id)
    const detailPanel = await expandRowDetail(page, SEEDED.test.id)

    await detailPanel.locator('.btn-server').click()
    const modal = page.locator('#modalServer').first()
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    const serverCheckbox = modal.locator('#server')
    await expect(serverCheckbox).not.toBeChecked()

    // iCheck requires jQuery API — clicking the ins overlay directly fails due to pointer event interception.
    // Mirror the app's own iCheck call pattern: check + update + trigger ifChecked so autostart enables.
    await page.evaluate(() =>
      $('#modalServerForm #server').iCheck('check').iCheck('update').trigger('ifChecked'),
    )

    await page.evaluate(() => $('#modalServerForm #autostart').iCheck('check').iCheck('update'))

    const enableResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${SEEDED.test.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const enableRes = await enableResponse
    expect(enableRes.status()).toBeLessThan(400)
    const enableBody = JSON.parse((await enableRes.request().postData()) || '{}')
    expect(enableBody).toMatchObject({ server: true, server_autostart: true })
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Reload and verify Server column shows 'AUTO' after enable.
    await gotoDesktops(page)
    await findDesktopRow(page, SEEDED.test.id)
    const serverAfterEnable = await page.evaluate((id) => {
      const d = window.domains_table?.row(`#${id}`)?.data()
      return d ? (d.server ? (d.server_autostart ? 'AUTO' : 'SERVER') : '-') : null
    }, SEEDED.test.id)
    expect(serverAfterEnable, 'Server column must show "AUTO" after enable').toBe('AUTO')

    // Disable server mode — re-expand the detail panel after the reload.
    const detailPanel2 = await expandRowDetail(page, SEEDED.test.id)
    await detailPanel2.locator('.btn-server').click()
    const modal2 = page.locator('#modalServer').first()
    await modal2.waitFor({ state: 'visible', timeout: 10000 })

    const serverCheckbox2 = modal2.locator('#server')
    await expect(serverCheckbox2).toBeChecked({ timeout: 10000 })
    await page.evaluate(() =>
      $('#modalServerForm #server').iCheck('uncheck').iCheck('update').trigger('ifUnchecked'),
    )

    const disableResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${SEEDED.test.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal2.locator('#send').click()
    expect((await disableResponse).status()).toBeLessThan(400)
    await modal2.waitFor({ state: 'hidden', timeout: 10000 })

    // Reload and verify Server column reverts to '-' after disable.
    await gotoDesktops(page)
    await findDesktopRow(page, SEEDED.test.id)
    const serverAfterDisable = await page.evaluate((id) => {
      const d = window.domains_table?.row(`#${id}`)?.data()
      return d ? (d.server ? (d.server_autostart ? 'AUTO' : 'SERVER') : '-') : null
    }, SEEDED.test.id)
    expect(serverAfterDisable, 'Server column must revert to "-" after disable').toBe('-')

    // Cleanup via API.
    await editDesktop({
      client: apiv4Admin,
      path: { desktop_id: SEEDED.test.id },
      body: { server: false, server_autostart: false },
    }).catch(() => {})
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S18 — admin opens the Info modal for a desktop
  // ──────────────────────────────────────────────────────────────────────────
  test('S18: Info modal shows desktop ID; Start button fires PUT /start; UUID search opens same modal; invalid UUID shows error', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    test.skip(!bootableTemplateId, 'no bootable template available (media→desktop→template build failed)')
    test.setTimeout(180000)

    // The Start sub-case boots the desktop, so it needs a real qcow2 — use a created
    // desktop, not a seed. The modal display + UUID-search assertions work on it too.
    const { id } = await createDisposableDesktop(apiv4Admin, testInfo, 's18')
    if (!id) test.skip(true, 'bulk-create did not return an id')
    await ensureDesktopStopped(apiv4Admin, id)

    await gotoDesktops(page)

    const row = waitForTableRow(page, id)
    await expect(row).toBeVisible({ timeout: 10000 })

    // Click the info button on the row — button has data-domain-info attribute.
    await row.locator('button[data-domain-info]').first().click()

    const infoModal = page.locator('#domain-info-modal')
    await infoModal.waitFor({ state: 'visible', timeout: 10000 })

    // Modal loads content via AJAX — wait for the desktop ID to appear.
    await expect(infoModal).toContainText(id, { timeout: 10000 })
    // Owner section must have at least one row (username, role, etc.).
    await expect(infoModal.locator('#owner-info-table tr')).not.toHaveCount(0, { timeout: 8000 })
    // Network interfaces section must render (either real entries or the "No interfaces" message).
    await expect(infoModal.locator('#interfaces-info-table tr')).not.toHaveCount(0, { timeout: 8000 })

    // ── Start button sub-case ─────────────────────────────────────────────
    // .btn-domain-start is enabled for Stopped/Failed desktops and fires
    // PUT /start directly — no reservables/booking check (unlike the table row button).
    // The hypervisor boots the desktop for real; it is returned to Stopped at the end.
    const startBtn = infoModal.locator('.btn-domain-start')
    await expect(startBtn).toBeVisible({ timeout: 5000 })
    await expect(startBtn).toBeEnabled({ timeout: 5000 })

    const startResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${id}/start`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await startBtn.click()
    expect((await startResponse).status()).toBeLessThan(400)

    // Close modal.
    await infoModal.locator('[data-dismiss="modal"]').first().click()
    await infoModal.waitFor({ state: 'hidden', timeout: 5000 })

    // UUID search sub-case: valid UUID.
    const uuidSearch = page.locator('#domain-uuid-search')
    const uuidSearchVisible = await uuidSearch.isVisible()
    if (uuidSearchVisible) {
      // click() ensures focus after the Bootstrap modal close steals it;
      // without it fill() sets the value but press('Enter') is silently ignored.
      await uuidSearch.click()
      await uuidSearch.fill(id)
      await uuidSearch.press('Enter')

      await infoModal.waitFor({ state: 'visible', timeout: 10000 })
      await expect(infoModal).toContainText(id, { timeout: 10000 })

      // Close modal.
      await infoModal.locator('[data-dismiss="modal"]').first().click()
      await infoModal.waitFor({ state: 'hidden', timeout: 5000 })

      // Invalid UUID — PNotify title: "Invalid UUID", text: "Please enter a valid UUID format."
      await uuidSearch.click()
      await uuidSearch.fill('not-a-valid-uuid')
      await uuidSearch.press('Enter')
      await expect(
        page.locator('.ui-pnotify-title').filter({ hasText: 'Invalid UUID' }),
      ).toBeVisible({ timeout: 5000 })

      // Empty field — PNotify title: "Error", text: "Please enter a desktop ID to search for."
      await uuidSearch.fill('')
      await uuidSearch.press('Enter')
      await expect(
        page.locator('.ui-pnotify-text').filter({ hasText: 'Please enter a desktop ID' }),
      ).toBeVisible({ timeout: 5000 })
    }

    // Stop it so afterEach can delete it (the real Start booted it).
    await ensureDesktopStopped(apiv4Admin, id)
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S19 — admin sets and clears favourite hypervisor
  // ──────────────────────────────────────────────────────────────────────────
  test('S19: set favourite hyp fires PUT /edit {favourite_hyp:[...]}, clear fires PUT {favourite_hyp:false}', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await findDesktopRow(page, SEEDED.test.id)
    const detailPanel = await expandRowDetail(page, SEEDED.test.id)

    await detailPanel.locator('.btn-favouritehyp').click()
    const modal = page.locator('#modalFavouriteHyp')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    const checkbox = modal.locator('#favouritehyp-check')
    await expect(checkbox).not.toBeChecked()

    // iCheck requires jQuery API — clicking the hidden input bypasses ifChecked.
    await page.evaluate(() => $('#favouritehyp-check').iCheck('check'))
    const hypDropdown = modal.locator('#favourite_hyp')
    await hypDropdown.waitFor({ state: 'visible', timeout: 10000 })
    // AJAX populates options asynchronously after the select appears; wait before skipping.
    await hypDropdown.locator('option:not([value=""])').first()
      .waitFor({ state: 'attached', timeout: 5000 })
      .catch(() => {})

    const options = await hypDropdown.locator('option:not([value=""])').all()
    if (options.length === 0) {
      test.skip(true, 'no hypervisors registered in dev DB')
    }
    await hypDropdown.selectOption({ index: 0 })
    const selectedHypId = await hypDropdown.locator('option:checked').getAttribute('value')

    const setResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${SEEDED.test.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await setResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Reload and verify Fav Hyper column shows the chosen hypervisor ID.
    await gotoDesktops(page)
    const row2 = await findDesktopRow(page, SEEDED.test.id)
    await expect(row2.locator('td').filter({ hasText: selectedHypId }).first()).toBeVisible()
    const detailPanel2 = await expandRowDetail(page, SEEDED.test.id)

    await detailPanel2.locator('.btn-favouritehyp').click()
    const modal2 = page.locator('#modalFavouriteHyp')
    await modal2.waitFor({ state: 'visible', timeout: 10000 })

    const checkbox2 = modal2.locator('#favouritehyp-check')
    await expect(checkbox2).toBeChecked()
    await page.evaluate(() => $('#favouritehyp-check').iCheck('uncheck'))

    const clearResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${SEEDED.test.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal2.locator('#send').click()
    expect((await clearResponse).status()).toBeLessThan(400)
    await modal2.waitFor({ state: 'hidden', timeout: 10000 })

    // Reload and verify Fav Hyper column reverts to '-'.
    await gotoDesktops(page)
    await findDesktopRow(page, SEEDED.test.id)
    const favHypAfterClear = await page.evaluate((id) => {
      const d = window.domains_table?.row(`#${id}`)?.data()
      return d ? (d.favourite_hyp && d.favourite_hyp.length > 0 ? d.favourite_hyp.join(',') : '-') : null
    }, SEEDED.test.id)
    expect(favHypAfterClear, 'Fav Hyper column must revert to "-" after clear').toBe('-')

    // Cleanup via API.
    await editDesktop({
      client: apiv4Admin,
      path: { desktop_id: SEEDED.test.id },
      body: { favourite_hyp: false },
    }).catch(() => {})
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S20 — admin opens the desktop logs modal and both tabs load without error
  // ──────────────────────────────────────────────────────────────────────────
  test('S20: desktop logs modal opens; both POST /logs_desktops respond < 400; no error state', async ({
    authenticatedPage: page,
  }) => {
    await findDesktopRow(page, SEEDED.test.id)
    const detailPanel = await expandRowDetail(page, SEEDED.test.id)

    // Register first logs response before clicking.
    const logsPromise1 = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/logs_desktops') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )

    await detailPanel.locator('.btn-desktop-logs').click()
    const modal = page.locator('#desktop-logs-modal')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Modal title must include the desktop name (set by desktop_logs_modal.js line 161).
    await expect(modal.locator('#desktop-logs-title')).toHaveText(
      `Desktop Logs: ${SEEDED.test.name}`,
      { timeout: 8000 },
    )
    // Download CSV button must be present and enabled.
    await expect(modal.locator('#desktop-logs-csv-btn')).toBeVisible({ timeout: 5000 })
    await expect(modal.locator('#desktop-logs-csv-btn')).toBeEnabled({ timeout: 5000 })

    expect((await logsPromise1).status()).toBeLessThan(400)

    // Tab 1: desktop logs table should be present.
    const logsTable = page.locator('#table-desktop-logs')
    await logsTable.waitFor({ state: 'visible', timeout: 10000 })

    // Switch to Direct Viewer tab.
    const logsPromise2 = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/logs_desktops') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    const directViewerTab = modal
      .locator('a[data-target], a[href], li a')
      .filter({ hasText: /direct.*viewer|directviewer/i })
      .first()
    await directViewerTab.click()

    // Tab 2 data should have loaded.
    expect((await logsPromise2).status()).toBeLessThan(400)

    const dvTable = page.locator('#table-directviewer-logs')
    await dvTable.waitFor({ state: 'visible', timeout: 10000 })

    // Close the modal.
    await modal.locator('button').filter({ hasText: /close/i }).first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S21 — User/Category/Role/Group columns populated after load, edit, create
  // ──────────────────────────────────────────────────────────────────────────
  test('S21: User, Role, Category, Group columns show correct seeded values after initial load, edit, and create', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    // Expected values come from the seeded user (admin_e2e_09) who owns SEEDED.test.
    // See testing/db/data/users.json (id: c7e77d70-e443-53d2-9933-d9b83e4a19a1),
    // categories.json (id: default) and groups.json (id: default-default).
    const SEEDED_TEST_CELLS = {
      user_name: 'E2E Admin 09',
      role: 'admin',
      category_name: 'Default',
      group_name: 'Default',
    }

    // ── Part A: initial load ──────────────────────────────────────────────

    // Intercept the table-load API response so we can check the JSON values
    // directly — this catches the case where the backend omits a field entirely.
    // Register the listener before navigating so we don't race the first request.
    const tableLoadResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/domains') &&
        r.request().method() === 'POST',
      { timeout: 20000 },
    )
    const row = await findDesktopRow(page, SEEDED.test.id)
    await expect(row).toBeVisible()

    const tableData = await (await tableLoadResponse).json().catch(() => [])
    const apiEntry = Array.isArray(tableData)
      ? tableData.find((d) => d.id === SEEDED.test.id)
      : null
    if (apiEntry) {
      expect(apiEntry.user_name, 'API user_name').toBe(SEEDED_TEST_CELLS.user_name)
      expect(apiEntry.role, 'API role').toBe(SEEDED_TEST_CELLS.role)
      expect(apiEntry.category_name, 'API category_name').toBe(SEEDED_TEST_CELLS.category_name)
      expect(apiEntry.group_name, 'API group_name').toBe(SEEDED_TEST_CELLS.group_name)
    }

    // DataTables renders plain <td> elements — no data-field attributes.
    // Assert that each expected value is visible somewhere in the rendered row.
    async function verifyMetadataCells(r, expected) {
      for (const [field, value] of Object.entries(expected)) {
        await expect(r, `${field} value "${value}" should appear in row`).toContainText(value)
      }
    }

    await verifyMetadataCells(row, SEEDED_TEST_CELLS)

    // ── Part B: after ajax.reload() triggered by an edit ─────────────────
    const detailPanel = await expandRowDetail(page, SEEDED.test.id)
    await detailPanel.locator('.btn-edit').click()
    const modal = page.locator('#modalEditDesktop')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    const descInput = modal.locator('#description')
    await descInput.clear()
    await descInput.fill(`e2e S21 edit at ${Date.now()}`)

    const reloadResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/domains') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/item/desktop/${SEEDED.test.id}/edit`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Validate JSON fields in the ajax.reload() response.
    const reloadData = await (await reloadResponse).json().catch(() => [])
    const reloadEntry = Array.isArray(reloadData)
      ? reloadData.find((d) => d.id === SEEDED.test.id)
      : null
    if (reloadEntry) {
      expect(reloadEntry.user_name, 'reload user_name').toBe(SEEDED_TEST_CELLS.user_name)
      expect(reloadEntry.role, 'reload role').toBe(SEEDED_TEST_CELLS.role)
      expect(reloadEntry.category_name, 'reload category_name').toBe(SEEDED_TEST_CELLS.category_name)
      expect(reloadEntry.group_name, 'reload group_name').toBe(SEEDED_TEST_CELLS.group_name)
    }

    // After reload, the rendered row must still show the same seeded values.
    const rowAfterEdit = waitForTableRow(page, SEEDED.test.id)
    await expect(rowAfterEdit).toBeVisible({ timeout: 10000 })
    await verifyMetadataCells(rowAfterEdit, SEEDED_TEST_CELLS)

    // Restore seed description so S23 ("Base desktop" assertion) is not
    // order-dependent on whether S21 ran first in the same suite run.
    await editDesktop({
      client: apiv4Admin,
      path: { desktop_id: SEEDED.test.id },
      body: { description: 'Base desktop' },
    }).catch(() => {})

    // ── Part C: newly created desktop row ────────────────────────────────
    if (!sharedTemplateId) {
      // Cannot test create path without a template — skip Part C only.
      return
    }

    const name = uniqueDesktopName(testInfo, 's21c')
    trackDesktopName(testInfo, name)

    await unwrap(
      bulkCreatePersistentDesktops({
        client: apiv4Admin,
        body: {
          name,
          description: 'e2e S21 create target',
          template_id: sharedTemplateId,
          allowed: { roles: false, categories: false, groups: false, users: ['local-default-admin-admin'] },
        },
      }),
    )

    // Wait for the new row to appear and check metadata.
    let newRow = null
    await expect.poll(
      async () => {
        await page.goto(DESKTOPS_URL)
        await page
          .locator('#domains tbody tr')
          .first()
          .waitFor({ state: 'visible', timeout: 5000 })
          .catch(() => {})
        const found = page.locator(`#domains tbody tr:has-text("${name}")`).first()
        const visible = await found.isVisible()
        if (visible) newRow = found
        return visible
      },
      { timeout: 20000, intervals: [2000, 3000, 5000] },
    ).toBe(true)

    await verifyMetadataCells(newRow, { user_name: 'Administrator', role: 'admin', category_name: 'Default', group_name: 'Default' })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S22 — admin opens the XML sections editor and saves without changes
  // ──────────────────────────────────────────────────────────────────────────
  test('S22: XML sections modal opens, both GETs respond < 400, sections render, Save fires POST < 400', async ({
    authenticatedPage: page,
  }) => {
    await findDesktopRow(page, SEEDED.test.id)
    const detailPanel = await expandRowDetail(page, SEEDED.test.id)

    // Both GET requests fire in parallel on modal open.
    const sectionsResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/domains/xml_sections/${SEEDED.test.id}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    const capsResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/domains/xml_capabilities') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await detailPanel.locator('.btn-xml').click()
    const modal = page.locator('#modalEditXmlSections')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    expect((await sectionsResponse).status()).toBeLessThan(400)
    expect((await capsResponse).status()).toBeLessThan(400)

    // Container should render sections — not stay as a spinner or error alert.
    const container = modal.locator('#xmlSectionsContainer')
    await expect(container.locator('.alert-danger')).toBeHidden({ timeout: 10000 })
    await expect(container).not.toBeEmpty({ timeout: 10000 })

    // Save without changes — fires POST /xml_sections/{id} with the current state.
    const saveResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/domains/xml_sections/${SEEDED.test.id}`) &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#xmlSectionsSave').click()
    expect((await saveResponse).status()).toBeLessThan(400)

    await modal.waitFor({ state: 'hidden', timeout: 10000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S23 — row detail panel shows correct description and hardware
  // ──────────────────────────────────────────────────────────────────────────
  test('S23: expanding row detail shows seeded description and hardware values', async ({
    authenticatedPage: page,
  }) => {
    await findDesktopRow(page, SEEDED.test.id)

    // Both AJAX calls fire when the detail panel opens.
    const detailsResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/domain/${SEEDED.test.id}/details`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    const hardwareResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/domain/hardware/${SEEDED.test.id}`) &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await expandRowDetail(page, SEEDED.test.id)

    expect((await detailsResponse).status()).toBeLessThan(400)
    expect((await hardwareResponse).status()).toBeLessThan(400)

    // Description comes from GET /details.
    // Seed value: testing/db/data/domains.json → description: "Base desktop".
    const descEl = page.locator(`#description-${SEEDED.test.id}`)
    await expect(descEl).toHaveText('Base desktop', { timeout: 8000 })

    // Hardware values come from GET /hardware.
    // Seed: vcpus=1, memory=524288 bytes (0.5 GB), disk_bus="default".
    const hwPanel = page.locator(`#hardware-${SEEDED.test.id}`)
    await expect(hwPanel.locator('#vcpu')).toHaveText('1 CPU(s)', { timeout: 8000 })
    await expect(hwPanel.locator('#ram')).toHaveText('0.50GB', { timeout: 8000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S24 — status filter (server-side indexed) sends param in POST /domains body
  // ──────────────────────────────────────────────────────────────────────────
  test('S24: status filter sends status param in POST /domains body and keeps Stopped rows visible', async ({
    authenticatedPage: page,
  }) => {
    await gotoDesktops(page)

    // #filter-select is a plain <select> (no Select2) — selectOption works directly.
    // Selecting triggers the change handler: newFilterBox('status') + populateSelect('status').
    await page.locator('#filter-select').selectOption('status')
    await page.locator('#filter-boxes #filter-status').waitFor({ state: 'visible', timeout: 8000 })

    // Set "Stopped" via jQuery — more reliable than UI interaction with Select2.
    await page.evaluate(() => {
      $('#status').val(['Stopped']).trigger('change')
    })

    // Search fires table.ajax.reload() for indexed filters.
    const searchResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/domains') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )

    await page.locator('#btn-search').click()

    const resp = await searchResponse
    expect(resp.status()).toBeLessThan(400)

    const body = JSON.parse((await resp.request().postData()) || '{}')
    expect(body.status, 'POST /domains body must include status filter').toBe('Stopped')

    // A seeded Stopped desktop must still be visible after the filtered reload.
    // Use SEEDED.gpu, not SEEDED.test: under serial mode the earlier edit tests
    // (S6/S15/S17/S19/S21) flip SEEDED.test to Failed (editing a diskless seed
    // triggers an engine XML rebuild that can't complete), so it no longer matches
    // the Stopped filter. SEEDED.gpu is only ever read (S2-GPU Cancel path), so it
    // stays Stopped for the whole run.
    await expect(waitForTableRow(page, SEEDED.gpu.id)).toBeVisible({ timeout: 10000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S25 — name filter (server-side) sends name param in POST /domains
  // ──────────────────────────────────────────────────────────────────────────
  test('S25: name filter sends name param in POST /domains body and shows only matching rows', async ({
    authenticatedPage: page,
  }) => {
    await gotoDesktops(page)

    await page.locator('#filter-select').selectOption('name')
    await page.locator('#filter-boxes #filter-name').waitFor({ state: 'visible', timeout: 8000 })

    // Name uses Select2 AJAX type-ahead — set the value programmatically to avoid
    // UI timing issues (clicking the container can hit adjacent navigation elements).
    await page.evaluate((name) => {
      var option = new Option(name, name, true, true)
      $('#name').append(option).trigger('change')
    }, SEEDED.test.name)

    const searchResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/domains') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )

    await page.locator('#btn-search').click()

    const resp = await searchResponse
    expect(resp.status()).toBeLessThan(400)

    const body = JSON.parse((await resp.request().postData()) || '{}')
    expect(body.name, 'POST /domains body must include name filter').toEqual(
      expect.arrayContaining([SEEDED.test.name]),
    )

    await expect(waitForTableRow(page, SEEDED.test.id)).toBeVisible({ timeout: 10000 })
    await expect(waitForTableRow(page, SEEDED.failed.id)).toBeHidden({ timeout: 10000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S26 — btn-clear removes all active filter boxes and restores their options
  // ──────────────────────────────────────────────────────────────────────────
  test('S26: btn-clear removes active filter boxes and restores their options to the dropdown', async ({
    authenticatedPage: page,
  }) => {
    await gotoDesktops(page)

    // Add two filter boxes so we verify bulk removal.
    await page.locator('#filter-select').selectOption('status')
    await page.locator('#filter-boxes #filter-status').waitFor({ state: 'visible', timeout: 8000 })

    await page.locator('#filter-select').selectOption('name')
    await page.locator('#filter-boxes #filter-name').waitFor({ state: 'visible', timeout: 8000 })

    // Once added, each option is removed from #filter-select.
    await expect(page.locator('#filter-select option[value="status"]')).not.toBeAttached()
    await expect(page.locator('#filter-select option[value="name"]')).not.toBeAttached()

    // Apply a column search directly so a non-matching row gets hidden.
    // removeFilter uses the `index` attr on the #name select (set to "name" by populateSelect)
    // to find and clear the matching DataTables column search.
    await page.evaluate(() => {
      const $nameSelect = $('#filter-name #name')
      if (!$nameSelect.find('option[value="e2e-sentinel"]').length) {
        $nameSelect.append(new Option('e2e-sentinel', 'e2e-sentinel', true, true))
      }
      $nameSelect.val(['e2e-sentinel'])
      // Apply column search directly — hides rows whose Name doesn't match the sentinel.
      domains_table.columns().every(function () {
        if ($(this.header()).text().trim().toLowerCase() === 'name') {
          this.search('(?:^e2e-sentinel$)', true, false).draw()
        }
      })
    })
    // A seeded row whose name is not "e2e-sentinel" must now be hidden.
    await expect(waitForTableRow(page, SEEDED.test.id)).toBeHidden({ timeout: 5000 })

    await page.locator('#btn-clear').click()

    // Both filter boxes must be removed from the DOM.
    await expect(page.locator('#filter-boxes #filter-status')).toBeHidden({ timeout: 5000 })
    await expect(page.locator('#filter-boxes #filter-name')).toBeHidden({ timeout: 5000 })

    // Their options must be restored to the dropdown.
    await expect(page.locator('#filter-select option[value="status"]')).toBeAttached({ timeout: 5000 })
    await expect(page.locator('#filter-select option[value="name"]')).toBeAttached({ timeout: 5000 })

    // The column search must have been cleared by removeFilter — previously hidden row must reappear.
    await expect(waitForTableRow(page, SEEDED.test.id)).toBeVisible({ timeout: 5000 })
  })

  // ──────────────────────────────────────────────────────────────────────────
  // S27 — btn-reload redraws the table without an API call and repopulates
  //       active filter options
  // ──────────────────────────────────────────────────────────────────────────
  test('S27: btn-reload redraws table without POST /domains and repopulates filter options', async ({
    authenticatedPage: page,
  }) => {
    await gotoDesktops(page)

    await page.locator('#filter-select').selectOption('status')
    await page.locator('#filter-boxes #filter-status').waitFor({ state: 'visible', timeout: 8000 })

    // Reload must not fire a new POST /domains (reloadOtherFiltersContent calls
    // table.draw(false) — client-side redraw only, no ajax.reload()).
    const unexpectedApiCall = page
      .waitForResponse(
        (r) =>
          r.url().includes('/api/v4/admin/items/domains') &&
          r.request().method() === 'POST',
        { timeout: 2000 },
      )
      .then(() => true)
      .catch(() => false)

    await page.locator('#btn-reload').click()

    expect(await unexpectedApiCall, 'btn-reload must not trigger POST /domains').toBe(false)

    // The filter box must still be present after reload.
    await expect(page.locator('#filter-boxes #filter-status')).toBeVisible({ timeout: 5000 })

    // After reload, populateSelect reruns and the status options must be present.
    await expect(
      page.locator('#filter-status #status option'),
    ).not.toHaveCount(0, { timeout: 5000 })
  })
})
