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
      (e) =>
        !/Failed to load resource/.test(e) &&
        !/net::ERR_/.test(e) &&
        !/i18n|translation|locale|missing key/i.test(e) &&
        !/Cannot find module.*\.svg/.test(e)
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
      (e) =>
        !/Failed to load resource/.test(e) &&
        !/net::ERR_/.test(e) &&
        !/i18n|translation|locale|missing key/i.test(e) &&
        !/Cannot find module.*\.svg/.test(e)
    )
    expect(realErrors).toEqual([])
  })

  test('unknown route falls through to 404 view or /login', async ({ page }) => {
    const response = await page.goto('/this-route-does-not-exist')
    if (response) expect(response.status()).toBeLessThan(500)
    await page.waitForLoadState('networkidle')

    // Either the SPA renders a NotFound view, the router-level
    // guard pushed us to /login, or nginx serves the SPA for the
    // unknown path and the wildcard router renders NotFound in-
    // place (URL stays at /this-route-does-not-exist). Acceptable
    // outcome: page reachable (no 5xx) AND visible body matches a
    // fallback / login / NotFound copy.
    const url = page.url()
    const body = (await page.textContent('body')) ?? ''
    expect(
      body,
      `unknown route ${url} should render a NotFound / login / error fallback; ` +
        'got an unrecognised body. nginx returned no SPA index.html or the ' +
        'wildcard route is missing.'
    ).toMatch(
      /not found|404|maintenance|login|sign in|desktops|oops|something went wrong|no longer here/i
    )
  })
})
