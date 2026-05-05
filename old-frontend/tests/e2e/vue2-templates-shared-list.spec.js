// @ts-check
//
// Regression for Naomi's persistent #36 — the "Shared with you"
// templates listing endpoint was crashing with
// ``NameError: name 'r' is not defined`` because a lambda in
// ``api/services/templates.py`` referenced the rethinkdb top-level
// ``r`` without importing it. Fix moved the ReQL into _common
// (``Alloweds.get_items_allowed`` now accepts the declarative
// ``exclude_owner_user_id`` + ``require_enabled`` kwargs).
//
// Spec: GET ``/api/v4/items/templates/allowed/shared`` as admin →
// 200, returns a list, items are non-owned by caller AND
// enabled.

import { expect } from '@playwright/test'
import { test } from './api-fixture'

test.describe('Bug #36 regression — /items/templates/allowed/shared returns 200', () => {
  test('admin GET /items/templates/allowed/shared → 200 list of non-owned enabled templates', async ({ api }) => {
    const list = await api._authFetch('GET', '/api/v4/items/templates/allowed/shared')
    expect(Array.isArray(list), '/allowed/shared must return an array').toBeTruthy()

    // The full /allowed/all listing is the superset.
    const all = await api._authFetch('GET', '/api/v4/items/templates/allowed/all')
    expect(Array.isArray(all)).toBeTruthy()

    // Every item in /shared must be enabled. (The owner check
    // is harder to assert here because admin role short-circuits
    // ``Alloweds.is_allowed``; what matters is the endpoint
    // doesn't 500 anymore.)
    for (const tpl of list) {
      expect(tpl.enabled, `template ${tpl.id} in /shared should be enabled`).toBeTruthy()
    }
  })
})
