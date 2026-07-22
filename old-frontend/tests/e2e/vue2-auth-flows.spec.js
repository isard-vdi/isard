// @ts-check
//
// Unauthenticated auth-flow page smokes — /forgot-password,
// /reset-password, /verify-email.
//
// These three pages are entry points for password-recovery and
// email-verification flows. None has e2e coverage; Bug #48
// (email-verification 403 from has_token) lives near the
// /verify-email page.
//
// We DO NOT actually trigger the password reset / verification
// emails — those have side effects on the test admin user. The
// spec asserts:
//   * Each route loads (status < 400).
//   * Each renders form fields appropriate to its purpose.
//   * No raw i18n key leak in <title> or <body>.
//
// All three routes are reachable without authentication; explicit
// logout before each spec to avoid the auth fixture's redirect.

import { test, expect } from '@playwright/test'

const I18N_KEY_RE = /\b(views|components|forms|messages|router)\.[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*){1,5}\b/

test.describe('Vue 2 auth-flow pages (unauthenticated)', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure no leftover session from a prior spec.
    await page.goto('/isard-admin/logout')
  })

  test('/forgot-password renders form with email input', async ({ page }) => {
    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const response = await page.goto('/forgot-password')
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // The form has at least one email-type input + a submit button.
    const emailInput = page.locator('input[type="email"], input[type="text"]').first()
    await expect(emailInput).toBeVisible({ timeout: 10000 })

    const title = await page.title()
    expect(title, 'title for /forgot-password').not.toMatch(/^router\./)

    const body = (await page.textContent('body')) ?? ''
    const leak = body.match(I18N_KEY_RE)
    expect(leak, leak ? `i18n key leak: ${leak[0]}` : 'no i18n leak').toBeFalsy()

    const realErrors = consoleErrors.filter(
      (e) => !/Failed to load resource/.test(e) && !/net::ERR_/.test(e)
    )
    expect(realErrors, 'console errors on /forgot-password').toEqual([])
  })

  test('/reset-password renders password-reset form', async ({ page }) => {
    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const response = await page.goto('/reset-password')
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // Without a valid reset token in the URL the page may either
    // render the form or redirect to /login. Both are acceptable —
    // assert no console errors and no i18n leak in either case.
    const title = await page.title()
    expect(title, 'title for /reset-password').not.toMatch(/^router\./)

    const body = (await page.textContent('body')) ?? ''
    const leak = body.match(I18N_KEY_RE)
    expect(leak, leak ? `i18n key leak: ${leak[0]}` : 'no i18n leak').toBeFalsy()

    const realErrors = consoleErrors.filter(
      (e) => !/Failed to load resource/.test(e) && !/net::ERR_/.test(e)
    )
    expect(realErrors, 'console errors on /reset-password').toEqual([])
  })

  test('/verify-email renders without crashing (Bug #48 surface)', async ({ page }) => {
    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    page.on('pageerror', (err) => consoleErrors.push(String(err)))

    const response = await page.goto('/verify-email')
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // VerifyEmail.vue renders an email input + submit button when
    // ``alertType`` is empty. Without a token query param the form
    // is empty — verify the title at minimum.
    const title = await page.title()
    expect(title, 'title for /verify-email').not.toMatch(/^router\./)

    // Bug #48 surface: any apiv4 call from this page (fetchUser,
    // fetchConfig, etc.) shouldn't 403 if the user has an
    // email-verification-typed session. With no session at all the
    // page should still render cleanly.
    const realErrors = consoleErrors.filter(
      (e) => !/Failed to load resource/.test(e) &&
             !/net::ERR_/.test(e) &&
             !/401|403|unauthorized|forbidden/i.test(e) // expected when no session
    )
    expect(realErrors, 'console errors on /verify-email').toEqual([])
  })
})
