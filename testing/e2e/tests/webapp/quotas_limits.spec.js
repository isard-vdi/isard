// E2E tests for the legacy-admin Quotas / Limits page.
// Contract: testing/e2e/specs/webapp/quotas_limits.md
//
// All edits target the dedicated, non-Default, non-login `qle2e` category so
// the Default category and every login account are never mutated. The admin
// suite runs first; the manager suite (logged in as `qle2e-manager`, seeded
// inside `qle2e`) runs after — both edit the same `qle2e` fixtures, so the
// whole file is a single serial describe.
import { test, expect, unwrap } from '../../fixtures/apiv4/index.js'
import { bridgeAdminSession } from '../../fixtures/common.js'
import {
  adminListUsersNav,
  adminListGroupsNav,
  adminListCategoriesNav,
  adminGetQuotaByKindItem,
  adminUpdateUser,
  adminUpdateGroupQuota,
  adminUpdateGroupLimits,
  adminUpdateCategoryQuota,
  adminUpdateCategoryLimits,
} from '../../src/gen/apiv4/sdk.gen'

// ── Fixture identifiers (seeded in testing/db/data) ──────────────────────────
const CAT = 'qle2e'
const CAT_NAME = 'QuotasLimits E2E'
const GROUP = 'qle2e-group'
const GROUP_NAME = 'QL E2E Group'
const U_USER = 'qle2e-user' // role: user
const U_ADV = 'qle2e-adv' // role: advanced

// Sample edit payloads — values chosen distinct from the form defaults.
//
// Quota/limits hierarchy (enforced by the backend and by the webapp's
// per-field `max`): a child's quota/limits may not exceed its parent's
// (user ≤ group ≤ category), and every quota field is capped by the entity's
// effective limits. So `SAMPLE_LIMITS` is a COMPLETE, generous dict — every
// limits field sits at/above the largest quota sample — so a group/category
// whose limits a test sets never caps a later child quota edit below its
// sample. (A partial limits dict would leave the other inputs at the
// restrictive `quota_edit.html` defaults, e.g. vcpus:1 / memory:2, which would
// then block any child quota edit.)
const SAMPLE_QUOTA = { desktops: 7, running: 3, vcpus: 4, memory: 6 }
const SAMPLE_QUOTA_2 = { desktops: 9, running: 5, vcpus: 6, memory: 8 }
const SAMPLE_LIMITS = {
  users: 9,
  desktops: 12,
  volatile: 12,
  running: 10,
  templates: 12,
  isos: 12,
  memory: 64,
  vcpus: 32,
  desktops_disk_size: 200,
  total_size: 500,
  total_soft_size: 400,
  deployments_total: 12,
}

const QUOTAS_URL = '/isard-admin/admin/users/QuotasLimits'

// ── API helpers (raw, stored state) ─────────────────────────────────────────
// Groups/categories: read via the nav-list endpoints. They run a LIVE DB query
// (no server-side cache) and expose the raw `quota`/`limits` on the
// `quotas_limits` nav, so the value reflects an edit immediately.
async function getGroupRow(client, groupId) {
  const rows = await unwrap(adminListGroupsNav({ client, path: { nav: 'quotas_limits' } }))
  const row = rows.find((r) => r.id === groupId)
  if (!row) throw new Error(`group ${groupId} not in nav list`)
  return row
}
async function getCategoryRow(client, catId) {
  const rows = await unwrap(adminListCategoriesNav({ client, path: { nav: 'quotas_limits' } }))
  const row = rows.find((r) => r.id === catId)
  if (!row) throw new Error(`category ${catId} not in nav list`)
  return row
}
// Users: the user response models don't carry `quota`, and the only endpoint
// that does (GET /admin/quota/user/{id}) goes through a 10s server cache, so
// these reads MUST be polled (see expectQuotaEventually). Returns the raw user
// quota (`false` when inherited).
const getUserQuota = (client, userId) =>
  unwrap(adminGetQuotaByKindItem({ client, path: { kind: 'user', item_id: userId } })).then(
    (q) => q.quota,
  )

async function setUserQuotaViaApi(client, userId, quota) {
  await unwrap(adminUpdateUser({ client, path: { user_id: userId }, body: { quota } }))
}
async function setGroupQuotaViaApi(client, groupId, quota) {
  await unwrap(
    adminUpdateGroupQuota({ client, path: { group_id: groupId }, body: { quota, role: 'all_roles' } }),
  )
}
async function setGroupLimitsViaApi(client, groupId, limits) {
  await unwrap(adminUpdateGroupLimits({ client, path: { group_id: groupId }, body: { limits } }))
}
async function setCategoryQuotaViaApi(client, catId, quota) {
  await unwrap(
    adminUpdateCategoryQuota({
      client,
      path: { category_id: catId },
      body: { quota, role: 'all_roles' },
    }),
  )
}
async function setCategoryLimitsViaApi(client, catId, limits) {
  await unwrap(adminUpdateCategoryLimits({ client, path: { category_id: catId }, body: { limits } }))
}

// Reset the whole qle2e category back to fully-inherited. Uses the category
// propagate path, which updates groups' and users' quota/limits via a direct
// table write (NOT the session-revoking user-update path) — so the shared
// `qle2e-manager` session is never invalidated by cleanup.
async function resetQle2e(apiv4Admin) {
  await adminUpdateCategoryQuota({
    client: apiv4Admin,
    path: { category_id: CAT },
    body: { quota: false, role: 'all_roles', propagate: true },
  }).catch(() => {})
  await adminUpdateCategoryLimits({
    client: apiv4Admin,
    path: { category_id: CAT },
    body: { limits: false, propagate: true },
  }).catch(() => {})
}

// ── UI helpers ───────────────────────────────────────────────────────────────
async function gotoQuotas(page) {
  await page.goto(QUOTAS_URL)
  await page.locator('#users').waitFor({ state: 'visible', timeout: 20000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  // Show all rows so target entities are present in the DOM regardless of paging.
  await page.evaluate(() => {
    for (const sel of ['#users', '#groups', '#categories']) {
      try {
        const t = window.$(sel).DataTable()
        if (t && t.page) t.page.len(-1).draw(false)
      } catch (e) {
        /* table not yet initialised — ignore */
      }
    }
  })
}

// iCheck is jQuery-driven (the native input is opacity:0); call its API so the
// ifChecked/ifUnchecked handlers (which enable/disable the quota inputs) fire.
const setICheck = (page, selector, state) =>
  page.evaluate(({ selector, state }) => window.$(selector).iCheck(state), { selector, state })

async function applyInherit(page, formSel) {
  await setICheck(page, `${formSel} #unlimited`, 'check')
  // The user modal's Send requires Parsley to pass even for "inherit" (it has
  // no `|| 'unlimited' in formdata` bypass), and a stale partial prefill can
  // leave required quota fields blank. Backfill so Send isn't blocked — the
  // submitted quota is `false` regardless of these field values.
  await backfillEmpty(page, formSel, 'quota')
  await backfillEmpty(page, formSel, 'limits')
}
// The modal prefill is served from the same 10s server cache; a stale PARTIAL
// quota (the sample only sets a few keys) makes setQuotaMax blank the other
// inputs (`$('#quota-x').val(undefined)`). Once "unlimited" is unchecked those
// blank inputs are `required` and Parsley silently blocks Send. So after
// setting the sampled keys, backfill any still-empty field with a valid value.
async function backfillEmpty(page, formSel, prefix) {
  await page.evaluate(
    ({ formSel, prefix }) => {
      document.querySelectorAll(`${formSel} input[id^="${prefix}-"]`).forEach((el) => {
        if (el.value === '' || el.value == null) {
          el.value = '1'
          el.dispatchEvent(new Event('input', { bubbles: true }))
          el.dispatchEvent(new Event('change', { bubbles: true }))
        }
      })
    },
    { formSel, prefix },
  )
}
async function applyCustomQuota(page, formSel, quota) {
  await setICheck(page, `${formSel} #unlimited`, 'uncheck')
  for (const [k, v] of Object.entries(quota)) {
    await page.fill(`${formSel} #quota-${k}`, String(v))
  }
  await backfillEmpty(page, formSel, 'quota')
}
async function applyCustomLimits(page, formSel, limits) {
  await setICheck(page, `${formSel} #unlimited`, 'uncheck')
  for (const [k, v] of Object.entries(limits)) {
    await page.fill(`${formSel} #limits-${k}`, String(v))
  }
  await backfillEmpty(page, formSel, 'limits')
}

async function expandUserRow(page, userId) {
  await page.locator(`#users tbody tr[id="${userId}"] td.details-control`).click()
  await page.locator(`#show-users-quota-${userId}`).first().waitFor({ state: 'visible', timeout: 10000 })
}
async function openUserEdit(page, userId) {
  await expandUserRow(page, userId)
  const prefill = page.waitForResponse(
    (r) => r.url().includes(`/api/v4/admin/quota/user/${userId}`) && r.request().method() === 'GET',
    { timeout: 10000 },
  )
  await page.locator(`div[data-pk="${userId}"] .btn-edit`).first().click()
  await page.locator('#modalEditUser').waitFor({ state: 'visible', timeout: 10000 })
  await prefill.catch(() => {})
  await page.waitForTimeout(300) // let setQuotaMax bind the iCheck handlers
}

async function expandRowByName(page, tableSel, name) {
  const row = page
    .locator(`${tableSel} tbody tr`)
    .filter({ has: page.locator(`a:has-text("${name}")`) })
    .first()
  await row.locator('td.details-show').click()
  await page.waitForTimeout(400)
}
async function openGroupQuota(page) {
  await expandRowByName(page, '#groups', GROUP_NAME)
  const prefill = page.waitForResponse(
    (r) => r.url().includes(`/api/v4/admin/quota/group/${GROUP}`) && r.request().method() === 'GET',
    { timeout: 10000 },
  )
  await page.locator(`div[data-pk="${GROUP}"] .btn-edit-group-quotas`).first().click()
  await page.locator('#modalEditQuota').waitFor({ state: 'visible', timeout: 10000 })
  await prefill.catch(() => {})
  await page.waitForTimeout(300)
}
async function openGroupLimits(page) {
  await expandRowByName(page, '#groups', GROUP_NAME)
  await page.locator(`div[data-pk="${GROUP}"] .btn-edit-limits`).first().click()
  await page.locator('#modalEditLimits').waitFor({ state: 'visible', timeout: 10000 })
  await page.waitForTimeout(400)
}
async function openCategoryQuota(page) {
  await expandRowByName(page, '#categories', CAT_NAME)
  const prefill = page.waitForResponse(
    (r) => r.url().includes(`/api/v4/admin/quota/category/${CAT}`) && r.request().method() === 'GET',
    { timeout: 10000 },
  )
  await page.locator(`div[data-pk="${CAT}"] .btn-edit-category-quotas`).first().click()
  await page.locator('#modalEditQuota').waitFor({ state: 'visible', timeout: 10000 })
  await prefill.catch(() => {})
  await page.waitForTimeout(300)
}
async function openCategoryLimits(page) {
  await expandRowByName(page, '#categories', CAT_NAME)
  await page.locator(`div[data-pk="${CAT}"] .btn-edit-limits`).first().click()
  await page.locator('#modalEditLimits').waitFor({ state: 'visible', timeout: 10000 })
  await page.waitForTimeout(400)
}

function waitForPut(page, urlPart) {
  return page.waitForResponse(
    (r) => r.url().includes(urlPart) && r.request().method() === 'PUT',
    { timeout: 15000 },
  )
}

// Polls a quota/limits getter until it reflects the edit. Group/category
// getters read fresh (resolve on the first poll); the user getter rides out the
// 10s server cache on GET /admin/quota/user/{id} (which user updates don't
// invalidate). `expected` is `false` (inherited/unlimited) or a PARTIAL dict —
// only the listed keys are asserted (others may carry form defaults;
// `deployment_desktops` is not renderable in the form, see spec Known issues).
async function expectQuotaEventually(getter, expected) {
  await expect
    .poll(
      async () => {
        const q = await getter()
        if (expected === false) return q
        if (!q || typeof q !== 'object') return null
        return Object.fromEntries(Object.keys(expected).map((k) => [k, Number(q[k])]))
      },
      { timeout: 15000, intervals: [500, 1000, 1500, 2000] },
    )
    .toEqual(expected)
}

const userQuota = (client, id) => () => getUserQuota(client, id)
const groupQuota = (client) => async () => (await getGroupRow(client, GROUP)).quota
const groupLimits = (client) => async () => (await getGroupRow(client, GROUP)).limits
const categoryQuota = (client) => async () => (await getCategoryRow(client, CAT)).quota
const categoryLimits = (client) => async () => (await getCategoryRow(client, CAT)).limits

test.describe.serial('Quotas / Limits — webapp', () => {
  // Universal cleanup: restore qle2e to fully-inherited after every test.
  test.afterEach(async ({ apiv4Admin }) => {
    await resetQle2e(apiv4Admin)
  })

  // ════════════════════════════════════════════════════════════════════════
  //  Admin scenarios
  // ════════════════════════════════════════════════════════════════════════

  test('SA1 - admin previews a user quota without editing', async ({ authenticatedPage: page }) => {
    await gotoQuotas(page)
    const prefill = page.waitForResponse(
      (r) => r.url().includes(`/api/v4/admin/quota/user/${U_USER}`) && r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await expandUserRow(page, U_USER)
    expect((await prefill).status()).toBeLessThan(400)
    // Read-only preview: the quota inputs are disabled.
    await expect(page.locator(`#show-users-quota-${U_USER} #quota-desktops`).first()).toBeDisabled()
  })

  test('SA2a - admin applies the group quota to a user (inherit)', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await setUserQuotaViaApi(apiv4Admin, U_USER, SAMPLE_QUOTA) // start from a custom quota
    await gotoQuotas(page)
    await openUserEdit(page, U_USER)
    await applyInherit(page, '#modalEditUserForm')
    const put = waitForPut(page, `/api/v4/admin/item/user/${U_USER}`)
    await page.locator('#modalEditUser #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expect(page.locator('#modalEditUser')).toBeHidden({ timeout: 8000 })
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), false)
  })

  test('SA2b - admin applies a custom quota to a user', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openUserEdit(page, U_USER)
    await applyCustomQuota(page, '#modalEditUserForm', SAMPLE_QUOTA)
    const put = waitForPut(page, `/api/v4/admin/item/user/${U_USER}`)
    await page.locator('#modalEditUser #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expect(page.locator('#modalEditUser')).toBeHidden({ timeout: 8000 })
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), SAMPLE_QUOTA)
  })

  test('SA3a - admin applies the category quota to a group (inherit)', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await setGroupQuotaViaApi(apiv4Admin, GROUP, SAMPLE_QUOTA) // start from a custom group quota
    await gotoQuotas(page)
    await openGroupQuota(page)
    await applyInherit(page, '#modalEditQuotaForm')
    const put = waitForPut(page, `/api/v4/admin/item/quota/group/${GROUP}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expect(page.locator('#modalEditQuota')).toBeHidden({ timeout: 8000 })
    await expectQuotaEventually(groupQuota(apiv4Admin), false)
  })

  test('SA3b - admin applies a custom group quota (group default only)', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openGroupQuota(page) // role defaults to all_roles, propagate off
    await applyCustomQuota(page, '#modalEditQuotaForm', SAMPLE_QUOTA)
    const put = waitForPut(page, `/api/v4/admin/item/quota/group/${GROUP}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(groupQuota(apiv4Admin), SAMPLE_QUOTA)
    // members untouched (no propagate)
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), false)
    await expectQuotaEventually(userQuota(apiv4Admin, U_ADV), false)
  })

  test('SA3c - admin applies a group quota to a specific role', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openGroupQuota(page)
    await page.selectOption('#modalEditQuotaForm #add-role', 'user') // hides propagate
    await applyCustomQuota(page, '#modalEditQuotaForm', SAMPLE_QUOTA)
    const put = waitForPut(page, `/api/v4/admin/item/quota/group/${GROUP}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    // role=user member updated; advanced member + group default untouched
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), SAMPLE_QUOTA)
    await expectQuotaEventually(userQuota(apiv4Admin, U_ADV), false)
    await expectQuotaEventually(groupQuota(apiv4Admin), false)
  })

  test('SA3d - admin overrides the group users current quota', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openGroupQuota(page) // all_roles
    await applyCustomQuota(page, '#modalEditQuotaForm', SAMPLE_QUOTA)
    await setICheck(page, '#modalEditQuotaForm #propagate', 'check')
    const put = waitForPut(page, `/api/v4/admin/item/quota/group/${GROUP}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    // group default AND both members overwritten
    await expectQuotaEventually(groupQuota(apiv4Admin), SAMPLE_QUOTA)
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), SAMPLE_QUOTA)
    await expectQuotaEventually(userQuota(apiv4Admin, U_ADV), SAMPLE_QUOTA)
  })

  test('SA4a - admin applies the category limits to a group (inherit)', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await setGroupLimitsViaApi(apiv4Admin, GROUP, SAMPLE_LIMITS) // start from custom limits
    await gotoQuotas(page)
    await openGroupLimits(page)
    await applyInherit(page, '#modalEditLimitsForm')
    const put = waitForPut(page, `/api/v4/admin/item/limits/group/${GROUP}`)
    await page.locator('#modalEditLimits #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expect(page.locator('#modalEditLimits')).toBeHidden({ timeout: 8000 })
    await expectQuotaEventually(groupLimits(apiv4Admin), false)
  })

  test('SA4b - admin applies custom group limits', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openGroupLimits(page)
    await applyCustomLimits(page, '#modalEditLimitsForm', SAMPLE_LIMITS)
    const put = waitForPut(page, `/api/v4/admin/item/limits/group/${GROUP}`)
    await page.locator('#modalEditLimits #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(groupLimits(apiv4Admin), SAMPLE_LIMITS)
  })

  test('SA5a - admin applies unlimited category quota', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await setCategoryQuotaViaApi(apiv4Admin, CAT, SAMPLE_QUOTA) // start from a custom category quota
    await gotoQuotas(page)
    await openCategoryQuota(page)
    await applyInherit(page, '#modalEditQuotaForm') // ".apply" reads "unlimited quota"
    const put = waitForPut(page, `/api/v4/admin/item/quota/category/${CAT}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expect(page.locator('#modalEditQuota')).toBeHidden({ timeout: 8000 })
    await expectQuotaEventually(categoryQuota(apiv4Admin), false)
  })

  test('SA5b - admin applies a custom category quota (category default only)', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openCategoryQuota(page) // all_roles, propagate off
    await applyCustomQuota(page, '#modalEditQuotaForm', SAMPLE_QUOTA)
    const put = waitForPut(page, `/api/v4/admin/item/quota/category/${CAT}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(categoryQuota(apiv4Admin), SAMPLE_QUOTA)
    // groups/users untouched
    await expectQuotaEventually(groupQuota(apiv4Admin), false)
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), false)
  })

  test('SA5c - admin applies a category quota to a specific role', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openCategoryQuota(page)
    await page.selectOption('#modalEditQuotaForm #add-role', 'user')
    await applyCustomQuota(page, '#modalEditQuotaForm', SAMPLE_QUOTA)
    const put = waitForPut(page, `/api/v4/admin/item/quota/category/${CAT}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    // cascades to role=user only; advanced + category default untouched
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), SAMPLE_QUOTA)
    await expectQuotaEventually(userQuota(apiv4Admin, U_ADV), false)
    await expectQuotaEventually(categoryQuota(apiv4Admin), false)
  })

  test('SA5d - admin overrides the category users current quota', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openCategoryQuota(page) // all_roles
    await applyCustomQuota(page, '#modalEditQuotaForm', SAMPLE_QUOTA)
    await setICheck(page, '#modalEditQuotaForm #propagate', 'check')
    const put = waitForPut(page, `/api/v4/admin/item/quota/category/${CAT}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(categoryQuota(apiv4Admin), SAMPLE_QUOTA)
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), SAMPLE_QUOTA)
    await expectQuotaEventually(userQuota(apiv4Admin, U_ADV), SAMPLE_QUOTA)
  })

  test('SA6a - admin applies unlimited category limits', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await setCategoryLimitsViaApi(apiv4Admin, CAT, SAMPLE_LIMITS)
    await gotoQuotas(page)
    await openCategoryLimits(page)
    await applyInherit(page, '#modalEditLimitsForm')
    const put = waitForPut(page, `/api/v4/admin/item/limits/category/${CAT}`)
    await page.locator('#modalEditLimits #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expect(page.locator('#modalEditLimits')).toBeHidden({ timeout: 8000 })
    await expectQuotaEventually(categoryLimits(apiv4Admin), false)
  })

  test('SA6b - admin applies custom category limits', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openCategoryLimits(page)
    await applyCustomLimits(page, '#modalEditLimitsForm', SAMPLE_LIMITS)
    const put = waitForPut(page, `/api/v4/admin/item/limits/category/${CAT}`)
    await page.locator('#modalEditLimits #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(categoryLimits(apiv4Admin), SAMPLE_LIMITS)
  })

  // ════════════════════════════════════════════════════════════════════════
  //  Manager scenarios (logged in as qle2e-manager; run after the admin suite)
  // ════════════════════════════════════════════════════════════════════════

  test('SM1 - manager previews a user quota without editing', async ({ qle2eManagerPage: page }) => {
    await gotoQuotas(page)
    const prefill = page.waitForResponse(
      (r) => r.url().includes(`/api/v4/admin/quota/user/${U_USER}`) && r.request().method() === 'GET',
      { timeout: 10000 },
    )
    await expandUserRow(page, U_USER)
    expect((await prefill).status()).toBeLessThan(400)
    await expect(page.locator(`#show-users-quota-${U_USER} #quota-desktops`).first()).toBeDisabled()
  })

  test('SM2a - manager applies the group quota to a user (inherit)', async ({
    qle2eManagerPage: page,
    apiv4Admin,
  }) => {
    await setUserQuotaViaApi(apiv4Admin, U_USER, SAMPLE_QUOTA)
    await gotoQuotas(page)
    await openUserEdit(page, U_USER)
    await applyInherit(page, '#modalEditUserForm')
    const put = waitForPut(page, `/api/v4/admin/item/user/${U_USER}`)
    await page.locator('#modalEditUser #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), false)
  })

  test('SM2b - manager applies a custom quota to a user', async ({
    qle2eManagerPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openUserEdit(page, U_USER)
    await applyCustomQuota(page, '#modalEditUserForm', SAMPLE_QUOTA_2)
    const put = waitForPut(page, `/api/v4/admin/item/user/${U_USER}`)
    await page.locator('#modalEditUser #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), SAMPLE_QUOTA_2)
  })

  test('SM3a - manager applies the category quota to a group (inherit)', async ({
    qle2eManagerPage: page,
    apiv4Admin,
  }) => {
    await setGroupQuotaViaApi(apiv4Admin, GROUP, SAMPLE_QUOTA)
    await gotoQuotas(page)
    await openGroupQuota(page)
    await applyInherit(page, '#modalEditQuotaForm')
    const put = waitForPut(page, `/api/v4/admin/item/quota/group/${GROUP}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(groupQuota(apiv4Admin), false)
  })

  test('SM3b - manager applies a custom group quota (group default only)', async ({
    qle2eManagerPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openGroupQuota(page)
    await applyCustomQuota(page, '#modalEditQuotaForm', SAMPLE_QUOTA)
    const put = waitForPut(page, `/api/v4/admin/item/quota/group/${GROUP}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(groupQuota(apiv4Admin), SAMPLE_QUOTA)
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), false)
    await expectQuotaEventually(userQuota(apiv4Admin, U_ADV), false)
  })

  test('SM3c - manager applies a group quota to a specific role', async ({
    qle2eManagerPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openGroupQuota(page)
    await page.selectOption('#modalEditQuotaForm #add-role', 'user')
    await applyCustomQuota(page, '#modalEditQuotaForm', SAMPLE_QUOTA)
    const put = waitForPut(page, `/api/v4/admin/item/quota/group/${GROUP}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), SAMPLE_QUOTA)
    await expectQuotaEventually(userQuota(apiv4Admin, U_ADV), false)
    await expectQuotaEventually(groupQuota(apiv4Admin), false)
  })

  test('SM3d - manager overrides the group users current quota', async ({
    qle2eManagerPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openGroupQuota(page)
    await applyCustomQuota(page, '#modalEditQuotaForm', SAMPLE_QUOTA)
    await setICheck(page, '#modalEditQuotaForm #propagate', 'check')
    const put = waitForPut(page, `/api/v4/admin/item/quota/group/${GROUP}`)
    await page.locator('#modalEditQuota #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(groupQuota(apiv4Admin), SAMPLE_QUOTA)
    await expectQuotaEventually(userQuota(apiv4Admin, U_USER), SAMPLE_QUOTA)
    await expectQuotaEventually(userQuota(apiv4Admin, U_ADV), SAMPLE_QUOTA)
  })

  test('SM4a - manager applies the category limits to a group (inherit)', async ({
    qle2eManagerPage: page,
    apiv4Admin,
  }) => {
    await setGroupLimitsViaApi(apiv4Admin, GROUP, SAMPLE_LIMITS)
    await gotoQuotas(page)
    await openGroupLimits(page)
    await applyInherit(page, '#modalEditLimitsForm')
    const put = waitForPut(page, `/api/v4/admin/item/limits/group/${GROUP}`)
    await page.locator('#modalEditLimits #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(groupLimits(apiv4Admin), false)
  })

  test('SM4b - manager applies custom group limits', async ({
    qle2eManagerPage: page,
    apiv4Admin,
  }) => {
    await gotoQuotas(page)
    await openGroupLimits(page)
    await applyCustomLimits(page, '#modalEditLimitsForm', SAMPLE_LIMITS)
    const put = waitForPut(page, `/api/v4/admin/item/limits/group/${GROUP}`)
    await page.locator('#modalEditLimits #send').click()
    expect((await put).status()).toBeLessThan(400)
    await expectQuotaEventually(groupLimits(apiv4Admin), SAMPLE_LIMITS)
  })

  test('SM5 - manager only sees users from its own category', async ({ apiv4QleManager }) => {
    const users = await unwrap(
      adminListUsersNav({ client: apiv4QleManager, path: { nav: 'quotas_limits' } }),
    )
    expect(users.length).toBeGreaterThan(0)
    for (const u of users) expect(u.category).toBe(CAT)
    const usernames = users.map((u) => u.username)
    expect(usernames).toContain(U_USER)
    expect(usernames).not.toContain('admin')
    expect(usernames).not.toContain('user01')
  })

  test('SM6 - manager only sees groups from its own category', async ({ apiv4QleManager }) => {
    const groups = await unwrap(
      adminListGroupsNav({ client: apiv4QleManager, path: { nav: 'quotas_limits' } }),
    )
    expect(groups.length).toBeGreaterThan(0)
    for (const g of groups) expect(g.parent_category).toBe(CAT)
    const ids = groups.map((g) => g.id)
    expect(ids).toContain(GROUP)
    expect(ids).not.toContain('default-default')
  })

  test('SM7 - manager only sees its own category', async ({ apiv4QleManager }) => {
    const cats = await unwrap(
      adminListCategoriesNav({ client: apiv4QleManager, path: { nav: 'quotas_limits' } }),
    )
    expect(cats.length).toBe(1)
    expect(cats[0].id).toBe(CAT)
  })

  test('SM8 - editing its own quota logs the manager out', async ({
    browser,
    users,
    categories,
    loginHelpers,
    apiv4Admin,
  }) => {
    // Dedicated throwaway login so it never poisons the shared manager session.
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true })
    const page = await ctx.newPage()
    try {
      await loginHelpers.login(page, users.qle2e_logout_mgr, categories)
      await bridgeAdminSession(page)
      await gotoQuotas(page)

      const selfId = users.qle2e_logout_mgr.username
      await openUserEdit(page, selfId)
      await applyCustomQuota(page, '#modalEditUserForm', SAMPLE_QUOTA)
      const put = waitForPut(page, `/api/v4/admin/item/user/${selfId}`)
      await page.locator('#modalEditUser #send').click()
      expect((await put).status()).toBeLessThan(400) // edit succeeds...

      // ...but the session is now revoked: the next authenticated request 401s.
      const probe = await page.request.get('/api/v4/admin/items/users/quotas_limits/users')
      expect(probe.status()).toBe(401)

      // UI manifestation: a follow-up page action redirects to login.
      await page.reload().catch(() => {})
      await page.waitForURL(/\/login|\/isard-admin\/logout/, { timeout: 15000 }).catch(() => {})
      expect(page.url()).toMatch(/\/login|\/isard-admin\/logout/)
    } finally {
      await ctx.close()
      // The manager is logged out; reset its quota via admin.
      await setUserQuotaViaApi(apiv4Admin, users.qle2e_logout_mgr.username, false).catch(() => {})
    }
  })
})
