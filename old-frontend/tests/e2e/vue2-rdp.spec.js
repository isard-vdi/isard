// @ts-check
//
// Vue 2 RDP viewer smoke. /rdp is the Guacamole-RDP client landing page
// — Vue-2-only today. Without a valid direct-viewer token it shows the
// retry modal; with one it connects. We only pin that the viewer shell
// loads without a Vue/Router crash.

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 RDP viewer', () => {
  test('/rdp renders the viewport shell', async ({ page, login }) => {
    const errors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
      if (msg.type() === 'warning' && /\[Vue warn\]/.test(msg.text())) {
        errors.push(msg.text())
      }
    })

    const response = await page.goto('/rdp')
    if (response) expect(response.status()).toBeLessThan(400)

    // src/views/Rdp.vue top-level is `.viewport-rdp`.
    await expect(page.locator('.viewport-rdp')).toBeVisible({ timeout: 10000 })

    // Guacamole pulls in WebSocket + WebGL + audio APIs. Ignore the
    // network-origin noise and the expected "no token" complaints; fail
    // on genuine Vue warnings.
    const realErrors = errors.filter(
      (e) =>
        !/Failed to load resource/.test(e) &&
        !/net::ERR_/.test(e) &&
        !/token/i.test(e) &&
        !/websocket/i.test(e)
    )
    expect(realErrors).toEqual([])
  })
})
