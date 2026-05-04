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
import { test } from './login-page'

test.describe.configure({ mode: 'serial' })

test.describe('Vue 2 websocket — store updates without manual refresh', () => {
  /** @type {ApiHelper} */
  let api
  /** @type {string} */
  let desktopId
  /** @type {string} */
  let desktopName

  test.beforeAll(async ({ baseURL }) => {
    api = new ApiHelper(baseURL ?? 'https://localhost')
    await api.login()

    const templates = await api.getTemplates()
    const tpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!tpl) {
      test.skip(true, 'no Stopped+enabled template seeded')
      return
    }

    const ts = Date.now()
    desktopName = `ws-event-${ts}`
    const dsk = await api.createDesktop(desktopName, tpl.id)
    desktopId = dsk.id

    try {
      await api.waitForDomainStatus(desktopId, 'Stopped', 60000)
    } catch (e) {
      console.warn(`desktop did not reach Stopped: ${e.message}`)
    }
  })

  test.afterAll(async () => {
    if (desktopId) {
      try {
        await api._authFetch('DELETE', `/api/v4/item/desktop/${desktopId}?permanent=true`)
      } catch (e) { /* already gone */ }
    }
  })

  test('out-of-band delete removes row from /desktops without refresh', async ({
    page,
    login
  }) => {
    test.skip(!desktopId, 'beforeAll did not seed a desktop')

    await page.goto('/desktops')
    await page.waitForLoadState('networkidle')

    // Confirm the desktop is initially visible.
    const card = page.getByText(desktopName).first()
    await expect(
      card,
      `seeded desktop '${desktopName}' should be visible on /desktops`
    ).toBeVisible({ timeout: 15000 })

    // Out-of-band delete via API. The server emits a WS event that
    // the Vue 2 socket-instance subscribes to; the store handler
    // should remove the row from getDesktops.
    await api._authFetch('DELETE', `/api/v4/item/desktop/${desktopId}?permanent=true`)
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
