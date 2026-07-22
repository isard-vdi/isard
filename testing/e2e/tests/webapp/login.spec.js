import { test, expect, unwrap } from '../../fixtures/apiv4/index.js'
import {
  adminLoginConfigGet,
  adminLoginNotificationCoverEnable,
  adminLoginNotificationFormEnable,
  adminLoginNotificationUpdate,
} from '../../src/gen/apiv4/sdk.gen'

const LOGIN_URL = '/isard-admin/admin/login'

async function getLoginConfig(client) {
  return (await unwrap(adminLoginConfigGet({ client })).catch(() => ({}))) ?? {}
}

function toUpdateBody(cfg) {
  const cover = cfg.notification_cover ?? {}
  const form = cfg.notification_form ?? {}
  return {
    cover: {
      icon: cover.icon ?? '',
      title: cover.title ?? '',
      description: cover.description ?? '',
      extra_styles: cover.extra_styles ?? 'background-color: #FFFFFF;',
      button: {
        text: cover.button?.text ?? '',
        url: cover.button?.url ?? '',
        extra_styles: cover.button?.extra_styles ?? 'color: #114955;',
      },
    },
    form: {
      icon: form.icon ?? '',
      title: form.title ?? '',
      description: form.description ?? '',
      extra_styles: form.extra_styles ?? 'background-color: #FFFFFF;',
      button: {
        text: form.button?.text ?? '',
        url: form.button?.url ?? '',
        extra_styles: form.button?.extra_styles ?? 'color: #114955;',
      },
    },
  }
}

async function gotoLoginConfig(page) {
  await page.goto(LOGIN_URL)
  await page.locator('#LoginNotificationsPanel').waitFor({ state: 'visible', timeout: 15000 })
  await page.locator('#preview-panel').waitFor({ state: 'visible', timeout: 15000 })
}

async function checkboxChecked(page, selector) {
  return page.locator(selector).evaluate((el) => el.checked)
}

test.describe('Config — Login (admin webapp)', () => {
  test('A1: initial load of Login config page', async ({ authenticatedPage: page }) => {
    const getResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/login-config') && r.request().method() === 'GET',
      { timeout: 15000 },
    )

    await gotoLoginConfig(page)

    expect((await getResp).status()).toBeLessThan(400)
    await expect(page.locator('#enable_cover_notification_wrapper')).toBeVisible()
    await expect(page.locator('#enable_form_notification_wrapper')).toBeVisible()
  })

  test('A2: enable/disable left notification', async ({ authenticatedPage: page, apiv4Admin }) => {
    const original = await getLoginConfig(apiv4Admin)
    const originalEnabled = Boolean(original.notification_cover?.enabled)

    try {
      await gotoLoginConfig(page)
      const desired = !originalEnabled

      const putResp = page.waitForResponse(
        (r) =>
          r.url().includes('/api/v4/admin/item/login_config/notification/cover/enable') &&
          r.request().method() === 'PUT',
        { timeout: 15000 },
      )
      const refreshResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/login-config') && r.request().method() === 'GET',
        { timeout: 15000 },
      )

      await page.locator('label[for="enable_cover_notification_checkbox"]').click()

      expect((await putResp).status()).toBeLessThan(400)
      expect((await refreshResp).status()).toBeLessThan(400)
      await expect.poll(() => checkboxChecked(page, '#enable_cover_notification_checkbox')).toBe(desired)

      const persisted = await getLoginConfig(apiv4Admin)
      expect(Boolean(persisted.notification_cover?.enabled)).toBe(desired)
    } finally {
      await adminLoginNotificationCoverEnable({
        client: apiv4Admin,
        body: { enabled: originalEnabled },
      }).catch(() => {})
    }
  })

  test('A3: enable/disable right notification', async ({ authenticatedPage: page, apiv4Admin }) => {
    const original = await getLoginConfig(apiv4Admin)
    const originalEnabled = Boolean(original.notification_form?.enabled)

    try {
      await gotoLoginConfig(page)
      const desired = !originalEnabled

      const putResp = page.waitForResponse(
        (r) =>
          r.url().includes('/api/v4/admin/item/login_config/notification/form/enable') &&
          r.request().method() === 'PUT',
        { timeout: 15000 },
      )
      const refreshResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/login-config') && r.request().method() === 'GET',
        { timeout: 15000 },
      )

      await page.locator('label[for="enable_form_notification_checkbox"]').click()

      expect((await putResp).status()).toBeLessThan(400)
      expect((await refreshResp).status()).toBeLessThan(400)
      await expect.poll(() => checkboxChecked(page, '#enable_form_notification_checkbox')).toBe(desired)

      const persisted = await getLoginConfig(apiv4Admin)
      expect(Boolean(persisted.notification_form?.enabled)).toBe(desired)
    } finally {
      await adminLoginNotificationFormEnable({
        client: apiv4Admin,
        body: { enabled: originalEnabled },
      }).catch(() => {})
    }
  })

  test('A4: open edit modal with prefilled data', async ({ authenticatedPage: page, apiv4Admin }) => {
    const cfg = await getLoginConfig(apiv4Admin)

    await gotoLoginConfig(page)

    const getResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/login-config') && r.request().method() === 'GET',
      { timeout: 15000 },
    )
    await page.locator('#btnEditLoginNotification').click()
    expect((await getResp).status()).toBeLessThan(400)

    const modal = page.locator('#modalEditLoginNotification')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#cover_title')).toHaveValue(cfg.notification_cover?.title ?? '')
    await expect(modal.locator('#form_title')).toHaveValue(cfg.notification_form?.title ?? '')
  })

  test('A5: edit login notifications and save', async ({ authenticatedPage: page, apiv4Admin }) => {
    const original = await getLoginConfig(apiv4Admin)

    const coverTitle = `E2E cover title ${Date.now()}`
    const formTitle = `E2E form title ${Date.now()}`

    try {
      await gotoLoginConfig(page)
      await page.locator('#btnEditLoginNotification').click()

      const modal = page.locator('#modalEditLoginNotification')
      await modal.waitFor({ state: 'visible', timeout: 10000 })

      await modal.locator('#cover_title').fill(coverTitle)
      await modal.locator('#form_title').fill(formTitle)

      const putResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/login_config/notification') && r.request().method() === 'PUT',
        { timeout: 15000 },
      )
      const refreshResp = page.waitForResponse(
        (r) => r.url().includes('/api/v4/admin/item/login-config') && r.request().method() === 'GET',
        { timeout: 15000 },
      )
      await modal.locator('#send').click()

      expect((await putResp).status()).toBeLessThan(400)
      expect((await refreshResp).status()).toBeLessThan(400)
      await modal.waitFor({ state: 'hidden', timeout: 10000 })

      await expect(page.locator('#preview_cover_title')).toContainText(coverTitle)
      await expect(page.locator('#preview_form_title')).toContainText(formTitle)
    } finally {
      await adminLoginNotificationUpdate({
        client: apiv4Admin,
        body: toUpdateBody(original),
      }).catch(() => {})

      await adminLoginNotificationCoverEnable({
        client: apiv4Admin,
        body: { enabled: Boolean(original.notification_cover?.enabled) },
      }).catch(() => {})

      await adminLoginNotificationFormEnable({
        client: apiv4Admin,
        body: { enabled: Boolean(original.notification_form?.enabled) },
      }).catch(() => {})
    }
  })

  test('A6: edit validation blocks invalid payload (bad URL)', async ({ authenticatedPage: page }) => {
    await gotoLoginConfig(page)
    await page.locator('#btnEditLoginNotification').click()

    const modal = page.locator('#modalEditLoginNotification')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#cover_link_url').fill('javascript:alert(1)')

    const putResp = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/login_config/notification') && r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()

    const status = (await putResp).status()
    expect(status).toBeGreaterThanOrEqual(400)
    await expect(modal).toBeVisible()
    await expect(page.locator('.ui-pnotify-title')).toContainText(/error/i)
  })
})
