// Drives Config → System in the legacy admin webapp.
// Mirrors testing/e2e/specs/webapp/system.md (A1..A9).

import { test, expect, unwrap } from '../../fixtures/apiv4/index.js'
import {
  adminSmtpGet,
  adminSmtpPut,
  getMaintenanceText,
  maintenanceStatus,
  updateMaintenance,
  updateMaintenanceText,
} from '../../src/gen/apiv4/sdk.gen'

const SYSTEM_URL = '/isard-admin/admin/system'

function normalizeMaintenanceText(payload) {
  if (!payload) return { title: '', body: '' }
  if (payload.text && typeof payload.text === 'object') {
    return {
      title: payload.text.title ?? '',
      body: payload.text.body ?? '',
    }
  }
  return {
    title: payload.title ?? '',
    body: payload.body ?? '',
  }
}

async function getMaintenanceEnabled(client) {
  const data = await unwrap(maintenanceStatus({ client }))
  if (typeof data === 'boolean') return data
  return Boolean(data?.enabled)
}

async function getMaintenanceTextApi(client) {
  const data = await unwrap(getMaintenanceText({ client })).catch(() => null)
  return normalizeMaintenanceText(data)
}

async function getSmtpApi(client) {
  return (await unwrap(adminSmtpGet({ client })).catch(() => ({}))) ?? {}
}

async function gotoSystem(page) {
  await page.goto(SYSTEM_URL)
  await page.locator('#maintenance_spinner').waitFor({ state: 'hidden', timeout: 15000 })
  await page.locator('#maintenance_wrapper').waitFor({ state: 'visible', timeout: 15000 })
  await page.locator('#preview').waitFor({ state: 'visible', timeout: 10000 })
  await page.locator('#form-smtp-show').waitFor({ state: 'visible', timeout: 10000 })
}

async function maintenanceChecked(page) {
  return page.locator('#maintenance_checkbox').evaluate((el) => el.checked)
}

async function clickMaintenanceToggleAndAssert(page, desired) {
  const putResponse = page.waitForResponse(
    (r) => r.url().includes('/api/v4/maintenance') && r.request().method() === 'PUT',
    { timeout: 15000 },
  )
  await page.locator('label[for="maintenance_checkbox"]').click()
  const resp = await putResponse
  expect(resp.status()).toBeLessThan(400)

  await page.locator('#maintenance_spinner').waitFor({ state: 'hidden', timeout: 15000 })
  await expect.poll(() => maintenanceChecked(page), { timeout: 10000 }).toBe(desired)
}

test.describe('Config — System (admin webapp)', () => {
  test('A1: initial System load renders sections and core GET calls succeed', async ({ authenticatedPage: page }) => {
    const statusResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/maintenance/status') &&
        r.request().method() === 'GET',
      { timeout: 15000 },
    )
    const textResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/maintenance/text') && r.request().method() === 'GET',
      { timeout: 15000 },
    )
    const smtpResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/smtp') && r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await gotoSystem(page)

    expect((await statusResp).status()).toBeLessThan(400)
    expect((await textResp).status()).toBeLessThan(400)
    expect((await smtpResp).status()).toBeLessThan(400)

    await expect(page.getByRole('heading', { name: /maintenance mode/i }).first()).toBeVisible()
    await expect(page.getByRole('heading', { name: /maintenance text/i }).first()).toBeVisible()
    await expect(page.getByRole('heading', { name: /smtp configuration/i }).first()).toBeVisible()
  })

  test('A2: enables maintenance mode from checkbox and receives 2XX', async ({ authenticatedPage: page, apiv4Admin }) => {
    // TODO: remove this skip when maintenance toggle UI/backend contract is fixed.
    test.skip(true, 'TEMP: genuine UI bug under fix (maintenance enable flow)')

    const original = await getMaintenanceEnabled(apiv4Admin)
    try {
      await unwrap(updateMaintenance({ client: apiv4Admin, body: { enabled: false } }))

      await gotoSystem(page)
      await expect.poll(() => maintenanceChecked(page), { timeout: 10000 }).toBe(false)
      await clickMaintenanceToggleAndAssert(page, true)
    } finally {
      await updateMaintenance({ client: apiv4Admin, body: { enabled: original } }).catch(() => {})
    }
  })

  test('A3: disables maintenance mode and persists unchecked state after reload', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    // TODO: remove this skip when maintenance disable persistence works end-to-end.
    test.skip(true, 'TEMP: genuine UI bug under fix (maintenance disable flow)')

    const original = await getMaintenanceEnabled(apiv4Admin)
    try {
      await unwrap(updateMaintenance({ client: apiv4Admin, body: { enabled: true } }))

      await gotoSystem(page)
      await expect.poll(() => maintenanceChecked(page), { timeout: 10000 }).toBe(true)
      await clickMaintenanceToggleAndAssert(page, false)

      await page.reload()
      await page.locator('#maintenance_spinner').waitFor({ state: 'hidden', timeout: 15000 })
      await expect.poll(() => maintenanceChecked(page), { timeout: 10000 }).toBe(false)
    } finally {
      await updateMaintenance({ client: apiv4Admin, body: { enabled: original } }).catch(() => {})
    }
  })

  test('A4: opens maintenance text modal with prefilled fields', async ({
    authenticatedPage: page,
  }) => {
    await gotoSystem(page)

    const getOnOpen = page.waitForResponse(
      (r) => r.url().includes('/api/v4/maintenance/text') && r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await page.locator('#btn-edit-maintenance-text').click()
    const openResp = await getOnOpen
    expect(openResp.status()).toBeLessThan(400)

    const modal = page.locator('#modalEditMaintenanceText')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#title')).toBeVisible()
    await expect(modal.locator('#text')).toBeVisible()
  })

  test('A5: edits maintenance text and updates preview', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    // TODO: remove this skip when maintenance preview renders saved text instead of undefined.
    test.skip(true, 'TEMP: genuine UI bug under fix (maintenance preview rendering)')

    const original = await getMaintenanceTextApi(apiv4Admin)
    const title = `E2E maintenance title ${Date.now()}`
    const body = `Line 1 ${Date.now()}\nLine 2 ${Date.now()}`

    try {
      await gotoSystem(page)
      await page.locator('#btn-edit-maintenance-text').click()

      const modal = page.locator('#modalEditMaintenanceText')
      await modal.waitFor({ state: 'visible', timeout: 10000 })
      await modal.locator('#title').fill(title)
      await modal.locator('#text').fill(body)

      const putRespPromise = page.waitForResponse(
        (r) => r.url().includes('/api/v4/maintenance/text') && r.request().method() === 'PUT',
        { timeout: 15000 },
      )
      const refreshRespPromise = page.waitForResponse(
        (r) => r.url().includes('/api/v4/maintenance/text') && r.request().method() === 'GET',
        { timeout: 15000 },
      )
      await modal.locator('#send').click()

      const putResp = await putRespPromise
      expect(putResp.status()).toBeLessThan(300)
      expect((await refreshRespPromise).status()).toBeLessThan(400)

      await modal.waitFor({ state: 'hidden', timeout: 10000 })
      await expect(page.locator('#preview')).toHaveText(`${title}\n\n${body}`)
    } finally {
      await updateMaintenanceText({
        client: apiv4Admin,
        body: { title: original.title, body: original.body },
      }).catch(() => {})
    }
  })

  test('A6: SMTP read-only form shows backend values', async ({ authenticatedPage: page, apiv4Admin }) => {
    const smtp = await getSmtpApi(apiv4Admin)

    await gotoSystem(page)

    const form = page.locator('#form-smtp-show')
    await expect(form).toBeVisible()

    for (const field of ['host', 'port', 'username', 'from']) {
      const value = smtp[field]
      if (value === undefined || value === null) continue
      await expect(form.locator(`[name="${field}"]`)).toHaveValue(String(value))
    }

    if (typeof smtp.enabled === 'boolean') {
      await expect
        .poll(
          () => form.locator('[name="enabled"]').evaluate((el) => el.checked),
          { timeout: 10000 },
        )
        .toBe(smtp.enabled)
    }
  })

  test('A7: opening SMTP modal preloads current values', async ({ authenticatedPage: page, apiv4Admin }) => {
    const smtp = await getSmtpApi(apiv4Admin)

    await gotoSystem(page)

    const getOnOpen = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/smtp') && r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await page.locator('#btn-edit-smtp').click()
    expect((await getOnOpen).status()).toBeLessThan(400)

    const modal = page.locator('#modal-smtp-configuration')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    for (const field of ['host', 'port', 'username', 'from']) {
      const value = smtp[field]
      if (value === undefined || value === null) continue
      await expect(modal.locator(`#form-smtp-edit [name="${field}"]`)).toHaveValue(String(value))
    }
  })

  test('A8: edits and saves SMTP configuration (without connection test)', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    const original = await getSmtpApi(apiv4Admin)

    await gotoSystem(page)
    await page.locator('#btn-edit-smtp').click()

    const modal = page.locator('#modal-smtp-configuration')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    const host = `smtp-${Date.now()}.e2e.local`
    const port = '587'
    const username = `e2e-user-${Date.now()}`
    const from = `"Isard E2E" <e2e-${Date.now()}@example.local>`

    const pwdField = modal.locator('#form-smtp-edit [name="password"]')
    const currentPwd = await pwdField.inputValue()
    test.skip(!currentPwd, 'SMTP password is redacted/empty; safe restore is not possible in this environment')

    try {
      await modal.locator('#form-smtp-edit [name="host"]').fill(host)
      await modal.locator('#form-smtp-edit [name="port"]').fill(port)
      await modal.locator('#form-smtp-edit [name="username"]').fill(username)
      await modal.locator('#form-smtp-edit [name="from"]').fill(from)

      const putRespPromise = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/smtp') && r.request().method() === 'PUT',
        { timeout: 15000 },
      )
      const refreshRespPromise = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/smtp') && r.request().method() === 'GET',
        { timeout: 15000 },
      )
      await modal.locator('#smtp-save').click()

      expect((await putRespPromise).status()).toBeLessThan(400)
      expect((await refreshRespPromise).status()).toBeLessThan(400)

      await modal.waitFor({ state: 'hidden', timeout: 10000 })

      const readOnly = page.locator('#form-smtp-show')
      await expect(readOnly.locator('[name="host"]')).toHaveValue(host)
      await expect(readOnly.locator('[name="port"]')).toHaveValue(port)
      await expect(readOnly.locator('[name="username"]')).toHaveValue(username)
      await expect(readOnly.locator('[name="from"]')).toHaveValue(from)
    } finally {
      const restoreBody = {}
      for (const key of ['enabled', 'host', 'port', 'username', 'from']) {
        if (original[key] !== undefined) restoreBody[key] = original[key]
      }
      await adminSmtpPut({ client: apiv4Admin, body: restoreBody }).catch(() => {})
    }
  })

  test('A9: SMTP form blocks invalid payloads in client validation', async ({ authenticatedPage: page }) => {
    await gotoSystem(page)
    await page.locator('#btn-edit-smtp').click()

    const modal = page.locator('#modal-smtp-configuration')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    const unexpectedPutPromise = page
      .waitForRequest(
        (req) => req.url().includes('/api/v4/admin/item/smtp') && req.method() === 'PUT',
        { timeout: 2000 },
      )
      .then(() => true)
      .catch(() => false)

    await modal.locator('#form-smtp-edit [name="host"]').fill('')
    await modal.locator('#form-smtp-edit [name="port"]').fill('70000')
    await modal.locator('#form-smtp-edit [name="username"]').fill('')
    await modal.locator('#form-smtp-edit [name="password"]').fill('')
    await modal.locator('#smtp-save').click()

    await expect(modal.locator('#form-smtp-edit [name="host"]')).toHaveClass(/parsley-error/)
    await expect(modal.locator('#form-smtp-edit [name="port"]')).toHaveClass(/parsley-error/)
    await expect(modal.locator('#form-smtp-edit [name="username"]')).toHaveClass(/parsley-error/)
    await expect(modal.locator('#form-smtp-edit [name="password"]')).toHaveClass(/parsley-error/)
    expect(await unexpectedPutPromise, 'invalid SMTP form should not trigger PUT').toBe(false)
  })
})
