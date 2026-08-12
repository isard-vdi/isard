// The template listings must return what the pre-apiv4 API returned.
//
// The defect behind this spec was invisible to the unit suite because the
// existing tests mocked `get_items_allowed` wholesale, so nothing ever
// exercised the selection loop against a real response. These assertions
// go through the real HTTP surface with a real session, which is the only
// level at which the merged-owner bug shows up.
//
// Owner fixture: `advanced_parity`, a dedicated advanced account — not one
// of the advanced_e2e_NN pool, so this spec never contends on a session a
// parallel worker is holding.
//
// Seeded templates, both owned by it:
//   template-parity-own     — shared with NOBODY, so it can only ever be
//                             listed through the OWNER branch
//   template-parity-shared  — shared with its own owner by user id, which
//                             is the only shape that reaches get-shared
//                             (ownership alone does not, see below). Shared
//                             by id rather than by group so no other
//                             account in the suite is affected.

import { expect, test } from '../fixtures/login.js'

const ALL = '/api/v4/items/templates/allowed/all'
const SHARED = '/api/v4/items/templates/get-shared'

const OWN = 'template-parity-own'
const SHARED_TPL = 'template-parity-shared'

test.describe.configure({ mode: 'serial' })

async function listing(page, url) {
  const resp = await page.request.get(url)
  expect(resp.ok(), `${url} -> ${resp.status()} ${await resp.text()}`).toBeTruthy()
  const body = await resp.json()
  const rows = Array.isArray(body) ? body : (body?.templates ?? body?.rows ?? [])
  return { rows, ids: rows.map((t) => t.id) }
}

async function loginAsOwner(page, users, categories, loginHelpers) {
  await loginHelpers.login(page, users.advanced_parity, categories)
}

test.describe('templates — listing parity with the pre-apiv4 api', () => {
  test('the owner gets their own template back from allowed/all', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    // The regression users reported: get_items_allowed merges the owner
    // into an object and then compares that object to a user id, so the
    // owner branch went dead and this template vanished from the list
    // behind "create a desktop from a template".
    await loginAsOwner(page, users, categories, loginHelpers)
    const { rows, ids } = await listing(page, ALL)
    expect(ids, 'an unshared own template can only arrive via the owner branch').toContain(OWN)
    // The same comparison drives `editable`, which the old frontend sorts on.
    expect(rows.find((t) => t.id === OWN).editable).toBe(true)
  })

  test('a template shared with the owner is listed too', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    await loginAsOwner(page, users, categories, loginHelpers)
    const { ids } = await listing(page, ALL)
    expect(ids).toContain(SHARED_TPL)
  })

  test('get-shared holds neither of the caller own templates', async ({
    page,
    users,
    categories,
    loginHelpers,
  }) => {
    // "Shared with me" is not the place for your own templates. The
    // unshared one never appeared — only_in_allowed skips the ownership
    // short-circuit, so ownership alone pulls nothing in. The one whose
    // ACL names its own owner did appear, and is what the fix removes.
    await loginAsOwner(page, users, categories, loginHelpers)
    const { ids } = await listing(page, SHARED)
    expect(ids, 'own template leaked into the shared tab').not.toContain(SHARED_TPL)
    expect(ids).not.toContain(OWN)
  })

  test('an unrelated advanced user sees neither listing entry', async ({ advancedE2EPage }) => {
    // Guards against the fixes over-widening: neither fixture names this
    // account on any axis — one is shared with nobody, the other only with
    // its own owner by id — so neither may reach it on either listing.
    for (const url of [ALL, SHARED]) {
      const { ids } = await listing(advancedE2EPage, url)
      expect(ids, `${url} leaked a foreign template`).not.toContain(OWN)
      expect(ids, `${url} leaked a foreign template`).not.toContain(SHARED_TPL)
    }
  })
})
