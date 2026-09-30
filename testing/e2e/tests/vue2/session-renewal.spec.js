// Vue 2 (old-frontend) — a session that can no longer be renewed.
// manager02 is used by no other spec: this one ends its session.

import { test, expect, loginHelpers } from '../../fixtures/login.js'

const API_RE = /\/api\/v4\//

test.describe('Vue 2 — a session that cannot be renewed', () => {
  test('renews once, sends nothing with the dead token and tells the user', async ({
    browser,
    users,
    categories,
  }) => {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true })
    const page = await ctx.newPage()
    await page.clock.install()
    await loginHelpers.login(page, users.manager02, categories)
    await page.goto('/desktops')
    await page.waitForFunction(
      () => !!document.getElementById('app')?.__vue__?.$store?.getters?.getSession,
    )

    const exp = await page.evaluate(() => {
      const token = document.getElementById('app').__vue__.$store.getters.getSession
      return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).exp
    })

    let renewCalls = 0
    await page.route('**/authentication/renew', (route) => {
      renewCalls += 1
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'invalid_session', msg: 'session expired' }),
      })
    })
    await page.route('**/authentication/logout', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }),
    )

    await page.clock.setSystemTime(new Date((exp + 3600) * 1000))

    const sent = []
    page.on('request', (req) => {
      if (API_RE.test(req.url())) sent.push(`${req.method()} ${new URL(req.url()).pathname}`)
    })

    // Background reads firing together, as when a sleeping tab wakes up.
    await page.evaluate(() => {
      const s = document.getElementById('app').__vue__.$store
      s.dispatch('fetchItemsInRecycleBin')
      s.dispatch('fetchStatusBarNotification').catch(() => {})
      s.dispatch('fetchDesktops')
    })

    await page.waitForTimeout(3000)
    const modal = await page.evaluate(() => {
      const m = document.getElementById('app').__vue__.$store.getters.getExpiredSessionModal
      return { show: m.show, kind: m.kind }
    })

    expect.soft(modal, 'the user is told the session ended').toEqual({ show: true, kind: 'max-renew-time' })
    await expect.soft(page.locator('.modal-header.bg-red')).toBeVisible()

    expect.soft(renewCalls, 'renewals sent for one expired session').toBe(1)
    expect.soft(sent, 'API requests sent after the renewal failed').toEqual([])
    expect.soft(new URL(page.url()).pathname).not.toMatch(/^\/login/)

    await ctx.close()
  })
})
