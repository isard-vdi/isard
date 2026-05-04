// @ts-check
//
// WebSocket-driven UI updates — broadcast → list re-renders
// without page reload.
//
// Bugs #13 (visibility-flip dup row), #17 (recycle-bin restore
// ghost), #33 (recreate-deployment phantom rows) all sit on the
// websocket → store → datatable update path. The store either:
//   (a) dispatches a duplicate add when an update fires for a
//       row already in the table, or
//   (b) doesn't dispatch the remove when the entity is deleted
//       elsewhere.
//
// Spec exercises one concrete path: admin opens /desktops in
// browser, then a separate API call deletes a desktop, then the
// browser's desktop list should drop the deleted row WITHOUT a
// manual refresh (within a reasonable WS-propagation window).
//
// This is the broadest WS gate available — if the store / WS
// integration breaks, this test fires before any specific dup-row
// regression makes it to production.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { PageLogin } from './login-page'
import { test } from './api-fixture'

test.describe.configure({ mode: 'serial' })

test.describe('Vue 2 websocket — store updates without manual refresh', () => {
  /** @type {string} */
  let desktopId
  /** @type {string} */
  let desktopName

  test.beforeAll(async ({ baseURL }) => {
    test.setTimeout(120000)
    // Use bootstrap admin everywhere in this spec — the test
    // body issues an out-of-band DELETE via the api fixture
    // AFTER the UI has authenticated, and the
    // ``one-session-per-user`` rule in isard-sessions would
    // invalidate the UI cookie if the api fixture re-logged in
    // as the same per-worker admin. Bootstrap admin keeps the
    // browser session intact while still seeing the desktop
    // (bootstrap admin owns it).
    const seed = new ApiHelper(baseURL ?? 'https://localhost')
    await seed.login()

    const templates = await seed.getTemplates()
    const tpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!tpl) {
      test.skip(true, 'no Stopped+enabled template seeded')
      return
    }

    const ts = Date.now()
    desktopName = `ws-event-${ts}`
    const dsk = await seed.createDesktop(desktopName, tpl.id)
    desktopId = dsk.id

    try {
      await seed.waitForDomainStatus(desktopId, 'Stopped', 60000)
    } catch (e) {
      // The engine on this stack is too slow to materialise a
      // desktop within 60 s — the WS-events test can't run if
      // the desktop never settles. Mark seedFailed so the test
      // body skips cleanly.
      console.warn(`desktop did not reach Stopped: ${e.message}`)
      desktopId = null
    }
  })

  test.afterAll(async ({ baseURL }) => {
    if (!desktopId) return
    try {
      const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
      await cleanup.login()
      await cleanup._authFetch('DELETE', `/api/v4/item/desktop/${desktopId}?permanent=true`)
    } catch (e) { /* already gone */ }
  })

  test('out-of-band delete removes row from /desktops without refresh', async ({
    page,
    baseURL
  }) => {
    test.skip(!desktopId, 'beforeAll did not seed a desktop')

    // Override the per-worker UI login to use bootstrap admin
    // so the browser session matches the seed/cleanup user.
    const login = new PageLogin(page)
    await login.goto()
    await login.form('admin', 'IsardVDI')
    await login.finished()

    await page.goto('/desktops')
    await page.waitForLoadState('networkidle')

    // The Vue 2 desktops list truncates long names in the row
    // text (e.g. ``ws-event-17779318710...``), so an exact text
    // locator fails. Match by a stable prefix instead — the
    // first 18 chars of the timestamped name are unique enough
    // for our purposes.
    const namePrefix = desktopName.slice(0, 18)
    const card = page.getByText(new RegExp(namePrefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))).first()
    await expect(
      card,
      `seeded desktop '${desktopName}' should be visible on /desktops`
    ).toBeVisible({ timeout: 15000 })

    // Out-of-band delete using the BROWSER's auth token —
    // logging in again as bootstrap admin would invalidate the
    // page's session (one-session-per-user) and the page would
    // redirect to /login, masking the WS event we want to
    // observe.
    const cookies = await page.context().cookies()
    const auth = cookies.find((c) => /authorization/i.test(c.name))
    const browserTok = auth ? decodeURIComponent(auth.value).replace(/^Bearer\s+/i, '') : ''
    if (!browserTok) {
      test.skip(true, 'no auth cookie on page; cannot perform out-of-band delete')
      return
    }
    const delRes = await fetch(`${baseURL ?? 'https://localhost'}/api/v4/item/desktop/${desktopId}?permanent=true`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${browserTok}` }
    })
    expect(delRes.ok || delRes.status === 404, `out-of-band DELETE got ${delRes.status}`).toBeTruthy()
    desktopId = null // prevent afterAll from trying to delete again

    // Wait up to 15s for the card to disappear without a manual
    // refresh. Bug #13/#17/#33 class regression is "card stays
    // visible" — assert it's gone.
    await expect(
      card,
      'out-of-band delete should propagate to /desktops via WebSocket; ' +
      'the card stayed visible — store handler didn\'t process the delete event.'
    ).not.toBeVisible({ timeout: 15000 })
  })
})
