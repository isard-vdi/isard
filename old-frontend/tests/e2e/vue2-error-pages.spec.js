// @ts-check
//
// Error pages and 404 fallback smoke.
//
// /error/:code renders a styled error page (legacy /error/maintenance,
// /error/notfound). The * route catches any unmatched path and
// either redirects to /desktops (authenticated) or /login.
//
// Spec asserts none of these crash the SPA.

import { test, expect } from '@playwright/test'

test.describe('Vue 2 error / fallback routes', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/isard-admin/logout')
  })

  test('/error/notfound renders error page', async ({ page }) => {
    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const response = await page.goto('/error/notfound')
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // Title shouldn't leak the i18n key.
    const title = await page.title()
    expect(title).not.toMatch(/^router\./)

    const realErrors = consoleErrors.filter(
      (e) => !/Failed to load resource/.test(e) && !/net::ERR_/.test(e)
    )
    expect(realErrors, 'console errors on /error/notfound').toEqual([])
  })

  test('/error/maintenance renders error page', async ({ page }) => {
    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const response = await page.goto('/error/maintenance')
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    const title = await page.title()
    expect(title).not.toMatch(/^router\./)

    const realErrors = consoleErrors.filter(
      (e) => !/Failed to load resource/.test(e) && !/net::ERR_/.test(e)
    )
    expect(realErrors).toEqual([])
  })

  test('unknown route falls through to 404 view or /login', async ({ page }) => {
    const response = await page.goto('/this-route-does-not-exist')
    if (response) expect(response.status()).toBeLessThan(500)
    await page.waitForLoadState('networkidle')

    // Either the SPA renders a NotFound view or the router-level
    // guard pushed us to /login. Both are acceptable; what we don't
    // want is an HTTP 5xx or a broken white page.
    const url = page.url()
    expect(
      url,
      `expected /login redirect or a NotFound view for unknown route, got ${url}`
    ).toMatch(/\/(login|error|desktops|isard-admin)/)
  })
})
