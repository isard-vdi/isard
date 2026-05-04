// @ts-check
//
// Regression for round-2 Bug #17 — recycle-bin restore creates a
// ghost row in the all-entries view.
//
// Bug #17 was filed twice: the first instance (per-user view) was
// fixed in commit 84b99c1ff. Naomi confirmed the *all-entries view*
// (RecycleBins.vue, /recycleBins route) still produces a ghost row
// after restore — the websocket fan-out emits the "restored" event
// to the all-entries listener which interprets it as "added" and
// keeps the now-restored row visible until manual page refresh.
//
// Spec:
//   1. Admin (via API) creates a desktop, then sends it to the
//      recycle bin via DELETE /item/desktop/{id} (non-permanent).
//   2. UI: navigate to /recycleBins (all-entries view).
//   3. Find the row corresponding to the recycled desktop, capture
//      the row count before restore.
//   4. Click the restore button on that row.
//   5. Wait for the snotify "restored" toast to clear.
//   6. Assert: row count is exactly count - 1 (the restored row is
//      gone). Bug #17's signature is count stays the same OR
//      increases (ghost row remains AND a new "restored" event
//      adds a duplicate).
//   7. afterAll: permanent-delete the desktop if it survived.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { test as loginTest } from './api-fixture'

loginTest.describe.configure({ mode: 'serial' })

loginTest.describe('Bug #17 regression — recycle-bin restore in all-entries view', () => {
  /** @type {string} */
  let desktopId
  /** @type {string} */
  let recycleBinId
  /** @type {string} */
  let desktopName

  loginTest.beforeAll(async ({ baseURL }) => {
    loginTest.setTimeout(120000)
    const seed = new ApiHelper(baseURL ?? 'https://localhost')
    await seed.login()

    const templates = await seed.getTemplates()
    const tpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!tpl) {
      loginTest.skip(true, 'no Stopped+enabled template seeded')
      return
    }

    const ts = Date.now()
    desktopName = `bug17-${ts}`
    const dsk = await seed.createDesktop(desktopName, tpl.id)
    desktopId = dsk.id

    // Wait for the desktop to reach Stopped before we delete it —
    // some delete flows reject Creating-state rows.
    try {
      await seed.waitForDomainStatus(desktopId, 'Stopped', 60000)
    } catch (e) {
      console.warn(`desktop ${desktopId} did not reach Stopped: ${e.message}`)
    }

    // Send to recycle bin via non-permanent DELETE.
    await seed._authFetch('DELETE', `/api/v4/item/desktop/${desktopId}`)

    // Find the recycle-bin entry id matching our desktop. The
    // listing endpoint depends on user role; admin sees all.
    const entries = await seed._authFetch('GET', '/api/v4/items/recycle-bin/all')
    const entry = (Array.isArray(entries) ? entries : []).find((e) =>
      JSON.stringify(e).includes(desktopName)
    )
    if (entry) recycleBinId = entry.id
  })

  loginTest.afterAll(async ({ baseURL }) => {
    if (!recycleBinId && !desktopId) return
    const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
    await cleanup.login()
    if (recycleBinId) {
      // Best-effort: empty the recycle bin entry permanently to
      // clean up.
      try {
        await cleanup._authFetch('DELETE', `/api/v4/item/recycle-bin/${recycleBinId}`)
      } catch (e) { /* already gone */ }
    }
    if (desktopId) {
      try {
        await cleanup._authFetch('DELETE', `/api/v4/item/desktop/${desktopId}?permanent=true`)
      } catch (e) { /* already gone */ }
    }
  })

  loginTest('restore from /recycleBins all-entries view does not leave a ghost row', async ({
    page,
    login
  }) => {
    loginTest.skip(!recycleBinId, 'beforeAll did not seed a recycle-bin entry')

    await page.goto('/recycleBins')
    await page.waitForLoadState('networkidle')

    // Pre-restore row count. The /recycleBins listing renders rows
    // as ``<tr>`` inside a ``<table>`` (BootstrapVue b-table). Each
    // entry row has the desktop name visible.
    const rowsBefore = await page.locator('table tbody tr').count()
    expect(rowsBefore, 'should have at least one recycle-bin entry').toBeGreaterThan(0)

    // Find the row containing our desktop name.
    const ourRow = page.getByRole('row', { name: new RegExp(desktopName) })
    await expect(ourRow).toBeVisible({ timeout: 10000 })

    // Click the restore button on the row. The button has icon
    // class or title "restore".
    const restoreBtn = ourRow.getByTitle(/restore/i).first()
    if (!(await restoreBtn.isVisible().catch(() => false))) {
      // Fallback: any button with a class containing 'green' (the
      // restore styling) on the row.
      await ourRow.locator('button.btn-green, button.btn-success').first().click()
    } else {
      await restoreBtn.click()
    }

    // Many list views use snotify for confirm prompts before
    // dispatching the actual API call. Click "Yes" if a confirm
    // dialog appears.
    const confirmYes = page.getByRole('button', { name: /^yes$|^ok$|^confirm$|^restore$/i }).first()
    if (await confirmYes.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmYes.click()
    }

    // Wait for the snotify "restored" toast to clear (the store
    // action issues PUT /restore then clears snotify on 200).
    await page.waitForTimeout(2500)

    // Assertion: the restored row should be GONE from the table.
    // Bug #17's signature is the row staying (or duplicating) until
    // a manual page refresh.
    const rowsAfter = await page.locator('table tbody tr').count()
    expect(
      rowsAfter,
      `Bug #17 regression: /recycleBins all-entries had ${rowsBefore} rows, ` +
        `expected ${rowsBefore - 1} after restore, got ${rowsAfter}. ` +
        'Ghost row signature: rowsAfter >= rowsBefore.'
    ).toBeLessThan(rowsBefore)

    // Sanity: the specific row for our desktop should be gone too.
    await expect(ourRow).not.toBeVisible({ timeout: 5000 })
  })
})
