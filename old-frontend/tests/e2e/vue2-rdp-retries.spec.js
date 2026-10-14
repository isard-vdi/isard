// @ts-check
//
// The RDP viewer retries a refused connection a bounded number of times.
// guacd is replaced by a scripted websocket: it opens the tunnel, sends a
// sync (which moves the Guacamole client to its connected state before the
// guest has negotiated anything) and then reports the guest's refusal.

import { expect, test } from '@playwright/test'

const MAX_RETRIES = 3

function encode (...args) {
  return args.map((a) => `${a.length}.${a}`).join(',') + ';'
}

function unsignedJwt (payload) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url')
  return `${b64({ alg: 'none', typ: 'JWT' })}.${b64(payload)}.`
}

async function openViewer (page, context, baseURL, errorCode, errorMessage) {
  const url = new URL(baseURL || 'https://localhost')
  const webViewer = {
    host: url.host,
    vmHost: 'guest.invalid',
    vmUsername: 'isard',
    vmPassword: 'secret',
    exp: Math.floor(Date.now() / 1000) + 3600
  }
  await context.addCookies([
    { name: 'browser_viewer', value: unsignedJwt({ web_viewer: webViewer }), url: url.origin },
    { name: 'viewerToken', value: 'test-token', url: url.origin }
  ])
  await page.route('**/api/v4/item/user/owns-desktop', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  )

  const attempts = { count: 0 }
  await page.routeWebSocket(/\/websocket-tunnel/, (ws) => {
    attempts.count++
    ws.send(encode('', '00000000-0000-4000-8000-000000000000'))
    ws.send(encode('sync', '1'))
    setTimeout(() => {
      ws.send(encode('error', errorMessage, String(errorCode)))
      ws.close()
    }, 200)
  })

  await page.goto('/rdp')
  return attempts
}

test.describe('Vue 2 RDP viewer retries', () => {
  test.setTimeout(90000)

  test('gives up after the maximum retries when the guest refuses', async ({ page, context, baseURL }) => {
    const attempts = await openViewer(page, context, baseURL, 0x0207, 'Server refused connection (wrong security type?)')

    await expect(page.locator('.modal-rdp h2')).toHaveText(/not accepting RDP/i, { timeout: 45000 })
    await page.waitForTimeout(8000)
    expect(attempts.count).toBe(MAX_RETRIES + 1)
  })

  test('does not blame the credentials for a failed security negotiation', async ({ page, context, baseURL }) => {
    await openViewer(page, context, baseURL, 0x0301, 'Security negotiation failed (wrong security type?)')

    await expect(page.locator('.modal-rdp h2')).toHaveText(/not accepting RDP/i, { timeout: 45000 })
  })

  test('tells the stored credentials were rejected', async ({ page, context, baseURL }) => {
    const attempts = await openViewer(page, context, baseURL, 0x0301, 'Authentication failure (invalid credentials?)')

    await expect(page.locator('.modal-rdp h2')).toHaveText(/credentials rejected/i, { timeout: 45000 })
    expect(attempts.count).toBe(MAX_RETRIES + 1)
  })
})
