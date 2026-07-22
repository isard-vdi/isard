// @ts-check
//
// Pin the WS-driven IP-arrival flow on Vue 2's ``/desktops`` page.
//
// In production a desktop with a wireguard interface comes up as
// WaitingIP. dnsmasq DHCPs it, the dnsmasq hook posts to
//   POST /api/v4/admin/hypervisor/vm/wg_addr
// which writes ``viewer.guest_ip`` on the domain row. The changefeed
// pluck includes ``viewer``, so the change-handler emits a
// ``desktop_update`` event on /userspace (room=user) carrying the new
// ip. Vue 2's ``socket_desktopUpdate`` action runs ``parseDesktop``
// with ``partial: true`` and merges the new ``ip`` into the Vuex
// row — the card then renders the IP and unlocks RDP viewer buttons.
//
// Symptom this pins (April 2026 bug report): Slax desktop got an IP
// via DHCP but the WS didn't update the card; refresh did. Root cause
// turned out to live in the Vue 3 frontend (ViewerSelect's frozen
// loading ref + the cloneDeepUnref(getXOptions()) misuse), but the
// Vue 2 path works today — this spec is a parity guard against
// regressing ``socket_desktopUpdate`` or ``parseDesktop({partial:
// true})``.
//
// Cost: ~5s wall, no hypervisor needed. Mutates a seeded fixture
// desktop's viewer.guest_ip via the admin table-update endpoint, the
// same code path the wg_addr endpoint ultimately drives.

import { test as base, expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { PageLogin } from './login-page'
import { fixture as baseFixture } from './base'

const FIXTURE_ID = 'ws-ip-arrival-fixture-0001'
const FIXTURE_IP = '10.99.99.42'

// Custom fixture set: bypass the e2e_admin pool because the seeded
// fixture is owned by ``local-default-admin-admin`` (bootstrap admin),
// and Vue 2's /desktops only lists the logged-in user's own rows.
const test = base.extend({
  ...baseFixture,
  bootstrapLogin: async ({ page }, use) => {
    const login = new PageLogin(page)
    await login.goto()
    await login.form(
      process.env.E2E_ADMIN_USERNAME ?? 'admin',
      process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI'
    )
    await login.finished()
    await use(login)
  }
})

test.describe.configure({ mode: 'serial' })

test.describe('Vue 2 WS desktop IP-arrival', () => {
  /** @type {ApiHelper} */
  let api

  test.beforeAll(async ({ baseURL }) => {
    api = new ApiHelper(baseURL ?? 'https://localhost')
    await api.login(
      process.env.E2E_ADMIN_USERNAME ?? 'admin',
      process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI',
      'default'
    )
    // Park the fixture at WaitingIP (no ip) before the test runs.
    await api.setDesktopGuestIp(FIXTURE_ID, null)
    await api.waitForDesktopIp(FIXTURE_ID, null, 5000)
  })

  test.afterAll(async () => {
    if (api) {
      try { await api.setDesktopGuestIp(FIXTURE_ID, null) } catch (e) {}
    }
  })

  test('socket_desktopUpdate merges viewer.guest_ip into the Vuex row', async ({
    page,
    bootstrapLogin
  }) => {
    // Attach the WS listener BEFORE any navigation so we catch the
    // socket.io connection that opens on /desktops mount. ``page.on``
    // only fires for NEW websockets — listeners attached after the
    // connection is already open miss every frame.
    /** @type {string[]} */
    const desktopUpdateFrames = []
    page.on('websocket', (ws) => {
      ws.on('framereceived', (frame) => {
        const payload = typeof frame.payload === 'string'
          ? frame.payload
          : frame.payload?.toString('utf8') ?? ''
        if (/desktop_update/.test(payload) && payload.includes(FIXTURE_ID)) {
          desktopUpdateFrames.push(payload)
        }
      })
    })

    await page.goto('/desktops')
    await page.waitForLoadState('networkidle')

    // Confirm the fixture row is in the Vuex store before we mutate.
    const readVuexIp = () =>
      page.evaluate((id) => {
        const root = document.querySelector('#app')
        // __vue__ is the Vue 2 root instance — store is exposed via $store.
        const store = root && (/** @type {any} */ (root)).__vue__?.$store
        if (!store) return { error: 'no-store' }
        const d = store.getters.getDesktop?.(id) ||
          (store.state?.desktops?.desktops || []).find((x) => x.id === id)
        return d ? { ip: d.ip ?? null, status: d.status ?? null } : { missing: true }
      }, FIXTURE_ID)

    // Poll for the desktop to land in the store (a fresh /desktops load
    // fetches via REST; the row arrives async after networkidle).
    let snapshot = await readVuexIp()
    for (let i = 0; i < 20 && (snapshot.missing || snapshot.error); i += 1) {
      await page.waitForTimeout(500)
      snapshot = await readVuexIp()
    }
    expect(snapshot, `fixture desktop ${FIXTURE_ID} must be in Vuex`)
      .toMatchObject({ ip: null })

    // Flip the IP via the admin endpoint — same DB write path the
    // dnsmasq hook drives in production.
    await api.setDesktopGuestIp(FIXTURE_ID, FIXTURE_IP)

    // Wait for the WS-driven Vuex update.
    let after = await readVuexIp()
    for (let i = 0; i < 40 && after.ip !== FIXTURE_IP; i += 1) {
      await page.waitForTimeout(250)
      after = await readVuexIp()
    }
    expect(after).toMatchObject({ ip: FIXTURE_IP })

    // The Vue 2 card renders ``IP: <ip>`` in the body for Started
    // desktops with an ip. The page-level text should now contain
    // the new IP literal.
    await expect(page.locator('body')).toContainText(FIXTURE_IP, {
      timeout: 5000
    })

    // And at least one captured WS frame must carry the new IP.
    expect(
      desktopUpdateFrames.some((f) => f.includes(FIXTURE_IP)),
      `expected ≥1 desktop_update WS frame carrying ${FIXTURE_IP}, ` +
        `got ${desktopUpdateFrames.length} frames`
    ).toBeTruthy()
  })
})
