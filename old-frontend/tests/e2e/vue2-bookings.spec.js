// @ts-check
//
// Vue 2 bookings smoke. The /booking/* routes are **Vue-2-only** today —
// Vue 3 has no bookings UI. Every hour the reservations feature spends
// on Vue 2 is an hour it's regression-exposed, so pin at least the
// summary list + the calendar mount.

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 bookings', () => {
  test('/booking/summary renders the bookings list page', async ({ page, login }) => {
    const response = await page.goto('/booking/summary')
    if (response) expect(response.status()).toBeLessThan(400)

    // The summary page is the one linked from the navbar "Bookings" entry.
    // If the i18n title key leaks, we know the SPA failed to hydrate.
    const title = await page.title()
    expect(title).not.toMatch(/^router\./)

    // #content is the b-container wrapping every authenticated page.
    // Its presence tells us the layout rendered.
    await expect(page.locator('#content')).toBeVisible()
  })

  test('/booking/summary has no console error on first load', async ({ page, login }) => {
    const errors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
      if (msg.type() === 'warning' && /\[Vue warn\]/.test(msg.text())) {
        errors.push(msg.text())
      }
    })
    await page.goto('/booking/summary')
    await page.waitForLoadState('networkidle')

    const realErrors = errors.filter(
      (e) => !/Failed to load resource/.test(e) && !/net::ERR_/.test(e)
    )
    expect(realErrors).toEqual([])
  })
})
