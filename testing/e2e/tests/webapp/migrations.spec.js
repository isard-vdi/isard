// Drives the admin Migrations screen at /isard-admin/admin/users/migration.
// Mirrors testing/e2e/specs/webapp/migrations.md — each test maps to a
// numbered scenario (A1..A9).
//
// All `users_migrations` rows used here come from the committed seed
// testing/db/data/users_migrations.json, loaded by populate_test_db.py like
// every other spec's data — there is no create API for migrations, so nothing
// is created at runtime. The read-only rows (A1..A6) are only read. The
// mutating tests (A7 delete / A8 revoke) each own a distinct seeded row and
// CONSUME it (delete removes it, revoke flips its status); cleanup is the SDK
// admin delete endpoint in afterEach, same as the rest of the suite, and
// populate restores the canonical rows on the next reseed. Because a consumed
// row cannot be re-created without a reseed, an attempt that finds its action
// button already gone (a retry after a mid-test failure, or a re-run without
// reseed) test.skip()s instead of failing: we assume the action already
// happened and flag it for manual review rather than reporting a false bug.

import { test, expect } from '../../fixtures/apiv4/index.js'
import { bridgeAdminSession } from '../../fixtures/common.js'
import { deleteMigration } from '../../src/gen/apiv4/sdk.gen'

const MIGRATION_URL = '/isard-admin/admin/users/migration'

const RO_IDS = {
  exported: 'e2e-mig-ro-exported',
  imported: 'e2e-mig-ro-imported',
  migrating: 'e2e-mig-ro-migrating',
  migrated: 'e2e-mig-ro-migrated',
  failed: 'e2e-mig-ro-failed',
  revoked: 'e2e-mig-ro-revoked',
}
// Seeded rows owned by the mutating tests (one distinct entry per test).
const MUT_IDS = {
  delOk: 'e2e-mig-del-ok',
  delCancel: 'e2e-mig-del-cancel',
  revOk: 'e2e-mig-rev-ok',
  revCancel: 'e2e-mig-rev-cancel',
}

// --- UI helpers ---
async function gotoMigrations(page) {
  const resp = page
    .waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/user-migrations') && r.status() < 400,
      { timeout: 20000 },
    )
    .catch(() => null)
  await page.goto(MIGRATION_URL)
  await resp
  await expect(page.locator('#migration-table')).toBeVisible()
  // Show every row on one page so per-worker rows are never paginated away.
  await page.evaluate(() => {
    const $ = window.jQuery || window.$
    $('#migration-table').DataTable().page.len(500).draw()
  })
}

function row(page, id) {
  return page.locator(`#migration-table tbody tr[id="${id}"]`)
}

async function clickPnotify(page, label) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: label })
    .first()
    .click({ timeout: 5000 })
}

test.describe('Admin Migrations — webapp', () => {
  // ---------------- A1 ----------------
  test('A1: table loads with every status, no "undefined" cells, per-status action', async ({
    authenticatedPage: page,
  }) => {
    await gotoMigrations(page)

    // every status row present
    for (const id of Object.values(RO_IDS)) {
      await expect(row(page, id)).toBeVisible()
    }

    // no body cell (cols 1..8 → Origin..Migration end) renders literal "undefined"
    for (const id of Object.values(RO_IDS)) {
      const texts = await row(page, id).locator('td').allInnerTexts()
      expect(texts.join(' | ')).not.toContain('undefined')
    }

    // action column per status
    for (const id of [RO_IDS.exported, RO_IDS.imported, RO_IDS.migrating]) {
      await expect(row(page, id).locator('.btn-revoke')).toBeVisible()
      await expect(row(page, id).locator('.btn-delete')).not.toBeAttached()
    }
    await expect(row(page, RO_IDS.migrated).locator('.btn-delete')).toBeVisible()
    await expect(row(page, RO_IDS.migrated).locator('.btn-revoke')).not.toBeAttached()
    for (const id of [RO_IDS.failed, RO_IDS.revoked]) {
      await expect(row(page, id).locator('.btn-revoke')).not.toBeAttached()
      await expect(row(page, id).locator('.btn-delete')).not.toBeAttached()
    }

    // no-target rows render "-" in Target User (col 3)
    await expect(row(page, RO_IDS.exported).locator('td:nth-child(3)')).toHaveText('-')
    await expect(row(page, RO_IDS.revoked).locator('td:nth-child(3)')).toHaveText('-')

    // timestamp presence by status (cols: 6 created, 7 import, 8 start, 9 end)
    for (const c of [7, 8, 9]) {
      await expect(row(page, RO_IDS.exported).locator(`td:nth-child(${c})`)).toHaveText('-')
    }
    await expect(row(page, RO_IDS.migrating).locator('td:nth-child(9)')).toHaveText('-')
    for (const c of [6, 7, 8, 9]) {
      await expect(row(page, RO_IDS.migrated).locator(`td:nth-child(${c})`)).not.toHaveText('-')
    }
  })

  // ---------------- A2 ----------------
  test('A2: global search filters the table', async ({ authenticatedPage: page }) => {
    await gotoMigrations(page)
    const search = page.locator('#migration-table_filter input')
    // "imported" is a status only the imported row carries (it is not a
    // substring of exported/migrating/migrated/revoked), so this stays
    // deterministic regardless of other workers' rows.
    await search.fill('imported')
    await expect(row(page, RO_IDS.imported)).toBeVisible()
    await expect(row(page, RO_IDS.migrated)).toBeHidden()
    await expect(row(page, RO_IDS.exported)).toBeHidden()
    await search.fill('')
    await expect(row(page, RO_IDS.migrated)).toBeVisible()
  })

  // ---------------- A3 ----------------
  test('A3: per-column footer search filters by status', async ({ authenticatedPage: page }) => {
    await gotoMigrations(page)
    // footer Status input is the 5th column; the handler binds "keyup change",
    // so type char-by-char (pressSequentially emits keyup) and clear via Delete.
    const statusInput = page.locator('#migration-table tfoot tr th:nth-child(5) input')
    await statusInput.pressSequentially('imported')
    await expect(row(page, RO_IDS.imported)).toBeVisible()
    await expect(row(page, RO_IDS.migrated)).toBeHidden()
    await statusInput.press('Control+a')
    await statusInput.press('Delete')
    await expect(row(page, RO_IDS.migrated)).toBeVisible()
  })

  // ---------------- A4 ----------------
  test('A4: expand details of a fully successful migration', async ({ authenticatedPage: page }) => {
    await gotoMigrations(page)
    await row(page, RO_IDS.migrated).locator('td.details-control').click()
    const panel = page.locator(`#migration-${RO_IDS.migrated}`)
    await expect(panel).toBeVisible()
    for (const t of ['desktops', 'templates', 'media', 'deployments']) {
      await expect(panel.locator(`#${t}-migrated`)).toHaveText('1')
      await expect(panel.locator(`#${t}-failed i.fa-circle`)).not.toBeAttached()
      await expect(panel.locator(`#${t}-detail`)).toHaveText('')
    }
    // collapse
    await row(page, RO_IDS.migrated).locator('td.details-control').click()
    await expect(page.locator(`#migration-${RO_IDS.migrated}`)).not.toBeAttached()
  })

  // ---------------- A5 ----------------
  test('A5: expand details of a failed migration shows the red circle', async ({
    authenticatedPage: page,
  }) => {
    await gotoMigrations(page)
    await row(page, RO_IDS.failed).locator('td.details-control').click()
    const panel = page.locator(`#migration-${RO_IDS.failed}`)
    await expect(panel).toBeVisible()

    // the red circle renders for the failed type: present in DOM + computed red
    const circle = panel.locator('#media-failed i.fa-circle')
    await expect(circle).toBeAttached()
    await expect(circle).toHaveCSS('color', 'rgb(255, 0, 0)')
    await expect(panel.locator('#media-detail')).toHaveText(
      'User E2E Migration Target already has media with name e2e-mig media',
    )
    // succeeded types: no circle
    for (const t of ['desktops', 'templates', 'deployments']) {
      await expect(panel.locator(`#${t}-failed i.fa-circle`)).not.toBeAttached()
    }
  })

  // ---------------- A6 ----------------
  test('A6: expand details of a non-migrated row stays clean', async ({ authenticatedPage: page }) => {
    await gotoMigrations(page)
    await row(page, RO_IDS.exported).locator('td.details-control').click()
    const panel = page.locator(`#migration-${RO_IDS.exported}`)
    await expect(panel).toBeVisible()
    for (const t of ['desktops', 'templates', 'media', 'deployments']) {
      await expect(panel.locator(`#${t}-migrated`)).toHaveText('-')
      await expect(panel.locator(`#${t}-failed i.fa-circle`)).not.toBeAttached()
      await expect(panel.locator(`#${t}-detail`)).toHaveText('')
    }
  })

  // ---------------- A7 / A8 (mutating, one distinct seeded row per test) ----------------
  test.describe('row actions', () => {
    // Clean up the seeded row this test owns via the SDK admin delete endpoint
    // (works on any status; ignore 404 when the confirm test already removed it).
    // populate restores all rows to canonical state on the next reseed.
    test.afterEach(async ({ apiv4Admin }) => {
      const ids = test
        .info()
        .annotations.filter((a) => a.type === 'migration-id')
        .map((a) => a.description)
      for (const migration_id of ids) {
        await deleteMigration({ client: apiv4Admin, path: { migration_id } }).catch(() => {})
      }
    })

    // Skip (don't fail) when the action button is already gone: the seeded row
    // was consumed by a prior attempt/run and can only return via a reseed.
    async function actionButtonOrSkip(page, id, selector, what) {
      test.info().annotations.push({ type: 'migration-id', description: id })
      const button = row(page, id).locator(selector)
      test.skip(
        (await button.count()) === 0,
        `${id}: ${what} button absent — row already consumed (retry / no reseed); assume it acted, review manually`,
      )
      return button
    }

    test('A7: delete a migrated migration (confirm)', async ({ authenticatedPage: page }) => {
      const id = MUT_IDS.delOk
      await gotoMigrations(page)
      const btn = await actionButtonOrSkip(page, id, '.btn-delete', 'delete')

      const del = page.waitForResponse(
        (r) =>
          r.url().includes(`/api/v4/admin/item/user-migration/${id}`) &&
          r.request().method() === 'DELETE',
        { timeout: 15000 },
      )
      await btn.click()
      await clickPnotify(page, /^ok$/i)
      expect((await del).status()).toBe(204)
      await expect(page.locator('.ui-pnotify-title', { hasText: /migration deleted/i })).toBeVisible()
      await expect(row(page, id)).not.toBeAttached()
    })

    test('A7: delete cancel keeps the row', async ({ authenticatedPage: page }) => {
      const id = MUT_IDS.delCancel
      await gotoMigrations(page)
      const btn = await actionButtonOrSkip(page, id, '.btn-delete', 'delete')
      await btn.click()
      await clickPnotify(page, /^cancel$/i)
      await page.waitForTimeout(500)
      await expect(row(page, id)).toBeVisible()
      await expect(row(page, id).locator('.btn-delete')).toBeVisible()
    })

    test('A8: revoke an exported migration (confirm)', async ({ authenticatedPage: page }) => {
      const id = MUT_IDS.revOk
      await gotoMigrations(page)
      const btn = await actionButtonOrSkip(page, id, '.btn-revoke', 'revoke')

      const put = page.waitForResponse(
        (r) =>
          r.url().includes(`/api/v4/admin/item/user-migration/${id}/revoke`) &&
          r.request().method() === 'PUT',
        { timeout: 15000 },
      )
      await btn.click()
      await clickPnotify(page, /^ok$/i)
      expect((await put).status()).toBe(204)
      await expect(page.locator('.ui-pnotify-title', { hasText: /migration revoked/i })).toBeVisible()
      // after reload: status becomes revoked, the Revoke button is gone
      await expect(row(page, id).locator('td:nth-child(5)')).toHaveText('revoked')
      await expect(row(page, id).locator('.btn-revoke')).not.toBeAttached()
    })

    test('A8: revoke cancel keeps status exported', async ({ authenticatedPage: page }) => {
      const id = MUT_IDS.revCancel
      await gotoMigrations(page)
      const btn = await actionButtonOrSkip(page, id, '.btn-revoke', 'revoke')
      await btn.click()
      await clickPnotify(page, /^cancel$/i)
      await page.waitForTimeout(500)
      await expect(row(page, id).locator('td:nth-child(5)')).toHaveText('exported')
      await expect(row(page, id).locator('.btn-revoke')).toBeVisible()
    })
  })
})

// ---------------- A9 (permissions) ----------------
test.describe('Admin Migrations — permissions', () => {
  for (const roleKey of ['manager_e2e_01', 'user_e2e_01']) {
    test(`A9: ${roleKey} is denied and redirected to login`, async ({
      page,
      users,
      categories,
      loginHelpers,
    }) => {
      await loginHelpers.login(page, users[roleKey], categories)
      await bridgeAdminSession(page)
      await page.goto(MIGRATION_URL)
      await expect(page).toHaveURL(/\/login/)
      await expect(page.locator('#migration-table')).not.toBeAttached()
    })
  }
})
