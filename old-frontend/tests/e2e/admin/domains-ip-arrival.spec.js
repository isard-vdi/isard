// @ts-check
//
// Pin the WS-driven IP-arrival flow on the Flask webapp admin
// /isard-admin/admin/domains DataTables view.
//
// The Flask admin page subscribes to ``desktop_data`` on the
// /administrators namespace. Handler chain
// (webapp/static/admin/js/desktops.js):
//
//   socket.on('desktop_data', desktopAddUpdateSocketHandle)
//     → if data.viewer.guest_ip arrives AND row didn't already have
//       one, call ``viewerButtonsIP(id, ip)`` which re-renders the
//       row's viewer buttons via ``setViewerButtons(id)``
//     → ``dtUpdateInsert(domains_table, mergedData)`` merges the
//       partial payload into the cached row and redraws.
//
// This spec doesn't rely on the column having an explicit "IP" cell
// (it doesn't); the assertion targets the row's underlying data via
// the DataTables API, which is the source of truth the visual cells
// are rendered from. Same fixture + mutation path as the Vue 2 /
// Vue 3 IP-arrival specs.

import { expect } from '@playwright/test'
import { ApiHelper } from '../helpers/api'
import { test } from '../login-page'

const FIXTURE_ID = 'ws-ip-arrival-fixture-0001'
const FIXTURE_IP = '10.99.99.44'

test.describe.configure({ mode: 'serial' })

test.describe('Admin /domains WS IP-arrival', () => {
  /** @type {ApiHelper} */
  let api

  test.beforeAll(async ({ baseURL }) => {
    api = new ApiHelper(baseURL ?? 'https://localhost')
    await api.login(
      process.env.E2E_ADMIN_USERNAME ?? 'admin',
      process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI',
      'default'
    )
    await api.setDesktopGuestIp(FIXTURE_ID, null)
    await api.waitForDesktopIp(FIXTURE_ID, null, 5000)
  })

  test.afterAll(async () => {
    if (api) {
      try { await api.setDesktopGuestIp(FIXTURE_ID, null) } catch (e) {}
    }
  })

  test('desktop_data event flips DataTable row viewer.guest_ip', async ({ page, login }) => {
    // Attach the WS listener BEFORE any navigation. ``page.on`` only
    // fires for NEW websockets; sockets opened before the listener was
    // attached are missed.
    /** @type {string[]} */
    const desktopDataFrames = []
    page.on('websocket', (ws) => {
      ws.on('framereceived', (frame) => {
        const payload = typeof frame.payload === 'string'
          ? frame.payload
          : frame.payload?.toString('utf8') ?? ''
        if (/desktop_data/.test(payload) && payload.includes(FIXTURE_ID)) {
          desktopDataFrames.push(payload)
        }
      })
    })

    await page.goto('/isard-admin/admin/domains/render/Desktops')
    await page.waitForLoadState('networkidle')

    // The DataTable mounts under #domains. Wait for jQuery + DataTables
    // to wire up the global ``domains_table`` ref (used by all the
    // socket handlers).
    await page.waitForFunction(
      () => typeof window.domains_table?.row === 'function',
      { timeout: 15000 }
    )

    // Wait for the fixture row to land in the DataTable. Admin sees
    // all desktops regardless of owner, so it must be visible.
    const readRowIp = () =>
      page.evaluate((id) => {
        // @ts-ignore — domains_table is a jQuery DataTables instance.
        const row = window.domains_table?.row('#' + id)
        if (!row || typeof row.data !== 'function') return { error: 'no-row-api' }
        const data = row.data()
        if (!data) return { missing: true }
        return {
          ip: data?.viewer?.guest_ip ?? null,
          status: data?.status ?? null
        }
      }, FIXTURE_ID)

    let snapshot = await readRowIp()
    for (let i = 0; i < 30 && (snapshot.missing || snapshot.error); i += 1) {
      await page.waitForTimeout(500)
      snapshot = await readRowIp()
    }
    expect(
      snapshot,
      `fixture row ${FIXTURE_ID} must appear in DataTable for admin`
    ).toMatchObject({ ip: null })

    // Drive the wg_addr-equivalent DB update.
    await api.setDesktopGuestIp(FIXTURE_ID, FIXTURE_IP)

    // Wait for the row data to flip.
    let after = await readRowIp()
    for (let i = 0; i < 40 && after.ip !== FIXTURE_IP; i += 1) {
      await page.waitForTimeout(250)
      after = await readRowIp()
    }
    expect(after).toMatchObject({ ip: FIXTURE_IP })

    // At least one ``desktop_data`` WS frame carrying the new IP.
    expect(
      desktopDataFrames.some((f) => f.includes(FIXTURE_IP)),
      `expected ≥1 desktop_data WS frame carrying ${FIXTURE_IP}`
    ).toBeTruthy()
  })
})
