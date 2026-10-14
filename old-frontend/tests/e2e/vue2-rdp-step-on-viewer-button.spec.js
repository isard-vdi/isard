// @ts-check
//
// The RDP verification step of a desktop is shown on its RDP viewer button
// (spinner or warning icon, the text as tooltip) and never as extra text in
// the card, so a card keeps the same height whatever the step. The desktops
// list is served by a route mock, so no hypervisor or guest is needed.

import { expect } from '@playwright/test'
import { test } from './login-page'

const EVIL = '<img src=x onerror="window.__rdpXss=1">'

function desktop (rdp) {
  return {
    id: 'rdp-step-fixture-0001',
    name: 'RDP step fixture',
    description: '',
    status: 'Started',
    state: 'Started',
    type: 'persistent',
    viewers: ['browser-rdp', 'browser-vnc'],
    ip: '10.2.0.75',
    rdp,
    interfaces: ['default', 'wireguard'],
    image: { id: 'stock', url: '/assets/img/desktops/stock/1.jpg', type: 'stock' },
    permissions: [],
    editable: true,
    tag: false,
    needs_booking: false
  }
}

async function cardFor (page, rdp) {
  await page.route('**/item/user/desktops', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([desktop(rdp)]) })
  )
  await page.goto('/desktops')
  const card = page.locator('.card').filter({ hasText: 'RDP step fixture' }).first()
  await expect(card).toBeVisible({ timeout: 15000 })
  return card
}

test.describe('Vue 2 RDP step on the viewer button', () => {
  test('the card keeps its height in every RDP step', async ({ page, login }) => {
    const heights = {}
    for (const [name, rdp] of Object.entries({
      none: null,
      waiting: { state: 'waiting' },
      refused: { state: 'refused', reason: 'ssl_not_allowed_by_server' },
      unverified: { state: 'unverified' },
      lastFailed: { state: 'ready', last: { connected: false, result: 'auth_failed' } }
    })) {
      const card = await cardFor(page, rdp)
      heights[name] = Math.round((await card.boundingBox()).height)
      await page.unroute('**/item/user/desktops')
    }
    expect(new Set(Object.values(heights)).size, JSON.stringify(heights)).toBe(1)
  })

  test('the step is the tooltip of the RDP button', async ({ page, login }) => {
    const card = await cardFor(page, { state: 'refused', reason: 'ssl_not_allowed_by_server' })
    await expect(card.locator('.rdp-status-error')).toBeVisible()
    await card.locator('.dropdown-default-text').hover()
    await expect(page.locator('.tooltip')).toContainText(/refuse/i)
    await expect(page.locator('.tooltip')).not.toContainText('ssl_not_allowed_by_server')
    await expect(card).not.toContainText(/refuse/i)
  })

  test('a value from the API is never rendered as HTML', async ({ page, login }) => {
    const card = await cardFor(page, { state: 'refused', reason: EVIL })
    await card.locator('.dropdown-default-text').hover()
    await expect(page.locator('.tooltip')).toBeVisible()
    await expect(page.locator('.tooltip')).not.toContainText('<img')
    expect(await page.locator('img[src="x"]').count()).toBe(0)
    expect(await page.evaluate(() => window.__rdpXss)).toBeUndefined()

    await page.unroute('**/item/user/desktops')
    const card2 = await cardFor(page, { state: EVIL })
    await expect(card2.locator('.rdp-status-error')).toHaveCount(0)
    expect(await page.locator('img[src="x"]').count()).toBe(0)
  })
})
