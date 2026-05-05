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
import { ApiHelper } from './helpers/api'
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

  // The admin path above short-circuits the permission check at
  // the role level — so it doesn't actually exercise the lambda
  // in ``_common.helpers.alloweds.get_items_allowed`` that the
  // ``r is not defined`` NameError lived in. The bug was visible
  // for non-admin recipients of shared templates because their
  // request reached the filter expression. This sub-test pins
  // the non-admin path: a freshly-created ``user``-role user
  // hits the same endpoint and must get a 200 list (empty or
  // not), proving the fix holds for the path that originally
  // 500'd in production.
  test('non-admin user GET /items/templates/allowed/shared → 200 list (no NameError on the permission lambda)', async ({ baseURL }) => {
    const seed = new ApiHelper(baseURL ?? 'https://localhost')
    await seed.login()

    const ts = Date.now()
    /** @type {string|undefined} */
    let userId
    const username = `bug36-recipient-${ts}`

    try {
      // Group id follows the seed convention ``<category>-<group>``;
      // ``default`` alone matches no row (only the category does),
      // so apiv4 returns 404 ``Group default not found``.
      const user = await seed.createUser(username, 'default', 'default-default', 'user', 'test1234')
      userId = user?.id ?? user?.user?.id

      // Log in as the non-admin user — separate ApiHelper instance
      // so the admin token isn't clobbered.
      const recipient = new ApiHelper(baseURL ?? 'https://localhost')
      await recipient.login(username, 'test1234', 'default')

      // The endpoint is the regression target. With the cherry-
      // picked fix the lambda lives in ``Alloweds.get_items_allowed``
      // (declarative kwargs) instead of an in-route ``r.not_(...)``;
      // pre-fix this call 500'd with ``NameError: name 'r' is not
      // defined`` for any non-admin caller.
      const list = await recipient._authFetch(
        'GET',
        '/api/v4/items/templates/allowed/shared'
      )
      expect(
        Array.isArray(list),
        'non-admin /allowed/shared must return an array (was 500 NameError pre-fix)'
      ).toBeTruthy()

      // Sanity-check: every item the non-admin sees is enabled,
      // matching the ``require_enabled=True`` kwarg in the fix.
      for (const tpl of list) {
        expect(
          tpl.enabled,
          `template ${tpl.id} in non-admin /shared should be enabled`
        ).toBeTruthy()
      }
    } finally {
      if (userId) {
        try {
          await seed._authFetch('DELETE', `/api/v4/admin/user/${userId}`)
        } catch (e) { /* best-effort cleanup */ }
      }
    }
  })
})
