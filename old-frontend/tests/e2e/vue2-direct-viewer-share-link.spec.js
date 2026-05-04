// @ts-check
//
// Regression for round-2 Bug #2 + still-open Bugs #5/#31/#35 — the
// direct-viewer share-link flow.
//
// Bug #2 (fixed by 34de55f4d) was the anonymous get-viewer endpoint
// 500'ing because ``DesktopViewerResponse`` pydantic validation
// rejected viewer entries with missing optional fields.
//
// The route's broad ``except Exception`` (desktop_direct_viewer.py
// ~line 158) re-dresses all internal failures as a generic 404 with
// rate-limit-equalised timing. So from the outside the bug looks
// like "share-link works but viewer 404's"; the failure shape we
// can pin from e2e is simpler: the SHARE-LINK plumbing itself
// (toggle on, read back, parse token, hit anonymous URL) must NOT
// 5xx at any step.
//
// What we explicitly assert:
//   * Admin can toggle ``update-share-link`` to enabled (200).
//   * ``get-share-link`` returns a string with a token segment.
//   * Anonymous request to ``/token/{token}/get-viewer`` returns
//     either 200 (desktop ready) OR 404 (rate-limited / not
//     ready). It must NOT 5xx — that's the shape Bug #2 hit.
//
// This does NOT pin the per-template viewer-payload shape (Canary
// Alpine #31/#35) because the spec does not start the desktop —
// starting needs a real hypervisor and minutes of wait. The unit
// test layer would be the right place to pin specific viewer
// payload shapes.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { test } from './api-fixture'

test.describe.configure({ mode: 'serial' })

test.describe('Bug #2/#5/#31/#35 — direct-viewer share-link plumbing', () => {
  /** @type {string} */
  let desktopId

  test.beforeAll(async ({ baseURL }) => {
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
    const dsk = await seed.createDesktop(`share-link-${ts}`, tpl.id)
    desktopId = dsk.id
    // Don't wait for Started — the share-link toggle works on a
    // Stopped desktop too; the anonymous viewer endpoint will 404
    // rather than serve, which is the expected non-5xx behaviour.
  })

  test.afterAll(async ({ baseURL }) => {
    if (!desktopId) return
    try {
      const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
      await cleanup.login()
      await cleanup._authFetch('DELETE', `/api/v4/item/desktop/${desktopId}?permanent=true`)
    } catch (e) {
      console.warn(`afterAll: deleteDesktop failed: ${e.message}`)
    }
  })

  test('share-link toggle + read + anonymous fetch never 5xx', async ({ api }) => {
    test.skip(!desktopId, 'beforeAll did not seed a desktop')

    // 1. Enable sharing — PUT update-share-link.
    const updateRes = await api._authFetch(
      'PUT',
      `/api/v4/item/desktop/${desktopId}/update-share-link`,
      { enabled: true }
    )
    expect(updateRes).toBeTruthy()
    expect(typeof updateRes.link).toBe('string')

    // 2. Read back.
    const getRes = await api._authFetch(
      'GET',
      `/api/v4/item/desktop/${desktopId}/get-share-link`
    )
    expect(typeof getRes.link).toBe('string')
    expect(getRes.link.length).toBeGreaterThan(0)

    // 3. Extract the token from the share link. The link is
    //    either a full URL (``<base>/direct-viewer/<token>``) or
    //    just the bare token, depending on the apiv4 commit.
    //    Try the URL match first, then fall back to bare token.
    const urlMatch = getRes.link.match(/[/?&=]([A-Za-z0-9_-]{30,})/)
    const bareMatch = getRes.link.match(/^[A-Za-z0-9_-]{30,}$/)
    const match = urlMatch || bareMatch
    expect(match, `expected token in share link: ${getRes.link}`).toBeTruthy()
    const token = urlMatch ? urlMatch[1] : getRes.link

    // 4. Anonymous fetch (no Authorization header) to the viewer
    //    endpoint. The Bug #2 / #31 / #35 surface: the route MUST
    //    NOT return 5xx. 200 = desktop ready (rare for a Stopped
    //    desktop; possible if the engine boots fast). 404 = the
    //    swallowed-exception path or rate limit (expected for
    //    Stopped). Both are acceptable; 5xx means a bug regressed.
    const baseURL = test.info().project.use?.baseURL ?? 'https://localhost'
    const anonRes = await fetch(
      `${baseURL}/api/v4/item/desktop/token/${token}/get-viewer`,
      {
        // Node 18+ fetch — no agent option for self-signed certs;
        // rely on `ignoreHTTPSErrors: true` in playwright.config.
        method: 'GET'
      }
    )

    expect(
      anonRes.status,
      'Bug #2/#31/#35 regression: anonymous /token/{token}/get-viewer ' +
        `returned ${anonRes.status}. Acceptable: 200 (desktop ready) or 404 ` +
        '(swallowed by the broad except / rate-limit path); 5xx means a ' +
        'pydantic ValidationError or other bug surfaces past the swallow.'
    ).toBeLessThan(500)
  })

  test('share-link toggle off — disabled state', async ({ api }) => {
    test.skip(!desktopId, 'beforeAll did not seed a desktop')

    const updateRes = await api._authFetch(
      'PUT',
      `/api/v4/item/desktop/${desktopId}/update-share-link`,
      { enabled: false }
    )
    expect(updateRes).toBeTruthy()
    // After toggle-off the link can be either null/empty or unchanged
    // depending on backend semantics. The assertion is simply that
    // the toggle doesn't 5xx.
  })
})
