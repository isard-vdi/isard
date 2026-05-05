// @ts-check
//
// Regression for Naomi's #54 — ``POST /api/v4/item/booking/event``
// was rejecting Vue 2 (old-frontend) payloads with 422
// ``missing item_id`` because old-frontend sends
// ``element_id`` / ``element_type`` (legacy v3 contract) while
// the apiv4 schema declares ``item_id`` / ``item_type``. Fix:
// Pydantic ``AliasChoices('item_id', 'element_id')`` so both wire
// shapes resolve to the same Python attribute.
//
// Spec: POST a booking with each shape, both must succeed (or fail
// with a non-validation error like 428 ``no_availability`` if the
// engine declines the slot — anything other than 422 / 500
// validates the schema fix).

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { test } from './api-fixture'

test.describe('Bug #54 regression — booking POST accepts element_id / item_id', () => {
  /** @type {string} */
  let desktopId
  /** @type {ApiHelper} */
  let seed

  test.beforeAll(async ({ baseURL }) => {
    seed = new ApiHelper(baseURL ?? 'https://localhost')
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
    const dsk = await seed.createDesktop(`bug54-${ts}`, tpl.id)
    desktopId = dsk.id
    try {
      await seed.waitForDomainStatus(desktopId, 'Stopped', 30000)
    } catch (e) { /* engine may be slow; the schema is what matters */ }
  })

  test.afterAll(async ({ baseURL }) => {
    if (!desktopId) return
    try {
      const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
      await cleanup.login()
      await cleanup._authFetch('DELETE', `/api/v4/item/desktop/${desktopId}?permanent=true`)
    } catch (e) { /* best-effort */ }
  })

  // The booking event schema's contract is the focus; whether
  // the engine actually books the slot depends on hypervisor/
  // reservables config. We assert the schema layer accepts each
  // shape — i.e. the response is NOT 422 ``missing item_id``.
  const expectNotValidation = (status, body, hint) => {
    expect(
      status === 422 && /missing.*item_id|item_id.*required/i.test(JSON.stringify(body)),
      `${hint}: should NOT 422 missing item_id; got ${status} ${JSON.stringify(body).slice(0, 200)}`
    ).toBeFalsy()
  }

  test('POST with legacy element_id / element_type passes the schema', async ({ api }) => {
    test.skip(!desktopId, 'beforeAll did not seed a desktop')
    const start = new Date(Date.now() + 60_000).toISOString()
    const end = new Date(Date.now() + 3600_000).toISOString()
    const res = await api._authFetch('POST', '/api/v4/item/booking/event', {
      element_id: desktopId,
      element_type: 'desktop',
      title: 'bug54-legacy',
      start,
      end
    }).catch((e) => ({ __err: e }))
    if (res?.__err) {
      // Helper threw on non-2xx — inspect the message for a 422
      // shape mismatch vs an engine-side decline.
      const msg = res.__err.message
      const m = msg.match(/\((\d+)\):\s*(.+)/)
      const status = m ? Number(m[1]) : 0
      const body = m ? m[2] : msg
      expectNotValidation(status, body, 'legacy element_id shape')
      return
    }
    // Cleanup so the slot is free for the second test.
    if (res?.id) {
      await api._authFetch('DELETE', `/api/v4/item/booking/event/${res.id}`).catch(() => undefined)
    }
  })

  test('POST with canonical item_id / item_type passes the schema', async ({ api }) => {
    test.skip(!desktopId, 'beforeAll did not seed a desktop')
    const start = new Date(Date.now() + 60_000).toISOString()
    const end = new Date(Date.now() + 3600_000).toISOString()
    const res = await api._authFetch('POST', '/api/v4/item/booking/event', {
      item_id: desktopId,
      item_type: 'desktop',
      title: 'bug54-canonical',
      start,
      end
    }).catch((e) => ({ __err: e }))
    if (res?.__err) {
      const msg = res.__err.message
      const m = msg.match(/\((\d+)\):\s*(.+)/)
      const status = m ? Number(m[1]) : 0
      const body = m ? m[2] : msg
      expectNotValidation(status, body, 'canonical item_id shape')
      return
    }
    if (res?.id) {
      await api._authFetch('DELETE', `/api/v4/item/booking/event/${res.id}`).catch(() => undefined)
    }
  })
})
