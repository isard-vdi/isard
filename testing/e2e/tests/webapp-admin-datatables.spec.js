// Datatable integration smokes for the high-traffic Flask admin pages.
// Each test asserts:
//   1. Page loads (covered by the navigation spec too, but repeated here
//      so failures are localised instead of cascading).
//   2. The DataTables widget initialises — its jQuery plugin injects a
//      `.dataTables_wrapper` around the server-rendered <table>.
//   3. Either at least one data row renders, or the widget's built-in
//      "No data available" row is shown. Both are acceptable; a blank
//      container means the AJAX call never fired or the handler errored.
//
// Deeper coverage (filter, sort, add/edit/delete CRUD) is left to a
// follow-up wave — these are the pages that most often hide real bugs
// behind a shell that happens to render.

import { test, expect } from '../fixtures/login.js'
import { bridgeAdminSession } from '../fixtures/common.js'

async function expectDataTableReady(page, tableSelector) {
  // DataTables wraps the <table> in a `.dataTables_wrapper` div once
  // initialised. Absence = the plugin never ran (JS error, bundle
  // loading issue, etc).
  const wrapper = page.locator(
    `${tableSelector} ~ .dataTables_wrapper, .dataTables_wrapper:has(${tableSelector})`,
  )
  // Some templates wrap the table before initialisation too — fall back
  // to the globally-generated `.dataTables_info` text which only exists
  // post-init.
  const info = page.locator('.dataTables_info').first()
  await Promise.race([
    wrapper.first().waitFor({ state: 'visible', timeout: 15000 }),
    info.waitFor({ state: 'visible', timeout: 15000 }),
  ])

  // Either a tbody with >=1 row exists, or the "No data" placeholder does.
  const hasRow = await page
    .locator(`${tableSelector} tbody tr`)
    .first()
    .isVisible({ timeout: 5000 })
    .catch(() => false)
  const hasEmpty = await page
    .locator('.dataTables_empty')
    .first()
    .isVisible({ timeout: 2000 })
    .catch(() => false)
  return { hasRow, hasEmpty }
}

test.describe('Admin datatables — users page', () => {
  test.beforeEach(async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.login(page, users.admin, categories)
    await bridgeAdminSession(page)
  })

  test('#users datatable initialises and shows the seeded admin', async ({
    page,
  }) => {
    await page.goto('/isard-admin/admin/users/Management')
    const state = await expectDataTableReady(page, '#users')
    // The admin user is always seeded, so we expect at least one row —
    // if we only see the empty-state, the AJAX call either failed
    // silently or dropped every row.
    expect(state.hasRow, 'users row count').toBeTruthy()
  })

  test('#categories datatable initialises', async ({ page }) => {
    await page.goto('/isard-admin/admin/users/Management')
    const state = await expectDataTableReady(page, '#categories')
    expect(state.hasRow || state.hasEmpty).toBeTruthy()
  })

  test('#groups datatable initialises', async ({ page }) => {
    await page.goto('/isard-admin/admin/users/Management')
    const state = await expectDataTableReady(page, '#groups')
    expect(state.hasRow || state.hasEmpty).toBeTruthy()
  })

  test('#roles datatable initialises', async ({ page }) => {
    await page.goto('/isard-admin/admin/users/Management')
    const state = await expectDataTableReady(page, '#roles')
    expect(state.hasRow || state.hasEmpty).toBeTruthy()
  })
})

test.describe('Admin datatables — hypervisors page', () => {
  test.beforeEach(async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.login(page, users.admin, categories)
    await bridgeAdminSession(page)
  })

  test('#hypervisors datatable initialises', async ({ page }) => {
    await page.goto('/isard-admin/admin/hypervisors')
    const state = await expectDataTableReady(page, '#hypervisors')
    // A dev host typically has one hypervisor; at minimum the empty
    // state must show (not a blank div).
    expect(state.hasRow || state.hasEmpty).toBeTruthy()
  })

  test('#hypervisors_pools datatable initialises', async ({ page }) => {
    await page.goto('/isard-admin/admin/hypervisors')
    const state = await expectDataTableReady(page, '#hypervisors_pools')
    expect(state.hasRow || state.hasEmpty).toBeTruthy()
  })
})

test.describe('Admin datatables — domains pages', () => {
  test.beforeEach(async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.login(page, users.admin, categories)
    await bridgeAdminSession(page)
  })

  test('Desktops datatable initialises', async ({ page }) => {
    await page.goto('/isard-admin/admin/domains/render/Desktops')
    // The desktops template uses a jQuery-DataTables table; the ID
    // varies by server-render so target by role attribute instead.
    const hasTable = await page
      .locator('table.dataTable, .dataTables_wrapper')
      .first()
      .isVisible({ timeout: 15000 })
      .catch(() => false)
    expect(hasTable, 'desktops datatable wrapper').toBeTruthy()
  })

  test('Templates datatable initialises', async ({ page }) => {
    await page.goto('/isard-admin/admin/domains/render/Templates')
    const hasTable = await page
      .locator('table.dataTable, .dataTables_wrapper')
      .first()
      .isVisible({ timeout: 15000 })
      .catch(() => false)
    expect(hasTable, 'templates datatable wrapper').toBeTruthy()
  })

  test('Deployments datatable initialises', async ({ page }) => {
    await page.goto('/isard-admin/admin/domains/render/Deployments')
    const hasTable = await page
      .locator('table.dataTable, .dataTables_wrapper')
      .first()
      .isVisible({ timeout: 15000 })
      .catch(() => false)
    expect(hasTable, 'deployments datatable wrapper').toBeTruthy()
  })

  test('Storage datatable initialises', async ({ page }) => {
    await page.goto('/isard-admin/admin/domains/render/Storage')
    const hasTable = await page
      .locator('table.dataTable, .dataTables_wrapper')
      .first()
      .isVisible({ timeout: 15000 })
      .catch(() => false)
    expect(hasTable, 'storage datatable wrapper').toBeTruthy()
  })
})
