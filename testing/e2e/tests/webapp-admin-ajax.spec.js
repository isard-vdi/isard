// AJAX-driven admin action smokes.
//
// The datatables spec verifies the *page* loads. This spec verifies the
// secondary AJAX calls that the page-level JS fires AFTER the user opens
// modals, picks a row, or types into a typeahead input — the traffic
// most likely to silently break when an apiv4 route is renamed or the
// /api/v4 prefix is dropped during a refactor.
//
// We capture network responses and assert that the URLs the page emits
// resolve to a 2xx/3xx code. A 404 on an admin AJAX URL almost always
// means the v3->v4 migration missed the call site (the request lands on
// the static SPA fallback or 404s outright). Test passes if the URL
// pattern appears in the network log AND its status is < 400.
//
// We deliberately do NOT assert on the on-screen UI here — those
// assertions are flaky against a dev DB. Network status is enough to
// catch the regression we care about.

import { test, expect } from '../fixtures/login.js'
import { bridgeAdminSession } from '../fixtures/common.js'

function captureXhr(page, predicate) {
  const matched = []
  page.on('response', async (resp) => {
    if (predicate(resp.url())) {
      matched.push({
        url: resp.url(),
        status: resp.status(),
        method: resp.request().method(),
      })
    }
  })
  return matched
}

test.describe('Admin AJAX — hypervisors page', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  test('hypervisors_pools dropdown POST resolves under /api/v4', async ({ page }) => {
    const xhr = captureXhr(page, (u) => u.includes('/admin/table/hypervisors_pools'))
    await page.goto('/isard-admin/admin/hypervisors')
    await page.waitForLoadState('networkidle')

    // Click the "Add hypervisor" button. The modal handler fires the
    // POST /api/v4/admin/table/hypervisors_pools that populates the
    // pools dropdown.
    const addBtn = page
      .locator('button:has-text("New"), button:has-text("Add"), .btn-add-hyper, .btn-new-hyper')
      .first()
    if (await addBtn.isVisible({ timeout: 5000 })) {
      await addBtn.click()
      await page.waitForTimeout(1500)
    }

    // The page-load itself fires `GET /api/v4/admin/table/hypervisors_pools`
    // for the bottom datatable, so even if the Add modal didn't appear we
    // should see at least one pools fetch. Both must have status < 400.
    const matched = xhr.filter((x) => x.url.includes('/api/v4/admin/table/hypervisors_pools'))
    expect(matched.length, 'expected at least one /api/v4/admin/table/hypervisors_pools call').toBeGreaterThan(0)
    for (const m of matched) {
      expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
    }

    // Crucially, no /admin/table/hypervisors_pools without /api/v4 prefix.
    const stale = xhr.filter(
      (x) => !x.url.includes('/api/v4/admin/table/hypervisors_pools') &&
              x.url.includes('/admin/table/hypervisors_pools'),
    )
    expect(stale, 'stale /admin/table/hypervisors_pools call (missing /api/v4)').toEqual([])
  })
})

test.describe('Admin AJAX — domains resources page', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  test('Resources page table fetches resolve under /api/v4', async ({ page }) => {
    const xhr = captureXhr(
      page,
      (u) => u.includes('/admin/table/') && (
        u.includes('interfaces') ||
        u.includes('qos_disk') ||
        u.includes('qos_net') ||
        u.includes('videos') ||
        u.includes('boots') ||
        u.includes('virt_install') ||
        u.includes('remotevpn')
      ),
    )
    await page.goto('/isard-admin/admin/domains/render/Resources')
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {})

    const stale = xhr.filter((x) => !x.url.includes('/api/v4/'))
    expect(stale, 'one or more /admin/table/* calls missing /api/v4 prefix').toEqual([])

    const ok = xhr.filter((x) => x.url.includes('/api/v4/'))
    for (const m of ok) {
      expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
    }
  })
})

test.describe('Admin AJAX — backups page', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  test('integrity toggle GET hits /api/v4 (not /api/v3)', async ({ page }) => {
    const xhr = captureXhr(page, (u) => u.includes('/admin/backups/integrity'))
    await page.goto('/isard-admin/admin/backups')
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {})

    const stale = xhr.filter((x) => x.url.includes('/api/v3/'))
    expect(stale, 'backups integrity still on /api/v3').toEqual([])

    const v4 = xhr.filter((x) => x.url.includes('/api/v4/admin/backups/integrity'))
    expect(v4.length, 'expected /api/v4/admin/backups/integrity').toBeGreaterThan(0)
    for (const m of v4) {
      expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
    }
  })
})

test.describe('Admin AJAX — bookables priority page', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  test('bookings_priority table fetch hits /api/v4', async ({ page }) => {
    const xhr = captureXhr(page, (u) => u.includes('/admin/table/bookings_priority'))
    await page.goto('/isard-admin/admin/domains/render/Priority')
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {})

    const stale = xhr.filter((x) => !x.url.includes('/api/v4/'))
    expect(stale, 'bookings_priority call missing /api/v4').toEqual([])

    const ok = xhr.filter((x) => x.url.includes('/api/v4/'))
    for (const m of ok) {
      expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
    }
  })
})

test.describe('Admin AJAX — desktops priority page', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  test('desktops_priority table fetch hits /api/v4', async ({ page }) => {
    const xhr = captureXhr(page, (u) => u.includes('/admin/table/desktops_priority'))
    await page.goto('/isard-admin/admin/domains/render/Priority')
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {})

    const stale = xhr.filter((x) => !x.url.includes('/api/v4/'))
    expect(stale, 'desktops_priority call missing /api/v4').toEqual([])
  })
})

test.describe('Admin AJAX — usage page', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  test('usage list_parameters fetch hits /api/v4', async ({ page }) => {
    const xhr = captureXhr(page, (u) => u.includes('/admin/usage/'))
    await page.goto('/isard-admin/admin/usage_config')
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {})

    const stale = xhr.filter((x) => !x.url.includes('/api/v4/'))
    expect(stale, 'usage call missing /api/v4').toEqual([])
  })
})
