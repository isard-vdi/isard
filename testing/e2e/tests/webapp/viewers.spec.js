import { test, expect, unwrap } from '../../fixtures/apiv4/index.js'
import {
  adminViewersConfig,
  adminViewersConfigUpdate,
} from '../../src/gen/apiv4/sdk.gen'

const VIEWERS_URL = '/isard-admin/admin/viewers'

async function getViewersConfig(client) {
  const data = await unwrap(adminViewersConfig({ client })).catch(() => [])
  return Array.isArray(data) ? data : []
}

async function gotoViewers(page) {
  await page.goto(VIEWERS_URL)
  await page
    .locator('#viewers-conf-table ~ .dataTables_wrapper, .dataTables_wrapper:has(#viewers-conf-table)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
  await page
    .locator('#viewers-conf-table tbody tr:not(.dataTables_empty)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
}

async function rowByKey(page, key) {
  return page.locator(`#viewers-conf-table tbody tr:has(button#btn-edit[data-id="${key}"])`).first()
}

async function clickPnotifyOk(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^ok$/i })
    .first()
    .click({ timeout: 5000 })
}

test.describe('Config — Viewers (admin webapp)', () => {
  test('A1: initial load of Viewers page', async ({ authenticatedPage: page }) => {
    const getResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/items/viewers-config') && r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await gotoViewers(page)

    expect((await getResp).status()).toBeLessThan(400)
    await expect(page.locator('#viewers-conf-table')).toBeVisible()
    await expect(page.locator('#viewers-conf-table thead')).toContainText(/viewer/i)
  })

  test('A2: edit viewer custom options', async ({ authenticatedPage: page, apiv4Admin }) => {
    const viewers = await getViewersConfig(apiv4Admin)
    test.skip(viewers.length === 0, 'no viewers config rows available')

    const target = viewers[0]
    const original = target.custom ?? ''
    const updated = `${original}\n# e2e ${Date.now()}`

    try {
      await gotoViewers(page)
      const row = await rowByKey(page, target.key)
      await expect(row).toBeVisible({ timeout: 10000 })

      await row.locator('button#btn-edit').click()
      const modal = page.locator('#modalEditViewersConfig')
      await modal.waitFor({ state: 'visible', timeout: 10000 })

      await modal.locator('#custom').fill(updated)

      const putResp = page.waitForResponse(
        (r) =>
          r.url().includes(`/api/v4/admin/item/viewers-config/${target.key}`) &&
          r.request().method() === 'PUT',
        { timeout: 15000 },
      )
      const reloadResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/items/viewers-config') && r.request().method() === 'GET',
        { timeout: 15000 },
      )
      await modal.locator('#send').click()

      expect((await putResp).status()).toBeLessThan(400)
      expect((await reloadResp).status()).toBeLessThan(400)
      await modal.waitFor({ state: 'hidden', timeout: 10000 })

      const after = await getViewersConfig(apiv4Admin)
      const persisted = after.find((v) => v.key === target.key)
      expect(persisted?.custom ?? '').toBe(updated)
    } finally {
      await adminViewersConfigUpdate({
        client: apiv4Admin,
        path: { viewer: target.key },
        body: { custom: original },
      }).catch(() => {})
    }
  })

  test('A3: reset (delete) viewer custom options', async ({ authenticatedPage: page, apiv4Admin }) => {
    const viewers = await getViewersConfig(apiv4Admin)
    test.skip(viewers.length === 0, 'no viewers config rows available')

    const target = viewers[0]
    const original = target.custom ?? ''
    const expectedAfterReset = target.default ?? ''
    const seeded = `e2e-reset-${Date.now()}`

    try {
      await adminViewersConfigUpdate({
        client: apiv4Admin,
        path: { viewer: target.key },
        body: { custom: seeded },
      })

      await gotoViewers(page)
      const row = await rowByKey(page, target.key)
      await expect(row).toBeVisible({ timeout: 10000 })

      await row.locator('button#btn-reset').click()

      const resetResp = page.waitForResponse(
        (r) =>
          r.url().includes(`/api/v4/admin/item/viewers-config/reset/${target.key}`) &&
          r.request().method() === 'PUT',
        { timeout: 15000 },
      )
      const reloadResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/items/viewers-config') && r.request().method() === 'GET',
        { timeout: 15000 },
      )
      await clickPnotifyOk(page)

      expect((await resetResp).status()).toBeLessThan(400)
      expect((await reloadResp).status()).toBeLessThan(400)

      // Persistence check: source of truth is backend config (DB-backed API).
      await expect
        .poll(async () => {
          const latest = await getViewersConfig(apiv4Admin)
          const row = latest.find((v) => v.key === target.key)
          return row?.custom ?? null
        }, { timeout: 15000 })
        .toBe(expectedAfterReset)

      const after = await getViewersConfig(apiv4Admin)
      const persisted = after.find((v) => v.key === target.key)
      expect(persisted?.custom ?? '').toBe(expectedAfterReset)
      expect(persisted?.custom ?? '').not.toBe(seeded)
    } finally {
      // Restore previous user state, not the reset one.
      await adminViewersConfigUpdate({
        client: apiv4Admin,
        path: { viewer: target.key },
        body: { custom: original },
      }).catch(() => {})
    }
  })
})
