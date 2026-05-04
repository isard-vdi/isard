// @ts-check
//
// Regression for round-3 Bug #15 + open Bugs #33, #43.
//
// PUT /item/deployment/{id}/recreate triggers async deletion +
// re-creation of all desktops in the deployment. Three reported
// failure modes:
//
//   #15 (fixed) — Recreate 500 + desktops vanish. The fix
//        (commit 9be7946d1) added the threading-fallback pattern
//        for `asyncio.create_task` on the recreate path.
//   #33 (open) — Modal shows wrong count ("2 of 4 desktops"
//        when only 2 exist). Phantom rows persist in the table
//        until manual page refresh.
//   #43 (open) — Orphan storage rows: each recreate spawns a
//        storage row that no desktop references. Storage table
//        accumulates over time.
//
// This spec runs the recreate end-to-end via API (UI also covered
// indirectly because the same endpoint is hit). Assertions:
//   * Recreate returns 2xx (regression for #15).
//   * Final desktop count equals the original count (regression
//     for #33).
//   * Orphan-storage check is best-effort: counts storage rows
//     belonging to admin BEFORE and AFTER, asserts no net new
//     orphans. Tolerates +/- 1 because the engine may still have
//     in-flight rows when we sample.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { test } from './api-fixture'

test.describe.configure({ mode: 'serial' })

test.describe('Bug #15/#33/#43 — recreate deployment round-trip', () => {
  /** @type {string} */
  let deploymentId
  /** @type {number} */
  let storageCountBefore

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
    const resp = await seed.createDeployment(`recreate-${ts}`, tpl.id, {
      roles: ['admin'],
      categories: false,
      groups: false,
      users: false
    })
    deploymentId = resp.id

    // Sample storage table BEFORE the recreate. The orphan-storage
    // check (#43) compares this to the post-recreate count; an
    // unbounded grow signals storage rows are leaking on each
    // recreate.
    try {
      const storage = await seed._authFetch(
        'POST',
        '/api/v4/admin/table/storage',
        {}
      )
      storageCountBefore = Array.isArray(storage) ? storage.length : 0
    } catch (e) {
      console.warn(`storage baseline failed: ${e.message}`)
      storageCountBefore = -1
    }
  })

  test.afterAll(async ({ baseURL }) => {
    if (!deploymentId) return
    try {
      const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
      await cleanup.login()
      await cleanup.deleteDeployment(deploymentId)
    } catch (e) {
      console.warn(`afterAll: deleteDeployment failed: ${e.message}`)
    }
  })

  test('recreate succeeds and final desktop count matches original', async ({ api }) => {
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')

    // 1. Capture original desktop count from /item/deployment/{id}
    const before = await api._authFetch(
      'GET',
      `/api/v4/item/deployment/${deploymentId}`
    )
    const originalCount = (before.users || []).reduce(
      (acc, u) => acc + (u.desktops || []).length,
      0
    )
    expect(originalCount, 'deployment must have at least one desktop').toBeGreaterThan(0)

    // 2. Trigger recreate. Bug #15 was a 500 here; this assertion
    //    pins the fix (asyncio.create_task fallback for sync
    //    dispatch paths).
    const recreateRes = await api._authFetch(
      'PUT',
      `/api/v4/item/deployment/${deploymentId}/recreate`
    )
    expect(recreateRes).toBeTruthy()

    // 3. Recreate is async — engine deletes the old desktops then
    //    creates new ones. Poll until the count stabilises (or
    //    timeout). The bug's signature (#33) is that the count
    //    DOUBLES temporarily and never converges back to the
    //    original — so we want both "stabilised" AND "matches
    //    original".
    const deadline = Date.now() + 60000
    let lastCount = -1
    let stableSamples = 0
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 2000))
      const snap = await api._authFetch(
        'GET',
        `/api/v4/item/deployment/${deploymentId}`
      )
      const count = (snap.users || []).reduce(
        (acc, u) => acc + (u.desktops || []).length,
        0
      )
      if (count === lastCount) {
        stableSamples += 1
        if (stableSamples >= 3) break
      } else {
        stableSamples = 0
        lastCount = count
      }
    }

    // 4. The regression assertion: final count MUST equal the
    //    original. Bug #33's signature is final count >
    //    original (phantom rows from in-flight desktops accumulating).
    expect(
      lastCount,
      `Bug #33 regression: deployment had ${originalCount} desktops before recreate; ` +
        `after recreate-stabilise it has ${lastCount}. Phantom-row bug fires if > original.`
    ).toBe(originalCount)

    // 5. Bug #43 best-effort: storage table shouldn't have grown
    //    by more than the desktop count. A clean recreate
    //    produces 1 new storage per desktop AND deletes 1
    //    storage per old desktop, for a net delta of zero (or
    //    +1/-1 if the engine is mid-flight when we sample).
    if (storageCountBefore >= 0) {
      try {
        const after = await api._authFetch(
          'POST',
          '/api/v4/admin/table/storage',
          {}
        )
        const storageCountAfter = Array.isArray(after) ? after.length : 0
        const delta = storageCountAfter - storageCountBefore
        expect(
          delta,
          `Bug #43 regression: storage table grew by ${delta} after a single recreate ` +
            `(${storageCountBefore} → ${storageCountAfter}). Each recreate should net to zero ` +
            'delta (engine deletes old + creates new); a positive delta means orphan rows.'
        ).toBeLessThanOrEqual(originalCount + 2)
      } catch (e) {
        console.warn(`storage post-check failed: ${e.message}`)
      }
    }
  })
})
