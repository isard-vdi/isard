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

  test('GET /permissions on a fresh deployment returns a list (200)', async ({ api }) => {
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')

    const result = await api._authFetch(
      'GET',
      `/api/v4/item/deployment/${deploymentId}/permissions`
    )
    expect(
      Array.isArray(result),
      'deployment /permissions must return a list (was crashing with AttributeError on legacy rows)'
    ).toBeTruthy()
  })
})
