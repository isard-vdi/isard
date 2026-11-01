// Drives the admin Storage "Reconcile" panel through the portal: Report
// (apply=false) and Apply (apply=true) both POST /api/v4/admin/storage/reconcile.

import { test, expect } from '../../fixtures/apiv4/index.js'

const STORAGE_URL = '/isard-admin/admin/domains/render/Storage'
const RECONCILE = '/api/v4/admin/storage/reconcile'

test.describe('Admin Storage — reconcile panel', () => {
  test('Report then Apply drive the reconcile endpoint and render the report', async ({
    authenticatedPage: page,
  }, testInfo) => {
    const consoleErrors = []
    page.on('console', (m) => {
      if (m.type() === 'error') consoleErrors.push(m.text())
    })
    page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${e}`))
    // Apply pops a window.confirm; accept it so the applying POST fires.
    page.on('dialog', (d) => d.accept())

    await page.goto(STORAGE_URL)
    await page
      .locator('#btn-reconcile-report')
      .waitFor({ state: 'visible', timeout: 20000 })
    await expect(page.locator('#btn-reconcile-apply')).toBeVisible()

    // --- Report (apply=false) ---
    const reportResp = page.waitForResponse(
      (r) =>
        r.url().endsWith(RECONCILE) && r.request().method() === 'POST',
      { timeout: 25000 },
    )
    await page.locator('#btn-reconcile-report').click()
    const rr = await reportResp
    expect(rr.status()).toBeLessThan(400)
    expect((await rr.json()).apply).toBe(false)

    await expect(page.locator('#reconcile-report')).toContainText(/Last report/i, {
      timeout: 25000,
    })
    await page.screenshot({
      path: testInfo.outputPath('reconcile-report.png'),
      fullPage: true,
    })

    // --- Apply (apply=true) ---
    const applyResp = page.waitForResponse(
      (r) => r.url().endsWith(RECONCILE) && r.request().method() === 'POST',
      { timeout: 25000 },
    )
    await page.locator('#btn-reconcile-apply').click()
    const ar = await applyResp
    expect(ar.status()).toBeLessThan(400)
    expect((await ar.json()).apply).toBe(true)
    await page.screenshot({
      path: testInfo.outputPath('reconcile-apply.png'),
      fullPage: true,
    })

    const panelErrors = consoleErrors.filter(
      (e) => /reconcile|storage_reconcile\.js/i.test(e),
    )
    expect(
      panelErrors,
      `panel console errors: ${panelErrors.join(' | ')}`,
    ).toEqual([])
    testInfo.attach('all-console-errors', {
      body: consoleErrors.join('\n') || '(none)',
      contentType: 'text/plain',
    })
  })
})
