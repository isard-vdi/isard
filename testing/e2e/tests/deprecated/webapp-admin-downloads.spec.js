// Webapp/Flask admin /admin/updates page (Slax + media + virt_install +
// videos + viewers downloads).
//
// The page renders five separate jQuery DataTables, each loading from
// /api/v4/admin/downloads/<type>. Each row exposes a Download/Abort/Delete
// button that posts to /api/v4/admin/downloads/<action>/<type>/<id>.
//
// We deliberately do NOT click Download — that would actually queue a
// real download on the backend. Instead we assert that the read paths
// (page-load GETs + the registration check) are all hitting /api/v4
// with status < 400. Catches the regression where the v3->v4 admin
// migration drops the prefix and silently falls back to the SPA 200.

import { test, expect } from '../../fixtures/login.js'
import { bridgeAdminSession } from '../../fixtures/common.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')

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

test.describe('Admin AJAX — updates (downloads) page', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
    await bridgeAdminSession(page)
  })

  test('downloads page table fetches all hit /api/v4', async ({ page }) => {
    const xhr = captureXhr(page, (u) => u.includes('/admin/downloads'))
    await page.goto('/isard-admin/admin/updates')
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {})

    // We expect the registration check + at least one of the five
    // DataTable endpoints to fire on initial render.
    //
    // Both endpoints depend on the deployment being registered with
    // the upstream catalog. On a fresh-from-scratch stack that hasn't
    // been registered yet, apiv4 deliberately returns 428 Precondition
    // Required ("IsardVDI hasn't been registered yet."). That is a
    // documented, expected response — not a bug — so allow 428 in
    // addition to 2xx/3xx. The point of this test is to verify the
    // URL prefix is /api/v4, not that the data is non-empty (the
    // separate `stale` assertion below is the one that actually
    // catches the legacy-prefix regression).
    const expectedReads = [
      '/api/v4/admin/downloads',           // registration probe
      '/api/v4/admin/downloads/domains',   // Slax / desktops downloads
    ]
    for (const path of expectedReads) {
      const matched = xhr.filter((x) => x.url.includes(path))
      expect(matched.length, `expected at least one ${path} call`).toBeGreaterThan(0)
      for (const m of matched) {
        // 428 = "not registered yet" — the registration probe always
        // returns this on a fresh stack and is then cleared by clicking
        // the register button (covered in the next test).
        if (m.status === 428) continue
        expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
      }
    }

    // No legacy-prefix downloads URL (would land on SPA fallback as 200
    // and silently break the buttons).
    const stale = xhr.filter(
      (x) => !x.url.includes('/api/v4/') && /\/admin\/downloads\b/.test(x.url),
    )
    expect(stale, 'one or more /admin/downloads/* calls missing /api/v4 prefix').toEqual([])
  })

  test('register button targets /api/v4/admin/downloads/register', async ({ page }) => {
    const xhr = captureXhr(page, (u) => u.includes('/admin/downloads/register'))
    await page.goto('/isard-admin/admin/updates')
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {})

    // The "Register" button is shown when the deployment has not yet
    // been registered with the upstream catalog. Click it if visible —
    // on an already-registered devel stack the button is hidden so the
    // POST never fires; in that case the registration check above
    // already covered the pre-action GET, which is what we care about.
    const register = page.locator('.not_registered button, .btn-register').first()
    if (await register.isVisible({ timeout: 3000 }).catch(() => false)) {
      await register.click()
      await page.waitForTimeout(1500)
    }

    // Any /admin/downloads/register call we observed must be /api/v4-prefixed.
    const stale = xhr.filter((x) => !x.url.includes('/api/v4/'))
    expect(stale, 'register call missing /api/v4 prefix').toEqual([])
  })
})
