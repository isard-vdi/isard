// @ts-check
//
// Admin desktops smoke — previously the entire file was commented out.
// Pin the landing-page render + i18n-key resolution for the Flask
// admin's desktops table. CRUD flows are out of scope (they require
// seeded desktops + a full hypervisor); this catches the hot case —
// a blank page after an admin-JS bundle regression.

import { expect } from '@playwright/test'
import { test } from '../login-page'

test.describe('Admin desktops', () => {
  test('admin desktops page loads', async ({ page, login }) => {
    // The admin desktops table is served by the Flask webapp under
    // /isard-admin/admin/domains/render/Desktops.
    const response = await page.goto('/isard-admin/admin/domains/render/Desktops')
    if (response) expect(response.status()).toBeLessThan(400)

    await expect(
      page.getByRole('heading', { name: /desktops/i }).first()
    ).toBeVisible({ timeout: 10000 })
  })

  test('admin desktops has a datatable', async ({ page, login }) => {
    await page.goto('/isard-admin/admin/domains/render/Desktops')
    await page.waitForLoadState('networkidle')

    // jQuery DataTables renders a <table> with a generated wrapper. If
    // neither is present, the admin bundle didn't hydrate.
    const hasDataTable = await page
      .locator('table.dataTable, div.dataTables_wrapper')
      .first()
      .isVisible({ timeout: 10000 })
      .catch(() => false)
    expect(hasDataTable).toBeTruthy()
  })
})
