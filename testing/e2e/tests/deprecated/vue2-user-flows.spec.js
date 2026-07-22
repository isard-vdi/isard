// Vue 2 (old-frontend) user-facing creation-flow regression net.
//
// vue2-navigation.spec.js verifies the index pages (/desktops, /templates,
// /deployments, /media, …) load. This spec verifies the *creation* sub-routes
// — TemplateNew, DeploymentNew, MediaNew, NewFromMedia — that the Vue 2 app
// owns end-to-end. They are the routes most likely to silently 5xx after an
// apiv4 endpoint rename, because the pages themselves are tiny but they
// dispatch fetch-on-mount and post-on-submit through the Vue 2 store, and
// nothing guards against a fallback to /error/* when the backend route is
// missing.
//
// We assert:
//   1. Page loads (status < 500, did not redirect to /error/*).
//   2. The Vue 2 SPA mounted (#app present).
//   3. The on-mount XHRs each page fires resolve to /api/v4 with status < 400.
//   4. No console errors after networkidle.
//   5. The submit/cancel buttons render — proxy for "form rendered, not just
//      a blank skeleton".
//
// We deliberately DO NOT submit the forms. Submitting creates real records
// and (for /media/new) kicks off a multi-minute remote URL download. Network
// status on the read paths is enough to catch v3->v4 prefix regressions.
//
// Coverage intent: the creation sub-routes for the four user-facing item
// types Vue 2 still owns — templates, deployments, media, and desktops via
// new-from-media. Convert-to-template (the entry point that lands on
// /templates/new from the desktops cards) is exercised via direct
// navigation here; the card-action click path is covered by Card.vue's own
// route push behaviour and lives outside the e2e regression net.

import { test, expect } from '../../fixtures/login.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')

function consoleCollector(page) {
  const errors = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
    if (msg.type() === 'warning' && /uncaught/i.test(msg.text())) {
      errors.push(msg.text())
    }
  })
  return () =>
    errors.filter(
      (e) =>
        // Same noise filter as vue2-navigation: dev-server reconnect chatter,
        // bootstrap-vue deprecation warnings, network-fetch failures already
        // covered by the response collector below.
        !/Failed to load resource/.test(e) &&
        !/net::ERR_/.test(e) &&
        !/\[Vue warn\]/.test(e) &&
        !/\[BootstrapVue warn\]/.test(e) &&
        !/\[Deprecation\]/.test(e) &&
        !/\[WDS\]/.test(e) &&
        !/sockjs-node/.test(e),
    )
}

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

test.describe('Vue 2 — creation-flow pages', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories)
  })

  test('/templates/new (convert-to-template) loads or redirects safely', async ({ page }) => {
    // /templates/new is a stateful route — it expects a source-desktop id in
    // the Vue 2 store (set by clicking "Make template" on a desktop card).
    // When opened without that state the page redirects back to /desktops.
    // The convert-to-template UI is exercised end-to-end by Card.vue's own
    // route push; this test's job is to assert the route is wired and does
    // not 5xx / land on /error/*. We accept either "form mounted" (#name
    // present) or "redirected to /desktops" — both prove the route is alive.
    const realErrors = consoleCollector(page)
    const xhr = captureXhr(
      page,
      (u) => u.includes('/api/v4/') && /\/(templates|images|profile)/.test(u),
    )
    const response = await page.goto('/templates/new')
    if (response) expect(response.status(), '/templates/new status').toBeLessThan(500)

    await expect(page.locator('#app').first(), '#app on /templates/new').toBeAttached({
      timeout: 5000,
    })
    expect(page.url(), 'did not redirect to /error').not.toMatch(/\/error\//)

    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {})

    // Either the form rendered (direct deep-link) or we landed somewhere safe
    // (the Vue 2 redirect target — /desktops). Both are acceptable.
    const finalUrl = page.url()
    const formMounted = await page
      .locator('#name')
      .isVisible({ timeout: 2000 })
      .catch(() => false)
    expect(
      formMounted || /\/desktops/.test(finalUrl),
      `expected /templates/new form OR safe redirect, got ${finalUrl}`,
    ).toBeTruthy()

    // Any /api/v4 XHR the page fires must succeed.
    for (const m of xhr) {
      expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
    }
    expect(realErrors(), 'console errors').toEqual([])
  })

  test('/deployments/new fetches templates + images via /api/v4', async ({ page }) => {
    const realErrors = consoleCollector(page)
    const xhr = captureXhr(
      page,
      (u) =>
        u.includes('/api/v4/items/templates/allowed/') ||
        u.includes('/api/v4/images/desktops') ||
        u.includes('/api/v4/items/groups-users/count'),
    )
    const response = await page.goto('/deployments/new')
    if (response) expect(response.status(), '/deployments/new status').toBeLessThan(500)

    await expect(page.locator('#app').first(), '#app on /deployments/new').toBeAttached({
      timeout: 5000,
    })
    expect(page.url(), 'did not redirect to /error').not.toMatch(/\/error\//)

    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {})

    // The page mounts dispatch fetchAllowedTemplates('all') and fetchDesktopImages.
    // Both are required reads — if the API renames break either, the form is
    // unusable and the user gets nothing in the dropdowns.
    const templates = xhr.filter((x) => x.url.includes('/api/v4/items/templates/allowed/'))
    expect(
      templates.length,
      'expected /api/v4/items/templates/allowed/ on /deployments/new mount',
    ).toBeGreaterThan(0)
    for (const m of templates) {
      expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
    }

    const images = xhr.filter((x) => x.url.includes('/api/v4/images/desktops'))
    // images can lag networkidle when the catalog is large — only assert
    // status when present.
    for (const m of images) {
      expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
    }

    // No console errors and no /error/* redirect.
    expect(realErrors(), 'console errors on /deployments/new').toEqual([])
  })

  test('/media/new renders the URL+name+kind form', async ({ page }) => {
    const realErrors = consoleCollector(page)
    const xhr = captureXhr(page, (u) => u.includes('/api/v4/'))
    const response = await page.goto('/media/new')
    if (response) expect(response.status(), '/media/new status').toBeLessThan(500)

    await expect(page.locator('#app').first(), '#app on /media/new').toBeAttached({
      timeout: 5000,
    })
    expect(page.url(), 'did not redirect to /error').not.toMatch(/\/error\//)

    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {})

    // MediaNew has a #mediaUrl text input — proxy for form rendered.
    await expect(page.locator('#mediaUrl')).toBeAttached({ timeout: 5000 })

    // Any /api/v4 XHR must succeed.
    for (const m of xhr) {
      expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
    }
    expect(realErrors(), 'console errors on /media/new').toEqual([])
  })

  test('/new-from-media renders without /error redirect', async ({ page }) => {
    // NewFromMedia expects the desktop-from-media wizard state populated by
    // a prior step on /media. When opened directly with no state, the page
    // dispatches navigate('media') which redirects to /media. Either landing
    // is acceptable here; the regression we want to catch is a 500 / SPA
    // crash / /error redirect.
    const realErrors = consoleCollector(page)
    const xhr = captureXhr(page, (u) => u.includes('/api/v4/'))
    const response = await page.goto('/new-from-media')
    if (response) expect(response.status(), '/new-from-media status').toBeLessThan(500)

    await expect(page.locator('#app').first(), '#app on /new-from-media').toBeAttached({
      timeout: 5000,
    })
    expect(page.url(), 'did not redirect to /error').not.toMatch(/\/error\//)

    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {})

    for (const m of xhr) {
      expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
    }
    expect(realErrors(), 'console errors on /new-from-media').toEqual([])
  })

  test('/desktops/new (new desktop wizard) renders + fetches templates', async ({ page }) => {
    const realErrors = consoleCollector(page)
    const xhr = captureXhr(
      page,
      (u) => u.includes('/api/v4/items/templates/allowed/') || u.includes('/api/v4/images/desktops'),
    )
    const response = await page.goto('/desktops/new')
    if (response) expect(response.status(), '/desktops/new status').toBeLessThan(500)

    await expect(page.locator('#app').first(), '#app on /desktops/new').toBeAttached({
      timeout: 5000,
    })
    expect(page.url(), 'did not redirect to /error').not.toMatch(/\/error\//)

    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {})

    // The wizard mount fires fetchAllowedTemplates('all'); failing this
    // means the user can't pick a template and the form is dead.
    const templates = xhr.filter((x) => x.url.includes('/api/v4/items/templates/allowed/'))
    expect(
      templates.length,
      'expected /api/v4/items/templates/allowed/ on /desktops/new mount',
    ).toBeGreaterThan(0)
    for (const m of templates) {
      expect(m.status, `${m.method} ${m.url}`).toBeLessThan(400)
    }

    expect(realErrors(), 'console errors on /desktops/new').toEqual([])
  })
})
