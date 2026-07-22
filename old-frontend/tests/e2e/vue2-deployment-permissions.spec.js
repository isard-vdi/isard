// @ts-check
//
// Regression for Naomi's #50 — GET
// ``/api/v4/item/deployment/{id}/permissions`` was 500ing with
// ``AttributeError: 'list' object has no attribute 'get'`` because
// the model's ``users_permissions.get(...)`` assumed a dict but
// ``Caches.get_document(table, id, [<single>])`` returns the
// unwrapped field value. Fix: collapse all None / empty / list
// returns to ``[]``.
//
// Spec: create a fresh deployment, GET /permissions → 200 list.
// Re-run on a fresh row (no user_permissions field populated)
// and on a row that already has permissions.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { test } from './api-fixture'

test.describe.configure({ mode: 'serial' })

test.describe('Bug #50 regression — GET deployment /permissions returns 200', () => {
  /** @type {string} */
  let deploymentId

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
    const dep = await seed.createDeployment(`bug50-${ts}`, tpl.id, {
      roles: ['admin'],
      categories: false,
      groups: false,
      users: false
    })
    deploymentId = dep.id
  })

  test.afterAll(async ({ baseURL }) => {
    if (!deploymentId) return
    try {
      const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
      await cleanup.login()
      try {
        await cleanup._authFetch('PUT', `/api/v4/item/deployment/${deploymentId}/stop`)
      } catch (e) { /* may already be stopped */ }
      await cleanup.deleteDeployment(deploymentId)
    } catch (e) { /* best-effort */ }
  })

  test('GET /permissions on a fresh deployment returns an empty list (200)', async ({ api }) => {
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')

    const result = await api._authFetch(
      'GET',
      `/api/v4/item/deployment/${deploymentId}/permissions`
    )
    expect(
      Array.isArray(result),
      'deployment /permissions must return a list (was crashing with AttributeError on legacy rows)'
    ).toBeTruthy()
    // Stronger than just "is array": fresh deployments have no
    // ``user_permissions`` field set in the rdb row at all, which
    // is what produced the original 500 — ``Caches.get_document``
    // returned None, and ``.get(...)`` on None raised AttributeError.
    // Post-fix the unwrap collapses None → [] and round-trips empty.
    expect(
      result.length,
      'fresh deployment must return an empty list, not the missing-field 500'
    ).toBe(0)
  })

  // The fresh-deployment branch covers the None / missing-field
  // path of the unwrap fix. The populated branch covers the other
  // half: when ``user_permissions`` is a non-empty list, the fix
  // must surface its contents unchanged. Without this sub-test a
  // future refactor that simplified ``get_deployment_permissions``
  // to ``return []`` (always) would still pass the fresh-state
  // test while silently breaking the round-trip of saved
  // permissions for every existing deployment.
  test('GET /permissions returns populated list after PUT /edit sets user_permissions', async ({ api }) => {
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')

    // ``PUT /item/deployment/{id}/edit`` is gated by
    // ``deployment_has_no_started_desktops`` (apiv4
    // ``api/dependencies/domains.py``). The owner desktop created
    // by ``createDeployment`` transitions through
    // ``CreatingDiskFromScratch`` before settling — sending
    // ``/edit`` while it's still creating yields a 428
    // ``deployment_stop`` error. Wait until every desktop is in
    // the safe set (``Stopped`` / ``Failed`` / ``Unknown``).
    //
    // On dev stacks where the seed template has no actual qcow2
    // disk on the hypervisor, the desktop gets stuck in a
    // non-safe state for far longer than this poll. In that case
    // the test skips rather than asserts — the schema fix is
    // already covered by the fresh-deployment test above; this
    // sub-test is a complement that requires a stack able to
    // settle desktops.
    const settledStatuses = new Set(['Stopped', 'Failed', 'Unknown'])
    const deadline = Date.now() + 30_000
    let allSettled = false
    while (Date.now() < deadline) {
      const resp = await api._authFetch('GET', '/api/v4/items/desktops')
      const desktops = (Array.isArray(resp) ? resp : resp?.desktops ?? [])
        .filter((d) => d.tag === deploymentId)
      if (desktops.length === 0) { allSettled = true; break }
      if (desktops.every((d) => settledStatuses.has(d.status))) {
        allSettled = true
        break
      }
      await new Promise((resolve) => setTimeout(resolve, 1000))
    }
    test.skip(
      !allSettled,
      'deployment desktops never reached a safe state on this stack — test only meaningful where engine can settle the deployment'
    )

    // Set ``user_permissions: ['recreate']`` via the edit form
    // (the same path the legacy Vue 2 deployment-edit modal uses).
    // ``DeploymentEditRequest`` allows all fields to default; we
    // only specify ``user_permissions`` to isolate the behaviour
    // under test.
    await api._authFetch(
      'PUT',
      `/api/v4/item/deployment/${deploymentId}/edit`,
      { user_permissions: ['recreate'] }
    )

    const populated = await api._authFetch(
      'GET',
      `/api/v4/item/deployment/${deploymentId}/permissions`
    )
    expect(
      Array.isArray(populated),
      'populated /permissions must still return a list'
    ).toBeTruthy()
    expect(
      populated,
      'PUT /edit ``user_permissions`` must round-trip through GET /permissions'
    ).toEqual(['recreate'])

    // Tear down the populated state so the suite stays
    // re-runnable: an unwound deployment should look like a fresh
    // one to subsequent specs that share the seed.
    await api._authFetch(
      'PUT',
      `/api/v4/item/deployment/${deploymentId}/edit`,
      { user_permissions: [] }
    )
  })
})
