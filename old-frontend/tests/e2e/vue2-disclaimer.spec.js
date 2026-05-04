// @ts-check
//
// /disclaimer page smoke.
//
// The disclaimer route is reachable when a user's session token has
// type ``disclaimer-acknowledgement-required`` (router redirects
// them there from any other page). Without that session we just
// load the page directly to assert it renders.

import { test, expect } from '@playwright/test'

test.describe('Vue 2 disclaimer page', () => {
  test('/disclaimer renders without errors', async ({ page }) => {
    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    // Don't authenticate — the page renders the disclaimer text
    // regardless of session state.
    await page.goto('/isard-admin/logout')
    const response = await page.goto('/disclaimer')
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // Page should have a visible heading or content area.
    // The exact text comes from i18n + admin-configurable
    // ``views.disclaimer.title`` so match permissively.
    const title = await page.title()
    expect(title, 'disclaimer page title').not.toMatch(/^router\./)

    const realErrors = consoleErrors.filter(
      (e) => !/Failed to load resource/.test(e) && !/net::ERR_/.test(e)
    )
    expect(realErrors, 'console errors on /disclaimer').toEqual([])
  })
})
