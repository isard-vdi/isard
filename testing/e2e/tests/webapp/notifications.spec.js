// Drives the notification administration pages:
//   /isard-admin/admin/notifications_manage   → Section A
//   /isard-admin/admin/notifications_templates → Section B
//   /isard-admin/admin/notifications_logs      → Section C
//
// Mirrors testing/e2e/specs/webapp/notifications.md — each test(...)
// corresponds to a numbered scenario in that spec.
//
// Conventions:
//   - Names go through testInfo.annotations (type "notif-id" / "tmpl-id")
//     so afterEach can clean them up even if the test failed mid-flow.
//   - The Select2 #display multi-select is driven via page.evaluate because
//     Select2's DOM wrapper is not a standard <select> — direct Playwright
//     fill/selectOption won't set the underlying value reliably.
//   - All DataTables are expanded to show all rows (page.len(-1)) before
//     row lookups so rows beyond page 1 are in the DOM.

import { test, expect, apiv4ClientForPage, unwrap } from '../../fixtures/apiv4/index.js'
import {
  adminCreateNotification,
  adminDeleteNotification,
  adminGetNotification,
  adminListNotifications,
  adminCreateNotificationTemplate,
  adminDeleteNotificationTemplate,
  adminGetNotificationTemplate,
  adminListCustomNotificationTemplates,
  adminListSystemNotificationTemplates,
  adminListNotificationTemplates,
  getUserNotificationTriggerDisplay,
} from '../../src/gen/apiv4/sdk.gen'

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function uniqueName(testInfo, prefix = 'e2e-notif') {
  return `${prefix}-${testInfo.workerIndex}-${Date.now()}`
}

function trackNotifId(testInfo, id) {
  testInfo.annotations.push({ type: 'notif-id', description: id })
}

function trackTmplId(testInfo, id) {
  testInfo.annotations.push({ type: 'tmpl-id', description: id })
}

async function createNotificationViaApi(client, data) {
  await unwrap(adminCreateNotification({ client, body: data }))
  // POST returns {"id": ""} — the backend doesn't capture RethinkDB's generated_keys.
  // Fall back to listing and matching by name, same as createTemplateViaApi.
  const list = await unwrap(adminListNotifications({ client }))
  const created = (list?.notifications ?? []).find((n) => n.name === data.name)
  if (!created?.id) throw new Error(`createNotificationViaApi: notification "${data.name}" not found after creation`)
  return created.id
}

async function deleteNotificationViaApi(client, id, deleteLogs = true) {
  await adminDeleteNotification({
    client,
    path: { notification_id: id },
    body: { delete_logs: deleteLogs },
  }).catch(() => {})
}

async function createTemplateViaApi(client, { name, language, title, body, footer }) {
  const created = await unwrap(
    adminCreateNotificationTemplate({
      client,
      body: { name, language, title, body, footer, default: language },
    })
  )
  if (!created?.id) throw new Error(`createTemplateViaApi: POST did not return an id for template "${name}"`)
  return created
}

async function deleteTemplateViaApi(client, id) {
  await adminDeleteNotificationTemplate({ client, path: { template_id: id } }).catch(() => {})
}

async function getFirstTemplate(client) {
  const list = await unwrap(adminListNotificationTemplates({ client })).catch(() => null)
  return (list?.templates ?? [])[0] ?? null
}

// Returns an existing template or creates one so tests in section A don't
// skip on a fresh/empty database.
async function ensureTemplate(client, testInfo) {
  const existing = await getFirstTemplate(client)
  if (existing) return existing
  const tmpl = await createTemplateViaApi(client, {
    name: uniqueName(testInfo, 'e2e-tmpl-prereq'),
    language: 'en',
    title: 'E2E prerequisite template',
    body: '<p>E2E test prerequisite</p>',
    footer: '',
  })
  trackTmplId(testInfo, tmpl.id)
  return tmpl
}

async function expandDatatablePagination(page, tableId) {
  await page.evaluate((id) => {
    // eslint-disable-next-line no-undef
    const t = $(`#${id}`).DataTable()
    if (t && typeof t.page?.len === 'function') t.page.len(-1).draw(false)
  }, tableId)
}

async function waitForDatatableLoad(page, tableId, timeout = 15000) {
  await page.locator(`#${tableId}`).waitFor({ state: 'visible', timeout })
  // Wait until the loading spinner disappears (real rows or empty state)
  await page
    .locator(`#${tableId} tbody tr`)
    .first()
    .waitFor({ state: 'visible', timeout })
}

// Click a PNotify action button by its button text (case-insensitive).
async function clickPnotifyButton(page, text, timeout = 8000) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', {
      hasText: new RegExp(text, 'i'),
    })
    .first()
    .click({ timeout })
}

// Set a Select2 multiple-select value programmatically.
async function setSelect2Values(page, selector, values) {
  await page.evaluate(
    ({ sel, vals }) => {
      // eslint-disable-next-line no-undef
      $(sel).val(vals).trigger('change')
    },
    { sel: selector, vals: values },
  )
}

// ---------------------------------------------------------------------------
// Navigation helpers
// ---------------------------------------------------------------------------

async function gotoManage(page) {
  await page.goto('/isard-admin/admin/notifications_manage')
  await waitForDatatableLoad(page, 'notifications-table')
  await expandDatatablePagination(page, 'notifications-table')
}

async function gotoTemplates(page) {
  await page.goto('/isard-admin/admin/notifications_templates')
  await waitForDatatableLoad(page, 'custom-notification-tmpls-table')
  await expandDatatablePagination(page, 'custom-notification-tmpls-table')
}

async function gotoLogs(page) {
  await page.goto('/isard-admin/admin/notifications_logs')
  // The logs page starts without a table — just wait for the status select
  await page.locator('#status').waitFor({ state: 'visible', timeout: 10000 })
}

// ---------------------------------------------------------------------------
// SECTION A — Manage Notifications
// ---------------------------------------------------------------------------

test.describe.serial('Admin Notifications — Manage', () => {
  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    const notifIds = testInfo.annotations
      .filter((a) => a.type === 'notif-id')
      .map((a) => a.description)
    for (const id of notifIds) {
      await deleteNotificationViaApi(apiv4Admin, id, true)
    }
    // Clean up any prerequisite templates created by ensureTemplate()
    const tmplIds = testInfo.annotations
      .filter((a) => a.type === 'tmpl-id')
      .map((a) => a.description)
    for (const id of tmplIds) {
      await deleteTemplateViaApi(apiv4Admin, id)
    }
  })

  // -------------------------------------------------------------------------
  // A1 — Create a notification via the UI and verify it is listed
  // -------------------------------------------------------------------------
  test('A1: creates a notification and lists it in #notifications-table', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueName(testInfo)
    await ensureTemplate(apiv4Admin, testInfo)

    await gotoManage(page)

    await page.locator('.btn-add-notification').first().click()
    const modal = page.locator('#modalNotification')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Wait for async dropdowns (templates, actions) to load
    await modal.locator('#template_id option').first().waitFor({ state: 'attached', timeout: 10000 })
    await modal.locator('#action_id option').first().waitFor({ state: 'attached', timeout: 10000 })

    await modal.locator('#name').fill(name)
    await modal.locator('#trigger').selectOption('login')
    await setSelect2Values(page, '#modalNotification #display', ['modal'])
    await modal.locator('#action_id').selectOption('custom')
    await modal.locator('#template_id').selectOption({ index: 0 })
    await modal.locator('#order').fill('0')

    const createResponse = page.waitForResponse(
      (r) => r.url().includes('/api/v4/admin/item/notification') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await createResponse
    expect(resp.status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /notification added/i }),
    ).toBeVisible({ timeout: 8000 })

    // Find the id from the API response to track for cleanup and row lookup
    const list = await unwrap(adminListNotifications({ client: apiv4Admin }))
    const created = (list?.notifications ?? []).find((n) => n.name === name)
    expect(created, 'created notification not found via API').toBeTruthy()
    trackNotifId(testInfo, created.id)

    await expandDatatablePagination(page, 'notifications-table')
    const row = page.locator(`#notifications-table tbody tr[id="${created.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await expect(row).toContainText(name)
  })

  // -------------------------------------------------------------------------
  // A2 — Edit a notification's name via the pencil icon
  // -------------------------------------------------------------------------
  test('A2: edits notification name via pencil icon', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstTemplate = await ensureTemplate(apiv4Admin, testInfo)
    const original = uniqueName(testInfo)
    const edited = `${original}-edited`

    const id = await createNotificationViaApi(apiv4Admin, {
      name: original,
      trigger: 'login',
      display: ['modal'],
      action_id: 'custom',
      item_type: 'user',
      template_id: firstTemplate.id,
      order: 0,
      enabled: true,
      keep_time: 168,
      allowed: { roles: false, categories: false, groups: false, users: false },
    })
    trackNotifId(testInfo, id)

    await gotoManage(page)
    const row = page.locator(`#notifications-table tbody tr[id="${id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button#btn-edit').click()

    const modal = page.locator('#modalNotification')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#name')).toHaveValue(original)

    await modal.locator('#name').fill(edited)

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/notification/${id}`) && r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await editResponse
    expect(resp.status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /notification updated/i }),
    ).toBeVisible({ timeout: 8000 })

    await expect(row).toContainText(edited, { timeout: 8000 })

    const fresh = await unwrap(adminGetNotification({ client: apiv4Admin, path: { notification_id: id } }))
    expect(fresh?.name ?? fresh?.['name']).toBe(edited)
  })

  // -------------------------------------------------------------------------
  // A3 — Delete notification keeping logs (3-button PNotify)
  // -------------------------------------------------------------------------
  test('A3: deletes notification with logs via 3-button confirm dialog', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstTemplate = await ensureTemplate(apiv4Admin, testInfo)

    const id = await createNotificationViaApi(apiv4Admin, {
      name: uniqueName(testInfo, 'e2e-notif-a3'),
      trigger: 'login',
      display: ['modal'],
      action_id: 'custom',
      item_type: 'user',
      template_id: firstTemplate.id,
      order: 0,
      enabled: true,
      keep_time: 168,
      allowed: { roles: false, categories: false, groups: false, users: false },
    })
    trackNotifId(testInfo, id)

    await gotoManage(page)
    const row = page.locator(`#notifications-table tbody tr[id="${id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    // Set up response listener before clicking so we don't miss the response
    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/notification/${id}`) && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await row.locator('button#btn-delete').click()
    // 3-button PNotify — click "Delete with logs"
    await clickPnotifyButton(page, 'delete with logs')
    const resp = await deleteResponse
    expect(resp.status()).toBeLessThan(400)
    expect(resp.request().postDataJSON()).toMatchObject({ delete_logs: true })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /deleted/i }),
    ).toBeVisible({ timeout: 8000 })
    await expect(row).toBeHidden({ timeout: 8000 })

    const list = await unwrap(adminListNotifications({ client: apiv4Admin }))
    expect((list?.notifications ?? []).find((n) => n.id === id)).toBeUndefined()
  })

  // -------------------------------------------------------------------------
  // A4 — Delete notification without logs
  // -------------------------------------------------------------------------
  test('A4: deletes notification without logs', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstTemplate = await ensureTemplate(apiv4Admin, testInfo)

    const id = await createNotificationViaApi(apiv4Admin, {
      name: uniqueName(testInfo, 'e2e-notif-a4'),
      trigger: 'login',
      display: ['modal'],
      action_id: 'custom',
      item_type: 'user',
      template_id: firstTemplate.id,
      order: 0,
      enabled: true,
      keep_time: 168,
      allowed: { roles: false, categories: false, groups: false, users: false },
    })
    trackNotifId(testInfo, id)

    await gotoManage(page)
    const row = page.locator(`#notifications-table tbody tr[id="${id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/notification/${id}`) && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await row.locator('button#btn-delete').click()
    await clickPnotifyButton(page, 'delete without logs')
    const resp = await deleteResponse
    expect(resp.status()).toBeLessThan(400)
    expect(resp.request().postDataJSON()).toMatchObject({ delete_logs: false })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /deleted/i }),
    ).toBeVisible({ timeout: 8000 })
    await expect(row).toBeHidden({ timeout: 8000 })
    const list = await unwrap(adminListNotifications({ client: apiv4Admin }))
    expect((list?.notifications ?? []).find((n) => n.id === id)).toBeUndefined()
  })

  // -------------------------------------------------------------------------
  // A5 — Delete button absent for desktop item_type rows
  // -------------------------------------------------------------------------
  test('A5: delete button is absent for desktop item_type notifications', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    // Find a seeded notification with item_type=desktop (unused_desktops)
    const list = await unwrap(adminListNotifications({ client: apiv4Admin }))
    const desktopNotif = (list?.notifications ?? []).find((n) => n.item_type === 'desktop')
    test.skip(!desktopNotif, 'no desktop item_type notification found in the dev DB')

    const userNotif = (list?.notifications ?? []).find((n) => n.item_type === 'user')

    await gotoManage(page)

    const desktopRow = page.locator(`#notifications-table tbody tr[id="${desktopNotif.id}"]`)
    await expect(desktopRow).toBeVisible({ timeout: 10000 })
    // Delete button must NOT appear for desktop type
    await expect(desktopRow.locator('button#btn-delete')).toHaveCount(0)
    // Edit and alloweds buttons must still be present
    await expect(desktopRow.locator('button#btn-edit')).toBeVisible()
    await expect(desktopRow.locator('button#btn-alloweds')).toBeVisible()

    // Cross-check: a user item_type row DOES have the delete button
    if (userNotif) {
      const userRow = page.locator(`#notifications-table tbody tr[id="${userNotif.id}"]`)
      await expect(userRow).toBeVisible({ timeout: 10000 })
      await expect(userRow.locator('button#btn-delete')).toBeVisible()
    }
  })

  // -------------------------------------------------------------------------
  // A6 — Parsley validation blocks submission with empty name
  // -------------------------------------------------------------------------
  test('A6: Parsley blocks submission when name is empty', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    await ensureTemplate(apiv4Admin, testInfo)

    await gotoManage(page)
    await page.locator('.btn-add-notification').first().click()
    const modal = page.locator('#modalNotification')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('#template_id option').first().waitFor({ state: 'attached', timeout: 10000 })

    // Leave #name empty, fill other required fields
    await modal.locator('#trigger').selectOption('login')
    await setSelect2Values(page, '#modalNotification #display', ['modal'])
    await modal.locator('#template_id').selectOption({ index: 0 })
    await modal.locator('#order').fill('0')

    let postFired = false
    page.on('request', (req) => {
      if (req.url().includes('/api/v4/admin/item/notification') && req.method() === 'POST') {
        postFired = true
      }
    })

    await modal.locator('#send').click()
    // Parsley marks the name field as invalid
    await expect(modal.locator('#name')).toHaveClass(/parsley-error/, { timeout: 3000 })
    await expect(modal).toBeVisible()
    expect(postFired, 'POST must not fire with an empty name').toBeFalsy()
  })

  // -------------------------------------------------------------------------
  // A7 — Selecting a template in the notification modal renders its preview
  // -------------------------------------------------------------------------
  test('A7: selecting a template in the notification modal renders its preview', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const tmpl = await createTemplateViaApi(apiv4Admin, {
      name: uniqueName(testInfo, 'e2e-tmpl-a7'),
      language: 'en',
      title: 'A7 preview title',
      body: '<p>A7 preview body</p>',
      footer: '',
    })
    trackTmplId(testInfo, tmpl.id)

    await gotoManage(page)
    await page.locator('.btn-add-notification').first().click()
    const modal = page.locator('#modalNotification')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await modal.locator('#template_id option').first().waitFor({ state: 'attached', timeout: 10000 })

    // Selecting the template triggers addTemplatePreviewListener →
    // GET /api/v4/admin/notifications/template/{id} → renders title in #preview-panel
    const previewResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/notifications/template/${tmpl.id}`) &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await modal.locator('#template_id').selectOption(tmpl.id)
    await previewResp

    await expect(modal.locator('#preview-panel')).toBeVisible({ timeout: 5000 })
    await expect(modal.locator('#preview-panel')).toContainText('A7 preview title')
  })
})

// ---------------------------------------------------------------------------
// SECTION B — Notification Templates
// ---------------------------------------------------------------------------

test.describe.serial('Admin Notifications — Templates', () => {
  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    const ids = testInfo.annotations
      .filter((a) => a.type === 'tmpl-id')
      .map((a) => a.description)
    for (const id of ids) {
      await deleteTemplateViaApi(apiv4Admin, id)
    }
  })

  // -------------------------------------------------------------------------
  // B1 — Create a custom template via the UI
  // -------------------------------------------------------------------------
  test('B1: creates a custom template and lists it in #custom-notification-tmpls-table', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueName(testInfo, 'e2e-tmpl')

    await gotoTemplates(page)
    await page.locator('.btn-add-notification-tmpl').first().click()
    const modal = page.locator('#modalNotificationTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#name').fill(name)
    await modal.locator('#language').selectOption('en')
    await modal.locator('#title').fill('e2e test title')
    await modal.locator('#body').fill('<p>e2e test body</p>')

    const createResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/notifications/template') && r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await createResponse
    expect(resp.status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /added/i }),
    ).toBeVisible({ timeout: 8000 })

    // Find the created template by name to get its ID for cleanup
    const list = await unwrap(adminListCustomNotificationTemplates({ client: apiv4Admin }))
    const created = (list?.templates ?? []).find((t) => t.name === name)
    expect(created, 'created template not found via API').toBeTruthy()
    trackTmplId(testInfo, created.id)

    await expandDatatablePagination(page, 'custom-notification-tmpls-table')
    const row = page.locator(`#custom-notification-tmpls-table tbody tr[id="${created.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await expect(row).toContainText(name)
  })

  // -------------------------------------------------------------------------
  // B2 — Edit a custom template's title via the pencil icon
  // -------------------------------------------------------------------------
  test('B2: edits custom template title via pencil icon', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueName(testInfo, 'e2e-tmpl-b2')
    const tmpl = await createTemplateViaApi(apiv4Admin, {
      name,
      language: 'en',
      title: 'original title',
      body: '<p>original body</p>',
      footer: '',
    })
    trackTmplId(testInfo, tmpl.id)

    await gotoTemplates(page)
    const row = page.locator(`#custom-notification-tmpls-table tbody tr[id="${tmpl.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button.btn-edit-notification-tmpl').click()

    const modal = page.locator('#modalNotificationTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    // Modal loads data via AJAX — wait for name to be pre-filled
    await expect(modal.locator('#name')).not.toHaveValue('', { timeout: 8000 })

    await modal.locator('#title').fill('updated title')

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/notifications/template/${tmpl.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await editResponse
    expect(resp.status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /updated/i }),
    ).toBeVisible({ timeout: 8000 })

    const fresh = await unwrap(
      adminGetNotificationTemplate({ client: apiv4Admin, path: { template_id: tmpl.id } }),
    )
    const enLang = fresh?.lang?.en
    expect(enLang?.title).toBe('updated title')
  })

  // -------------------------------------------------------------------------
  // B3 — Delete a custom template via the × icon
  // -------------------------------------------------------------------------
  test('B3: deletes custom template via the × icon', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueName(testInfo, 'e2e-tmpl-b3')
    const tmpl = await createTemplateViaApi(apiv4Admin, {
      name,
      language: 'en',
      title: 'to delete',
      body: '<p>to be deleted</p>',
      footer: '',
    })
    trackTmplId(testInfo, tmpl.id) // safety net — afterEach won't find it if deleted

    await gotoTemplates(page)
    const row = page.locator(`#custom-notification-tmpls-table tbody tr[id="${tmpl.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    // Set up listener before clicks so we never miss the DELETE response
    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/notifications/template/${tmpl.id}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await row.locator('button.btn-delete-notification-tmpl').click()
    // Standard PNotify confirm — "Ok" button
    await clickPnotifyButton(page, '^ok$')
    const resp = await deleteResponse
    expect(resp.status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /deleted/i }),
    ).toBeVisible({ timeout: 8000 })
    await expect(row).toBeHidden({ timeout: 8000 })

    const list = await unwrap(adminListCustomNotificationTemplates({ client: apiv4Admin }))
    expect((list?.templates ?? []).find((t) => t.id === tmpl.id)).toBeUndefined()
  })

  // -------------------------------------------------------------------------
  // B4 — System templates have no delete button
  // -------------------------------------------------------------------------
  test('B4: system templates have only edit button, no delete button', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    const systemList = await unwrap(adminListSystemNotificationTemplates({ client: apiv4Admin }))
    test.skip(
      !systemList?.templates?.length,
      'no system templates in the dev DB',
    )

    await gotoTemplates(page)

    // Wait for system templates table
    await page.locator('#system-notification-tmpls-table').waitFor({ state: 'visible', timeout: 10000 })
    await page
      .locator('#system-notification-tmpls-table tbody tr')
      .first()
      .waitFor({ state: 'visible', timeout: 10000 })

    const systemRows = page.locator('#system-notification-tmpls-table tbody tr')
    const count = await systemRows.count()
    expect(count).toBeGreaterThan(0)

    // No delete (×) button on any system row
    for (let i = 0; i < Math.min(count, 5); i++) {
      const rowActions = systemRows.nth(i).locator('button.btn-delete-notification-tmpl')
      await expect(rowActions).toHaveCount(0)
    }

    // Edit button IS present on system rows
    await expect(
      systemRows.first().locator('button.btn-edit-notification-tmpl'),
    ).toBeVisible()

    // Custom rows do have the delete button
    const customRows = page.locator('#custom-notification-tmpls-table tbody tr')
    const customCount = await customRows.count()
    if (customCount > 0) {
      await expect(
        customRows.first().locator('button.btn-delete-notification-tmpl'),
      ).toBeVisible()
    }
  })

  // -------------------------------------------------------------------------
  // B5 — Template preview toggles the body textarea ↔ rendered HTML
  // -------------------------------------------------------------------------
  test('B5: Preview button renders HTML and Edit text restores the textarea', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = uniqueName(testInfo, 'e2e-tmpl-b5')
    const tmpl = await createTemplateViaApi(apiv4Admin, {
      name,
      language: 'en',
      title: 'preview test',
      body: '<p>Hello <strong>world</strong></p>',
      footer: '',
    })
    trackTmplId(testInfo, tmpl.id)

    await gotoTemplates(page)
    const row = page.locator(`#custom-notification-tmpls-table tbody tr[id="${tmpl.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button.btn-edit-notification-tmpl').click()

    const modal = page.locator('#modalNotificationTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#name')).not.toHaveValue('', { timeout: 8000 })

    // Before preview: textarea visible, preview div hidden
    await expect(modal.locator('#body')).toBeVisible()
    await expect(modal.locator('#body-preview')).toBeHidden()
    await expect(modal.locator('#btn-preview')).toContainText(/preview/i)

    // Click Preview
    await modal.locator('#btn-preview').click()

    // After preview: textarea hidden, preview div visible
    await expect(modal.locator('#body')).toBeHidden()
    await expect(modal.locator('#body-preview')).toBeVisible()
    await expect(modal.locator('#btn-preview')).toContainText(/edit text/i)

    // No API call fired (preview is client-side)

    // Click Edit text to restore
    await modal.locator('#btn-preview').click()
    await expect(modal.locator('#body')).toBeVisible()
    await expect(modal.locator('#body-preview')).toBeHidden()
    await expect(modal.locator('#btn-preview')).toContainText(/preview/i)
  })

  // -------------------------------------------------------------------------
  // B6 — Parsley validation blocks submission with empty name
  // -------------------------------------------------------------------------
  test('B6: Parsley blocks submission when template name is empty', async ({
    authenticatedPage: page,
  }) => {
    await gotoTemplates(page)
    await page.locator('.btn-add-notification-tmpl').first().click()
    const modal = page.locator('#modalNotificationTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Select a language but leave name empty
    await modal.locator('#language').selectOption('en')
    await modal.locator('#title').fill('title without name')

    let postFired = false
    page.on('request', (req) => {
      if (
        req.url().includes('/api/v4/admin/item/notifications/template') &&
        req.method() === 'POST'
      ) {
        postFired = true
      }
    })

    await modal.locator('#send').click()
    await expect(modal.locator('#name')).toHaveClass(/parsley-error/, { timeout: 3000 })
    await expect(modal).toBeVisible()
    expect(postFired, 'POST must not fire with an empty name').toBeFalsy()
  })

  // -------------------------------------------------------------------------
  // B7 — Expanding a custom template row shows its default language content
  // -------------------------------------------------------------------------
  test('B7: expanding a custom template row shows its default language content inline', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const tmpl = await createTemplateViaApi(apiv4Admin, {
      name: uniqueName(testInfo, 'e2e-tmpl-b7'),
      language: 'en',
      title: 'B7 inline title',
      body: '<p>B7 inline body content</p>',
      footer: '',
    })
    trackTmplId(testInfo, tmpl.id)

    await gotoTemplates(page)
    const row = page.locator(`#custom-notification-tmpls-table tbody tr[id="${tmpl.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    // Click the expand (details-control) button — renders addDetailPannel(row.data(), "custom")
    await row.locator('td.details-control button').click()

    // Child row appears with the default language content in #system_tmpl-title / #system_tmpl-body
    await expect(page.getByText('B7 inline title')).toBeVisible({ timeout: 8000 })
    await expect(page.getByText('B7 inline body content')).toBeVisible({ timeout: 5000 })
  })

  // -------------------------------------------------------------------------
  // B8 — HTML injection in body is blocked client-side by checkCleanHTML
  // -------------------------------------------------------------------------
  test('B8: body containing <script> is rejected client-side without firing POST', async ({
    authenticatedPage: page,
  }) => {
    await gotoTemplates(page)
    await page.locator('.btn-add-notification-tmpl').first().click()
    const modal = page.locator('#modalNotificationTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#name').fill('e2e-html-injection-test')
    await modal.locator('#language').selectOption('en')
    await modal.locator('#body').fill('<script>alert(1)</script>')

    let postFired = false
    page.on('request', (req) => {
      if (req.url().includes('/api/v4/admin/item/notifications/template') && req.method() === 'POST') {
        postFired = true
      }
    })

    await modal.locator('#send').click()

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /invalid html/i }),
    ).toBeVisible({ timeout: 5000 })
    await expect(modal).toBeVisible()
    expect(postFired, 'POST must not fire when body contains <script>').toBeFalsy()
  })

  // -------------------------------------------------------------------------
  // B9 — Expanding a system template row shows its system content panel
  // -------------------------------------------------------------------------
  test('B9: expanding a system template row shows its system content panel', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    const systemList = await unwrap(adminListSystemNotificationTemplates({ client: apiv4Admin }))
    test.skip(!systemList?.templates?.length, 'no system templates in the dev DB')

    await gotoTemplates(page)
    await page.locator('#system-notification-tmpls-table').waitFor({ state: 'visible', timeout: 10000 })
    const firstRow = page.locator('#system-notification-tmpls-table tbody tr').first()
    await firstRow.waitFor({ state: 'visible', timeout: 10000 })

    // Click expand — addDetailPannel(row.data(), "system") uses template.system (not template.lang)
    await firstRow.locator('td.details-control button').click()

    // Parent row gets class "shown"; child row inserted by DataTables
    await expect(firstRow).toHaveClass(/shown/, { timeout: 8000 })
    // The cloned panel shows #system-title ("System default template" heading)
    await expect(page.getByText('System default template').first()).toBeVisible({ timeout: 5000 })
  })

  // -------------------------------------------------------------------------
  // B10 — Edit modal for a system template opens pre-filled in edit mode
  // -------------------------------------------------------------------------
  test('B10: edit modal opens pre-filled for a system template and shows edit-mode controls', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    const systemList = await unwrap(adminListSystemNotificationTemplates({ client: apiv4Admin }))
    test.skip(!systemList?.templates?.length, 'no system templates in the dev DB')
    const systemTmpl = systemList.templates[0]

    await gotoTemplates(page)
    await page.locator('#system-notification-tmpls-table').waitFor({ state: 'visible', timeout: 10000 })
    const row = page.locator(`#system-notification-tmpls-table tbody tr[id="${systemTmpl.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    const editResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/notifications/template/${systemTmpl.id}`) &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await row.locator('button.btn-edit-notification-tmpl').click()
    await editResp

    const modal = page.locator('#modalNotificationTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    // Name is pre-filled from the GET response — use input#name to avoid matching
    // the <a id="name"> parameter link that system templates render in the vars panel
    await expect(modal.locator('input#name')).toHaveValue(systemTmpl.name, { timeout: 8000 })
    // Apply button is only visible in edit mode (hidden in add mode)
    await expect(modal.locator('#btn-apply')).toBeVisible()
    // Modal title reflects edit mode
    await expect(modal.locator('.modal-header h4')).toContainText(/edit notification template/i)
  })

  // -------------------------------------------------------------------------
  // B11 — Apply button saves language content via PUT without closing the modal
  // -------------------------------------------------------------------------
  test('B11: Apply button saves language content via PUT without closing the modal', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const tmpl = await createTemplateViaApi(apiv4Admin, {
      name: uniqueName(testInfo, 'e2e-tmpl-b11'),
      language: 'en',
      title: 'B11 original title',
      body: '<p>B11 original body</p>',
      footer: '',
    })
    trackTmplId(testInfo, tmpl.id)

    await gotoTemplates(page)
    const row = page.locator(`#custom-notification-tmpls-table tbody tr[id="${tmpl.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button.btn-edit-notification-tmpl').click()

    const modal = page.locator('#modalNotificationTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#name')).not.toHaveValue('', { timeout: 8000 })
    // Apply is only shown in edit mode
    await expect(modal.locator('#btn-apply')).toBeVisible()

    await modal.locator('#title').fill('B11 applied title')

    const applyResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/notifications/template/${tmpl.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#btn-apply').click()
    const resp = await applyResp
    expect(resp.status()).toBeLessThan(400)

    // "Language body updated successfully" PNotify appears — modal stays open
    await expect(
      page.locator('.ui-pnotify-title', { hasText: /updated/i }),
    ).toBeVisible({ timeout: 8000 })
    await expect(modal).toBeVisible()

    // API confirms the title was persisted
    const fresh = await unwrap(
      adminGetNotificationTemplate({ client: apiv4Admin, path: { template_id: tmpl.id } }),
    )
    expect(fresh?.lang?.en?.title).toBe('B11 applied title')
  })

  // -------------------------------------------------------------------------
  // B12 — Switching language in edit mode fires GET and reloads template fields
  // -------------------------------------------------------------------------
  test('B12: switching language in edit mode reloads template content via GET', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const tmpl = await createTemplateViaApi(apiv4Admin, {
      name: uniqueName(testInfo, 'e2e-tmpl-b12'),
      language: 'en',
      title: 'B12 English title',
      body: '<p>B12 body</p>',
      footer: '',
    })
    trackTmplId(testInfo, tmpl.id)

    await gotoTemplates(page)
    const row = page.locator(`#custom-notification-tmpls-table tbody tr[id="${tmpl.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('button.btn-edit-notification-tmpl').click()

    const modal = page.locator('#modalNotificationTemplate')
    await modal.waitFor({ state: 'visible', timeout: 10000 })
    await expect(modal.locator('#name')).not.toHaveValue('', { timeout: 8000 })
    await expect(modal.locator('#language')).toHaveValue('en')

    // Switch to a different language — triggers changeBodyLanguage → GET (only in editModal)
    const langResp = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/notifications/template/${tmpl.id}`) &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await modal.locator('#language').selectOption('es')
    await langResp

    // 'es' is not the template's default ('en' is) → #default-lang unchecked
    await expect(modal.locator('#default-lang')).not.toBeChecked({ timeout: 5000 })
    // Title field is empty — the template has no 'es' content and no system fallback
    await expect(modal.locator('#title')).toHaveValue('')
  })
})

// ---------------------------------------------------------------------------
// SECTION C — Notification Logs
// ---------------------------------------------------------------------------

test.describe.serial('Admin Notifications — Logs', () => {
  // afterEach cleans up both notification and template created for log tests
  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    const notifIds = testInfo.annotations
      .filter((a) => a.type === 'notif-id')
      .map((a) => a.description)
    for (const id of notifIds) {
      await deleteNotificationViaApi(apiv4Admin, id, true)
    }
    const tmplIds = testInfo.annotations
      .filter((a) => a.type === 'tmpl-id')
      .map((a) => a.description)
    for (const id of tmplIds) {
      await deleteTemplateViaApi(apiv4Admin, id)
    }
  })

  // -------------------------------------------------------------------------
  // C1 — Status dropdown populates after data exists and triggers the table
  // -------------------------------------------------------------------------
  test('C1: status dropdown populates and loads the users table', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    // Generate a notified entry so the dropdown has at least one status
    await setupLoginNotificationData(page, apiv4Admin, testInfo)

    // Set up listener before navigating so we capture the statuses AJAX that
    // populates #status — gotoLogs returns as soon as the element is visible,
    // not when the AJAX completes.
    const statusesLoaded = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/notifications/statuses') &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await gotoLogs(page)
    await statusesLoaded

    // Dropdown now has "notified" from the data we generated
    await expect(page.locator('#status option[value="notified"]')).toBeAttached({ timeout: 5000 })

    // Selecting "notified" fires the by_status API call and renders the table
    const tableResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/notifications/data/by_status/notified') &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await page.locator('#status').selectOption('notified')
    const resp = await tableResp
    expect(resp.status()).toBeLessThan(400)

    await expect(page.locator('#notifications-users-table')).toBeVisible()
    await page
      .locator('#notifications-users-table tbody tr')
      .first()
      .waitFor({ state: 'visible', timeout: 10000 })
  })

  // -------------------------------------------------------------------------
  // Helper: create a custom login notification + trigger it for the admin user
  // so a notifications_data entry exists with status = "notified"
  // -------------------------------------------------------------------------
  async function setupLoginNotificationData(page, apiv4Admin, testInfo) {
    // Create a template
    const tmplName = uniqueName(testInfo, 'e2e-tmpl-log')
    const tmpl = await createTemplateViaApi(apiv4Admin, {
      name: tmplName,
      language: 'en',
      title: 'e2e log test',
      body: '<p>e2e log test body</p>',
      footer: '',
    })
    trackTmplId(testInfo, tmpl.id)

    // Create a custom login notification for all users
    const notifId = await createNotificationViaApi(apiv4Admin, {
      name: uniqueName(testInfo, 'e2e-notif-log'),
      trigger: 'login',
      display: ['fullpage'],
      action_id: 'custom',
      item_type: 'user',
      template_id: tmpl.id,
      order: 999, // high order to avoid interfering with existing notifications
      enabled: true,
      keep_time: 168,
      force_accept: false,
      allowed: { roles: [], categories: false, groups: false, users: false },
    })
    trackNotifId(testInfo, notifId)

    // Call the login notifications endpoint as the admin user — this creates a
    // notifications_data entry with status="notified" for the custom notification
    const client = apiv4ClientForPage(page)
    await unwrap(
      getUserNotificationTriggerDisplay({ client, path: { trigger: 'login', display: 'fullpage' } }),
    )

    return { notifId, tmplId: tmpl.id }
  }

  // -------------------------------------------------------------------------
  // C2 — Expanding a user row shows the notification log detail table
  // -------------------------------------------------------------------------
  test('C2: expanding a user row shows notification log detail entries', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    await setupLoginNotificationData(page, apiv4Admin, testInfo)

    await gotoLogs(page)

    // Select "notified" status
    const tableResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/notifications/data/by_status/notified') &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await page.locator('#status').selectOption('notified')
    await tableResp

    // Wait for at least one user row
    const firstRow = page.locator('#notifications-users-table tbody tr').first()
    await firstRow.waitFor({ state: 'visible', timeout: 15000 })

    // Expand it
    const detailResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/notifications/data/status/notified/user/') &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await firstRow.locator('td.details-control button').click()
    await detailResp

    // The clone of #notifications-logs-table is FIRST in DOM order (inside the
    // DataTables child row); the original is LAST (inside the hidden template div).
    const detailTable = page.locator('#notifications-logs-table').first()
    await detailTable.waitFor({ state: 'visible', timeout: 10000 })
    await expect(
      detailTable.locator('tbody tr').first(),
    ).toBeVisible({ timeout: 10000 })
  })

  // -------------------------------------------------------------------------
  // C3 — Delete an individual log entry from the detail panel
  // -------------------------------------------------------------------------
  test('C3: deletes an individual notification log entry from the detail panel', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    await setupLoginNotificationData(page, apiv4Admin, testInfo)

    await gotoLogs(page)

    const tableResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/notifications/data/by_status/notified') &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await page.locator('#status').selectOption('notified')
    await tableResp

    const firstRow = page.locator('#notifications-users-table tbody tr').first()
    await firstRow.waitFor({ state: 'visible', timeout: 15000 })

    const detailAjax = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/notifications/data/status/notified/user/') &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await firstRow.locator('td.details-control button').click()
    await detailAjax

    // The clone of #notifications-logs-table is FIRST in DOM (inside DataTables child row);
    // the original is LAST (inside the hidden template div).
    const detailTable = page.locator('#notifications-logs-table').first()
    await detailTable.waitFor({ state: 'visible', timeout: 10000 })
    // Wait for the actual data row (not the loading row) by waiting for the delete button
    const deleteBtn = detailTable.locator('tbody button#btn-delete-notification-data').first()
    await deleteBtn.waitFor({ state: 'visible', timeout: 10000 })
    const firstDetailRow = deleteBtn.locator('xpath=ancestor::tr').first()

    // Get the row id (= notification_data_id) and snapshot the button count.
    // Both are used for the post-delete assertion: rowId gives a stable CSS
    // selector; the button count is the fallback if DataTables hasn't yet set
    // the TR id attribute (which causes rowId to be null).
    const rowId = await firstDetailRow.getAttribute('id')
    const deleteBtnsBefore = await detailTable.locator('tbody button#btn-delete-notification-data').count()

    const deleteResp = page.waitForResponse(
      (r) =>
        r.url().includes('/notifications/data/') &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await deleteBtn.click()
    await clickPnotifyButton(page, '^ok$')
    const resp = await deleteResp
    expect(resp.status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /deleted/i }),
    ).toBeVisible({ timeout: 8000 })

    // Row disappears from the detail table
    if (rowId) {
      await expect(detailTable.locator(`tbody tr[id="${rowId}"]`)).toBeHidden({ timeout: 8000 })
    } else {
      // firstDetailRow is a live locator — after deletion it re-evaluates to the
      // next row. Check button count instead (stable regardless of re-evaluation).
      await expect(detailTable.locator('tbody button#btn-delete-notification-data'))
        .toHaveCount(deleteBtnsBefore - 1, { timeout: 8000 })
    }
  })

  // -------------------------------------------------------------------------
  // C3b — Delete a user row from the main users table
  // -------------------------------------------------------------------------
  test('C3b: deletes a user row from the main notifications-users-table', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    await setupLoginNotificationData(page, apiv4Admin, testInfo)

    await gotoLogs(page)

    const tableResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/notifications/data/by_status/notified') &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await page.locator('#status').selectOption('notified')
    await tableResp

    const firstRow = page.locator('#notifications-users-table tbody tr').first()
    await firstRow.waitFor({ state: 'visible', timeout: 15000 })

    const rowId = await firstRow.getAttribute('id')

    const deleteResp = page.waitForResponse(
      (r) =>
        r.url().includes('/notifications/data/') &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await firstRow.locator('button#btn-delete').click()
    await clickPnotifyButton(page, '^ok$')
    const resp = await deleteResp
    expect(resp.status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /deleted/i }),
    ).toBeVisible({ timeout: 8000 })

    if (rowId) {
      await expect(page.locator(`#notifications-users-table tbody tr[id="${rowId}"]`)).toBeHidden({ timeout: 8000 })
    } else {
      await expect(firstRow).toBeHidden({ timeout: 8000 })
    }
  })

  // -------------------------------------------------------------------------
  // C4 — Delete all notification data clears the users table
  // -------------------------------------------------------------------------
  test('C4: delete all notification data clears the users table', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    // Generate at least one entry so the delete-all has something to clear
    await setupLoginNotificationData(page, apiv4Admin, testInfo)

    await gotoLogs(page)

    const tableResp = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/items/notifications/data/by_status/notified') &&
        r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await page.locator('#status').selectOption('notified')
    await tableResp

    await page.locator('#notifications-users-table tbody tr').first().waitFor({ state: 'visible', timeout: 10000 })

    const deleteAllResp = page.waitForResponse(
      (r) =>
        r.url().endsWith('/api/v4/admin/items/notifications/data') &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await page.locator('#btn-delete-all-data').click()
    await clickPnotifyButton(page, '^ok$')
    const resp = await deleteAllResp
    expect(resp.status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-title', { hasText: /deleted/i }),
    ).toBeVisible({ timeout: 8000 })

    // Table is empty after deletion — DataTables shows one "No data" row
    await expect(
      page.locator('#notifications-users-table tbody td.dataTables_empty'),
    ).toBeVisible({ timeout: 8000 })

    // The status dropdown is also emptied ($('#status').empty()) so no options remain
    await expect(page.locator('#status option')).toHaveCount(0, { timeout: 5000 })
  })
})
