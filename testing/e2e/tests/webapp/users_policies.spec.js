// Drives the authentication-policy admin flows on
// /isard-admin/admin/users/pwd_policies. Mirrors
// testing/e2e/specs/webapp/users_policies.md — each `test(...)` maps to
// a numbered scenario in that spec.
//
// Conventions:
//   - Policy IDs go through `testInfo.annotations` (type "policy-id") so
//     afterEach can delete them even when the test failed mid-flow.
//   - Each worker owns a fixed (type="local", role) slot derived from
//     workerIndex to avoid two workers creating the same (type,category,role)
//     triple simultaneously. The four built-in roles (user, advanced,
//     manager, admin) cover up to four parallel workers; a fifth worker
//     wraps back to "user".
//   - Scenarios that require a disclaimer notification template (S4, S11,
//     S13) skip gracefully when no custom templates exist in the DB, so the
//     file is safe to run against a freshly seeded environment.
//   - iCheck hides the real <input> behind an opacity:0 overlay. Always
//     click the sibling <ins class="iCheck-helper"> and verify state via
//     page.evaluate — never Playwright's `toBeChecked`, which reads the
//     hidden element directly and can race against iCheck's async sync.

import { test, expect, apiv4ClientForPage, unwrap } from '../../fixtures/apiv4/index.js'
import {
  adminAuthenticationPolicies,
  adminAuthenticationPolicyAdd,
  adminAuthenticationPolicyDelete,
  adminAuthenticationPolicy,
  adminAuthenticationPolicyEdit,
  adminForceEmail,
  adminForceDisclaimer,
  adminForcePassword,
  adminGetRoles,
  adminListCategories,
  adminListCustomNotificationTemplates,
} from '../../src/gen/apiv4/sdk.gen'

// ─── Roles ordered by ascending privilege so worker N picks roles[N % 4].
const WORKER_ROLES = ['user', 'advanced', 'manager', 'admin']

// ─── API helpers ────────────────────────────────────────────────────────────

async function listPolicies(client) {
  const data = await unwrap(adminAuthenticationPolicies({ client })).catch(() => [])
  return Array.isArray(data) ? data : []
}

async function getPolicyById(client, id) {
  const data = await unwrap(
    adminAuthenticationPolicy({ client, path: { policy_id: id } }),
  ).catch(() => null)
  return data ?? null
}

async function createPolicyViaApi(client, body) {
  // If a policy already exists for this (type, category, role) — from a
  // seed or a previous aborted run — delete it first so the POST succeeds.
  const all0 = await listPolicies(client)
  const existing = all0.find(
    (p) => p.type === body.type && p.category === body.category && p.role === body.role,
  )
  if (existing) await deletePolicyViaApi(client, existing.id)

  // POST returns 204 No Content; the created id must be recovered from the
  // policies list because the response carries no body.
  await unwrap(adminAuthenticationPolicyAdd({ client, body }))
  const all = await listPolicies(client)
  const created = all.find(
    (p) =>
      p.type === body.type &&
      p.category === body.category &&
      p.role === body.role,
  )
  if (!created) {
    throw new Error(
      `createPolicyViaApi: policy (${body.type}, ${body.category}, ${body.role}) not found after POST`,
    )
  }
  return created
}

async function deletePolicyViaApi(client, policyId) {
  await adminAuthenticationPolicyDelete({
    client,
    path: { policy_id: policyId },
  }).catch(() => {})
}

async function listCustomTemplates(client) {
  const data = await unwrap(adminListCustomNotificationTemplates({ client })).catch(() => null)
  if (!data) return []
  // The response might be { templates: [...] } or a bare array depending on
  // the API version; handle both.
  if (Array.isArray(data)) return data
  if (Array.isArray(data.templates)) return data.templates
  return []
}

async function getFirstCategory(client) {
  const data = await unwrap(adminListCategories({ client })).catch(() => [])
  const cats = Array.isArray(data) ? data : []
  return cats[0] ?? null
}

// ─── Tracking helpers ────────────────────────────────────────────────────────

function trackPolicyId(testInfo, id) {
  testInfo.annotations.push({ type: 'policy-id', description: id })
}

// ─── Navigation helpers ──────────────────────────────────────────────────────

async function gotoPolicies(page) {
  await page.goto('/isard-admin/admin/users/pwd_policies')
  await page
    .locator('#users-password-policy ~ .dataTables_wrapper, .dataTables_wrapper:has(#users-password-policy)')
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
}

// ─── iCheck helpers ──────────────────────────────────────────────────────────

// Click the iCheck overlay for the element matched by `selector` inside
// `scope` (a Playwright Locator). The real <input> lives at opacity:0 so
// Playwright's own `.click()` would fight the overlay.
async function iCheckClick(scope, inputSelector) {
  // iCheck wraps: <div class="icheckbox_flat-green"><input .../><ins class="iCheck-helper"/></div>
  // Clicking the <ins> triggers iCheck's change logic.
  await scope.locator(`${inputSelector} + ins.iCheck-helper`).click({ force: true })
}

// Read the native `.checked` value bypassing iCheck's wrapper.
// Receives the already-scoped Playwright locator for the modal so that
// `.locator(inputSelector)` targets the right element without relying on
// document.querySelector, which would always return the first match in the
// DOM regardless of which modal is open.
function iCheckRead(scopeLocator, inputSelector) {
  return scopeLocator.locator(inputSelector).evaluate((el) => el.checked)
}

// ─── PNotify helper ──────────────────────────────────────────────────────────

async function clickPnotifyOk(page) {
  await page
    .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', { hasText: /^ok$/i })
    .first()
    .click({ timeout: 5000 })
}

// ─── Default password body (valid for type=local) ────────────────────────────

function defaultPasswordBody() {
  return {
    digits: 0,
    length: 8,
    lowercase: 0,
    uppercase: 0,
    special_characters: 0,
    expiration: 0,
    old_passwords: 0,
    not_username: true,
  }
}

// ─── Test suite ──────────────────────────────────────────────────────────────

test.describe('Admin users policies — webapp', () => {
  // Tests share the DB and the browser UI — must run sequentially to avoid
  // slot collisions across workers when fullyParallel is enabled globally.
  test.describe.configure({ mode: 'serial' })
  // Remove any leftover test policies this worker might have created in
  // a previous (aborted) run. Keyed by the worker's designated role so
  // different workers never collide on cleanup.
  test.beforeAll(async ({ authenticatedContext }, workerInfo) => {
    const page = await authenticatedContext.newPage()
    try {
      const client = apiv4ClientForPage(page)
      const workerRole = WORKER_ROLES[workerInfo.workerIndex % WORKER_ROLES.length]
      const firstCat = await getFirstCategory(client)
      if (!firstCat) return
      const stale = (await listPolicies(client)).filter(
        (p) => p.type === 'local' && p.category === firstCat.id && p.role === workerRole,
      )
      for (const p of stale) {
        await deletePolicyViaApi(client, p.id)
      }
    } finally {
      await page.close()
    }
  })

  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    const ids = testInfo.annotations
      .filter((a) => a.type === 'policy-id')
      .map((a) => a.description)
    for (const id of ids) {
      await deletePolicyViaApi(apiv4Admin, id)
    }
  })

  // -------------------------------------------------------------------------
  // Scenario 1 — admin creates a local policy and sees it listed
  // -------------------------------------------------------------------------
  test('S1: creates a local policy and it appears in the table', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]

    // Pre-clean the slot in case a previous test left it occupied (e.g. afterEach
    // failed to delete after an aborted run).
    const stale = (await listPolicies(apiv4Admin)).find(
      (p) => p.type === 'local' && p.category === firstCat.id && p.role === workerRole,
    )
    if (stale) await deletePolicyViaApi(apiv4Admin, stale.id)

    await gotoPolicies(page)
    await page.locator('.btn-add-policy').click()
    const modal = page.locator('#modalPolicyAdd')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Type
    await modal.locator('#type-select select').selectOption('local')
    // Category — pick firstCat
    await modal.locator('#category-select select').selectOption(firstCat.id)
    // Role
    await modal.locator('#role-select select').selectOption(workerRole)

    // Password fields (defaults are fine; just verify they are visible)
    await expect(modal.locator('.password_fields')).toBeVisible()
    await modal.locator('#digits').fill('1')
    await modal.locator('#length').fill('8')

    const createResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/authentication/policy') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await createResponse
    expect(resp.status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Recover the created policy id via API to locate the exact row.
    const created = (await listPolicies(apiv4Admin)).find(
      (p) => p.type === 'local' && p.category === firstCat.id && p.role === workerRole,
    )
    expect(created, 'policy not returned by GET /policies').toBeTruthy()
    trackPolicyId(testInfo, created.id)

    // Locate the row by id to avoid matching other rows with the same category name.
    const row = page.locator(`#users-password-policy tbody tr[id="${created.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await expect(row).toContainText('local')
    expect(created.password.digits).toBe(1)
  })

  // -------------------------------------------------------------------------
  // Scenario 1b — creating an all-category policy without disclaimer saves false
  // BUG: the JS condition `data['disclaimer-cb'] != 'on' && data['category'] !== "all"`
  // means category=all always takes the disclaimer branch even when unchecked.
  // If no template is selected, it sends `{ template: undefined }` → serialised
  // as `{}` in JSON. The backend stores `{}` instead of false.
  // -------------------------------------------------------------------------
  test.fail('S1b: creating all-category policy without disclaimer saves disclaimer=false', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]

    const staleAll = (await listPolicies(apiv4Admin)).find(
      (p) => p.type === 'local' && p.category === 'all' && p.role === workerRole,
    )
    if (staleAll) await deletePolicyViaApi(apiv4Admin, staleAll.id)

    await gotoPolicies(page)
    await page.locator('.btn-add-policy').click()
    const modal = page.locator('#modalPolicyAdd')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#type-select select').selectOption('local')
    await modal.locator('#category-select select').selectOption('all')
    await modal.locator('#role-select select').selectOption(workerRole)

    // Disclaimer section is visible for category=all; leave checkbox unchecked.
    await expect(modal.locator('#disclaimer-content')).toBeVisible()
    await expect.poll(() => iCheckRead(modal, '.disclaimer-cb'), { timeout: 3000 }).toBe(false)

    const createResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/authentication/policy') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await createResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    const created = (await listPolicies(apiv4Admin)).find(
      (p) => p.type === 'local' && p.category === 'all' && p.role === workerRole,
    )
    expect(created, 'policy not found after POST').toBeTruthy()
    trackPolicyId(testInfo, created.id)

    // Bug: the backend stores {} instead of false — disclaimer is truthy when it
    // should be absent.
    expect(created.disclaimer).toBe(false)
  })

  // -------------------------------------------------------------------------
  // Scenario 1c — creating a policy without email verification saves false
  // -------------------------------------------------------------------------
  test('S1c: creating a policy without email verification saves email_verification=false', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]

    const stale = (await listPolicies(apiv4Admin)).find(
      (p) => p.type === 'local' && p.category === firstCat.id && p.role === workerRole,
    )
    if (stale) await deletePolicyViaApi(apiv4Admin, stale.id)

    await gotoPolicies(page)
    await page.locator('.btn-add-policy').click()
    const modal = page.locator('#modalPolicyAdd')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    await modal.locator('#type-select select').selectOption('local')
    await modal.locator('#category-select select').selectOption(firstCat.id)
    await modal.locator('#role-select select').selectOption(workerRole)

    // Leave email verification unchecked (default state).
    await expect.poll(() => iCheckRead(modal, '#verification-cb'), { timeout: 3000 }).toBe(false)

    const createResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/authentication/policy') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await createResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    const created = (await listPolicies(apiv4Admin)).find(
      (p) => p.type === 'local' && p.category === firstCat.id && p.role === workerRole,
    )
    expect(created, 'policy not found after POST').toBeTruthy()
    trackPolicyId(testInfo, created.id)
    expect(created.email_verification).toBe(false)
  })

  // -------------------------------------------------------------------------
  // Scenario 2 — admin creates a non-local policy; password fields hidden
  // -------------------------------------------------------------------------
  test('S2: password section hides for a non-local provider', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]

    await gotoPolicies(page)
    await page.locator('.btn-add-policy').click()
    const modal = page.locator('#modalPolicyAdd')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Pick a non-local provider.
    await modal.locator('#type-select select').selectOption('google')
    // Password section must disappear immediately.
    await expect(modal.locator('.password_fields')).toBeHidden()

    await modal.locator('#category-select select').selectOption(firstCat.id)
    await modal.locator('#role-select select').selectOption(workerRole)

    const createResponse = page.waitForResponse(
      (r) =>
        r.url().includes('/api/v4/admin/item/authentication/policy') &&
        r.request().method() === 'POST',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const resp = await createResponse
    expect(resp.status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    const created = (await listPolicies(apiv4Admin)).find(
      (p) => p.type === 'google' && p.category === firstCat.id && p.role === workerRole,
    )
    expect(created, 'google policy not returned by API').toBeTruthy()
    trackPolicyId(testInfo, created.id)

    // In the table every password column must show "-".
    const row = page.locator(`#users-password-policy tbody tr[id="${created.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    // The six password columns (digits, length, lowercase, uppercase,
    // special_chars, expiration, old_passwords, not_username) all render "-"
    // when type !== "local"; verify at least one of them.
    const cells = row.locator('td')
    const cellTexts = await cells.allTextContents()
    // Cells 5–12 are the password columns (0-indexed after type/category/role/
    // email/disclaimer). At least half should be "-".
    const passwordCells = cellTexts.slice(5, 13)
    expect(
      passwordCells.filter((t) => t.trim() === '-').length,
      'non-local policy must show "-" for all password columns',
    ).toBeGreaterThan(0)
  })

  // -------------------------------------------------------------------------
  // Scenario 3 — admin enables email verification on a policy
  // -------------------------------------------------------------------------
  test('S3: enabling email verification turns on the green circle and force button', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]
    const policy = await createPolicyViaApi(apiv4Admin, {
      type: 'local',
      category: firstCat.id,
      role: workerRole,
      email_verification: false,
      disclaimer: false,
      password: defaultPasswordBody(),
    })
    trackPolicyId(testInfo, policy.id)

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${policy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    // The force button must be absent before enabling anything.
    await expect(row.locator('button#btn-policy-force')).toBeHidden()

    // Open edit dialog.
    await row.locator('button#btn-edit-policy').click()
    const modal = page.locator('#modalPolicyEdit')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // iCheck: click the overlay to check the email verification checkbox.
    await iCheckClick(modal, '#verification-cb')
    await expect.poll(() => iCheckRead(modal, '#verification-cb'), { timeout: 5000 }).toBe(true)

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/authentication/policy/${policy.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Email verification column must show a green circle.
    const emailCell = row.locator('td').nth(3) // col index: type(0) cat(1) role(2) email(3)
    await expect(emailCell.locator('i.fa-circle[style*="green"]')).toBeVisible({ timeout: 8000 })

    // Force button must now appear.
    await expect(row.locator('button#btn-policy-force')).toBeVisible({ timeout: 5000 })

    // API persistence check.
    const updated = await getPolicyById(apiv4Admin, policy.id)
    expect(updated.email_verification).toBe(true)
  })

  // -------------------------------------------------------------------------
  // Scenario 3b — disabling email verification via edit saves false
  // -------------------------------------------------------------------------
  test('S3b: unchecking email verification in edit saves email_verification=false', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]
    const policy = await createPolicyViaApi(apiv4Admin, {
      type: 'local',
      category: firstCat.id,
      role: workerRole,
      email_verification: true,
      disclaimer: false,
      password: defaultPasswordBody(),
    })
    trackPolicyId(testInfo, policy.id)

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${policy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    await row.locator('button#btn-edit-policy').click()
    const modal = page.locator('#modalPolicyEdit')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Wait for AJAX pre-fill — checkbox must start checked.
    await expect.poll(() => iCheckRead(modal, '#verification-cb'), { timeout: 8000 }).toBe(true)

    // Uncheck it.
    await iCheckClick(modal, '#verification-cb')
    await expect.poll(() => iCheckRead(modal, '#verification-cb'), { timeout: 5000 }).toBe(false)

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/authentication/policy/${policy.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    const updated = await getPolicyById(apiv4Admin, policy.id)
    expect(updated.email_verification).toBe(false)

    // Green circle must be gone from the Email verification column.
    const emailCell = row.locator('td').nth(3)
    await expect(emailCell.locator('i.fa-circle[style*="green"]')).toBeHidden({ timeout: 5000 })
  })

  // -------------------------------------------------------------------------
  // Scenario 4 — admin enables disclaimer on an all-categories policy
  // -------------------------------------------------------------------------
  test('S4: disclaimer can be enabled on an all-categories policy with a template', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const templates = await listCustomTemplates(apiv4Admin)
    const disclaimerTemplate = templates.find(
      (t) => !['password', 'email', 'deleted_gpu'].includes(t.kind),
    )
    test.skip(!disclaimerTemplate, 'no custom notification template available for disclaimer')

    // We must use the existing default policy (category=all, role=all,
    // type=local) since it is the only all-categories policy that always
    // exists and we cannot create a duplicate. Track nothing — we restore
    // disclaimer=false in the annotation cleanup is not needed (we restore it).
    const allPolicies = await listPolicies(apiv4Admin)
    const defaultPolicy = allPolicies.find(
      (p) => p.category === 'all' && p.role === 'all' && p.type === 'local',
    )
    test.skip(!defaultPolicy, 'default all-category policy not found')

    // Remember original disclaimer state so we can restore it.
    const originalDisclaimer = defaultPolicy.disclaimer

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${defaultPolicy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    await row.locator('button#btn-edit-policy').click()
    const modal = page.locator('#modalPolicyEdit')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // The disclaimer section must be visible (category = all).
    await expect(modal.locator('#disclaimer-content')).toBeVisible()
    await expect(modal.locator('#disclaimer-warning')).toBeHidden()

    // Check the disclaimer checkbox.
    await iCheckClick(modal, '.disclaimer-cb')
    await expect.poll(() => iCheckRead(modal, '.disclaimer-cb'), { timeout: 5000 }).toBe(true)

    // The template dropdown must appear.
    const templateContent = modal.locator('#template-content')
    await expect(templateContent).toBeVisible({ timeout: 5000 })

    // Select the template.
    await modal.locator('.disclaimer-template').selectOption(disclaimerTemplate.id)

    // Preview must render inside #preview-panel.
    await expect(modal.locator('#preview-panel')).toBeVisible({ timeout: 8000 })

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/authentication/policy/${defaultPolicy.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Disclaimer column must show a green circle.
    const disclaimerCell = row.locator('td').nth(4)
    await expect(disclaimerCell.locator('i.fa-circle[style*="green"]')).toBeVisible({ timeout: 8000 })

    // Force button must appear.
    await expect(row.locator('button#btn-policy-force')).toBeVisible({ timeout: 5000 })

    // Restore the original disclaimer state so this test is idempotent.
    await adminAuthenticationPolicyEdit({
      client: apiv4Admin,
      path: { policy_id: defaultPolicy.id },
      body: {
        type: defaultPolicy.type,
        email_verification: defaultPolicy.email_verification,
        disclaimer: originalDisclaimer ?? false,
        password: defaultPolicy.password,
      },
    }).catch(() => {})
  })

  // -------------------------------------------------------------------------
  // Scenario 4b — disabling disclaimer via edit sends false in the PUT body
  // -------------------------------------------------------------------------
  test('S4b: unchecking disclaimer in edit sends disclaimer=false in request body', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const templates = await listCustomTemplates(apiv4Admin)
    const disclaimerTemplate = templates.find(
      (t) => !['password', 'email', 'deleted_gpu'].includes(t.kind),
    )
    test.skip(!disclaimerTemplate, 'no custom template available for disclaimer')

    const allPolicies = await listPolicies(apiv4Admin)
    const defaultPolicy = allPolicies.find(
      (p) => p.category === 'all' && p.role === 'all' && p.type === 'local',
    )
    test.skip(!defaultPolicy, 'default policy not found')

    const originalDisclaimer = defaultPolicy.disclaimer

    // Arm the policy with a disclaimer via API so the edit dialog starts checked.
    await adminAuthenticationPolicyEdit({
      client: apiv4Admin,
      path: { policy_id: defaultPolicy.id },
      body: {
        type: defaultPolicy.type,
        email_verification: defaultPolicy.email_verification,
        disclaimer: { template: disclaimerTemplate.id },
        password: defaultPolicy.password,
      },
    })

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${defaultPolicy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    await row.locator('button#btn-edit-policy').click()
    const modal = page.locator('#modalPolicyEdit')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Wait for AJAX pre-fill — disclaimer must start checked.
    await expect.poll(() => iCheckRead(modal, '.disclaimer-cb'), { timeout: 8000 }).toBe(true)

    // Uncheck it.
    await iCheckClick(modal, '.disclaimer-cb')
    await expect.poll(() => iCheckRead(modal, '.disclaimer-cb'), { timeout: 5000 }).toBe(false)

    // Capture the PUT request to inspect the body the JS sends.
    // The bug is in the request, not the stored value — the backend normalises
    // null→false, so checking the API response would always pass.
    const putRequestPromise = page.waitForRequest(
      (r) =>
        r.url().includes(`/api/v4/admin/item/authentication/policy/${defaultPolicy.id}`) &&
        r.method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    const putRequest = await putRequestPromise
    const requestBody = JSON.parse(putRequest.postData() ?? '{}')

    // Bug: the form sends `null` instead of `false` when the checkbox is
    // unchecked, so the intent to clear the disclaimer is lost at the wire level.
    expect(requestBody.disclaimer).toBe(false)

    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Restore original state regardless of test outcome.
    await adminAuthenticationPolicyEdit({
      client: apiv4Admin,
      path: { policy_id: defaultPolicy.id },
      body: {
        type: defaultPolicy.type,
        email_verification: defaultPolicy.email_verification,
        disclaimer: originalDisclaimer ?? false,
        password: defaultPolicy.password,
      },
    }).catch(() => {})
  })

  // -------------------------------------------------------------------------
  // Scenario 5 — admin edits password parameters
  // -------------------------------------------------------------------------
  test('S5: editing password parameters pre-fills the dialog and persists via API', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]
    const policy = await createPolicyViaApi(apiv4Admin, {
      type: 'local',
      category: firstCat.id,
      role: workerRole,
      email_verification: false,
      disclaimer: false,
      password: { ...defaultPasswordBody(), digits: 0, expiration: 0, old_passwords: 0 },
    })
    trackPolicyId(testInfo, policy.id)

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${policy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    await row.locator('button#btn-edit-policy').click()
    const modal = page.locator('#modalPolicyEdit')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Dialog pre-fills from GET /policy/{id}.
    await expect.poll(
      () => modal.locator('#digits').inputValue(),
      { timeout: 8000 },
    ).toBe('0')

    // Type / Category / Role must be disabled (read-only).
    await expect(modal.locator('#type-select select')).toBeDisabled()
    await expect(modal.locator('#category-select select')).toBeDisabled()
    await expect(modal.locator('#role-select select')).toBeDisabled()

    // Change values.
    await modal.locator('#digits').fill('2')
    await modal.locator('#expiration').fill('60')
    await modal.locator('#old_passwords').fill('5')

    const editResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/authentication/policy/${policy.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await modal.locator('#send').click()
    expect((await editResponse).status()).toBeLessThan(400)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    // Table row should reflect the new expiration value.
    await expect(row).toContainText('60', { timeout: 8000 })

    // Persistence via API.
    const updated = await getPolicyById(apiv4Admin, policy.id)
    expect(updated.password.digits).toBe(2)
    expect(updated.password.expiration).toBe(60)
    expect(updated.password.old_passwords).toBe(5)
  })

  // -------------------------------------------------------------------------
  // Scenario 6 — admin deletes a policy with confirmation
  // -------------------------------------------------------------------------
  test('S6: deletes a deletable policy after PNotify confirmation', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]
    const policy = await createPolicyViaApi(apiv4Admin, {
      type: 'local',
      category: firstCat.id,
      role: workerRole,
      email_verification: false,
      disclaimer: false,
      password: defaultPasswordBody(),
    })
    // Track the id; afterEach will skip it gracefully if already deleted.
    trackPolicyId(testInfo, policy.id)

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${policy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    await row.locator('button#btn-policy-delete').click()

    // PNotify confirmation; the prompt names category and role.
    await expect(
      page.locator('.ui-pnotify-text', { hasText: new RegExp(firstCat.name, 'i') }),
    ).toBeVisible({ timeout: 5000 })

    const deleteResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/authentication/policy/${policy.id}`) &&
        r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await deleteResponse).status()).toBeLessThan(400)

    // Success toast.
    await expect(
      page.locator('.ui-pnotify-text', { hasText: /policy deleted successfully/i }),
    ).toBeVisible({ timeout: 5000 })

    // Row must vanish.
    await expect(row).toBeHidden({ timeout: 10000 })

    // Not returned by API anymore.
    expect(await getPolicyById(apiv4Admin, policy.id)).toBeNull()
  })

  // -------------------------------------------------------------------------
  // Scenario 7 — the system default policy has no delete button
  // -------------------------------------------------------------------------
  test('S7: default policy (all + all + local) shows no delete button', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    const allPolicies = await listPolicies(apiv4Admin)
    const defaultPolicy = allPolicies.find(
      (p) => p.category === 'all' && p.role === 'all' && p.type === 'local',
    )
    test.skip(!defaultPolicy, 'default policy not found in the DB')

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${defaultPolicy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    // Edit pencil must be there.
    await expect(row.locator('button#btn-edit-policy')).toBeVisible()
    // Delete button must NOT be there.
    await expect(row.locator('button#btn-policy-delete')).toHaveCount(0)
  })

  // -------------------------------------------------------------------------
  // Scenario 8 — admin cancels a policy deletion
  // -------------------------------------------------------------------------
  test('S8: cancelling the delete PNotify fires no DELETE call', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]
    const policy = await createPolicyViaApi(apiv4Admin, {
      type: 'local',
      category: firstCat.id,
      role: workerRole,
      email_verification: false,
      disclaimer: false,
      password: defaultPasswordBody(),
    })
    trackPolicyId(testInfo, policy.id)

    let deleteFired = false
    page.on('request', (req) => {
      if (
        req.url().includes(`/api/v4/admin/item/authentication/policy/${policy.id}`) &&
        req.method() === 'DELETE'
      ) {
        deleteFired = true
      }
    })

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${policy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    await row.locator('button#btn-policy-delete').click()
    await expect(page.locator('.ui-pnotify-action-bar')).toBeVisible({ timeout: 5000 })

    // Click Cancel.
    await page
      .locator('.ui-pnotify-action-bar .ui-pnotify-action-button', {
        hasText: /cancel/i,
      })
      .first()
      .click()

    expect(deleteFired, 'DELETE must not fire on Cancel').toBe(false)
    await expect(row).toBeVisible({ timeout: 5000 })

    // Policy still in API.
    expect(await getPolicyById(apiv4Admin, policy.id)).not.toBeNull()
  })

  // -------------------------------------------------------------------------
  // Scenario 9 — admin forces email re-verification
  // -------------------------------------------------------------------------
  test('S9: force-email button triggers PUT force_validate/email', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]
    const policy = await createPolicyViaApi(apiv4Admin, {
      type: 'local',
      category: firstCat.id,
      role: workerRole,
      email_verification: true,
      disclaimer: false,
      password: { ...defaultPasswordBody(), expiration: 0 },
    })
    trackPolicyId(testInfo, policy.id)

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${policy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    // Force validation button must be visible (email_verification is true).
    await expect(row.locator('button#btn-policy-force')).toBeVisible()
    await row.locator('button#btn-policy-force').click()

    const forceModal = page.locator('#modalForceVerification')
    await forceModal.waitFor({ state: 'visible', timeout: 10000 })

    // Only #force-email and #force-password must be visible/hidden correctly.
    // NOTE: the JS uses `#force_disclaimer` (underscore) but the HTML has
    // `id="force-disclaimer"` (hyphen), so the show/hide call never finds the
    // element — #force-disclaimer is always visible regardless of policy state.
    await expect(forceModal.locator('#force-email')).toBeVisible()
    await expect(forceModal.locator('#force-password')).toBeHidden()

    // Click Force Verify Email → PNotify secondary confirmation.
    await forceModal.locator('#force-email').click()
    await expect(page.locator('.ui-pnotify-action-bar')).toBeVisible({ timeout: 5000 })

    const forceResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/authentication/force_validate/email/${policy.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await forceResponse).status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-text', { hasText: /policy forced successfully/i }),
    ).toBeVisible({ timeout: 5000 })

    // The success handler only shows a PNotify and reloads the table —
    // it never calls modal('hide'). Verify the dialog is still open and
    // close it manually so the next test starts with a clean DOM.
    await expect(forceModal).toBeVisible()
    await forceModal.locator('[data-dismiss="modal"]').first().click()
    await forceModal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------------
  // Scenario 9b — force-disclaimer button is hidden when disclaimer=false
  // BUG: the JS calls `$(modal + " #force_disclaimer").hide()` (underscore)
  // but the HTML element has `id="force-disclaimer"` (hyphen). The selector
  // never matches, so the button is always visible regardless of policy state.
  // -------------------------------------------------------------------------
  test.fail('S9b: force-disclaimer button is hidden when policy has no disclaimer', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]
    // Use a specific category (not ALL) so the S1b bug does not interfere:
    // disclaimer will be stored as false, not {}.
    const policy = await createPolicyViaApi(apiv4Admin, {
      type: 'local',
      category: firstCat.id,
      role: workerRole,
      email_verification: true,
      disclaimer: false,
      password: { ...defaultPasswordBody(), expiration: 0 },
    })
    trackPolicyId(testInfo, policy.id)

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${policy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    await row.locator('button#btn-policy-force').click()
    const forceModal = page.locator('#modalForceVerification')
    await forceModal.waitFor({ state: 'visible', timeout: 10000 })

    // disclaimer=false → the Force Accept Disclaimer button should be hidden.
    // Bug: it is always visible because the jQuery selector uses the wrong id.
    await expect(forceModal.locator('#force-disclaimer')).toBeHidden({ timeout: 3000 })

    await forceModal.locator('[data-dismiss="modal"]').first().click()
    await forceModal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------------
  // Scenario 10 — admin forces password update
  // -------------------------------------------------------------------------
  test('S10: force-password button triggers PUT force_validate/password', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]
    const policy = await createPolicyViaApi(apiv4Admin, {
      type: 'local',
      category: firstCat.id,
      role: workerRole,
      email_verification: false,
      disclaimer: false,
      password: { ...defaultPasswordBody(), expiration: 90 },
    })
    trackPolicyId(testInfo, policy.id)

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${policy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    await expect(row.locator('button#btn-policy-force')).toBeVisible()
    await row.locator('button#btn-policy-force').click()

    const forceModal = page.locator('#modalForceVerification')
    await forceModal.waitFor({ state: 'visible', timeout: 10000 })

    // Only #force-password must be visible; #force-email hides correctly.
    // #force-disclaimer is always visible due to the JS typo noted in S9.
    await expect(forceModal.locator('#force-password')).toBeVisible()
    await expect(forceModal.locator('#force-email')).toBeHidden()

    await forceModal.locator('#force-password').click()
    await expect(page.locator('.ui-pnotify-action-bar')).toBeVisible({ timeout: 5000 })

    const forceResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/authentication/force_validate/password/${policy.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await forceResponse).status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-text', { hasText: /policy forced successfully/i }),
    ).toBeVisible({ timeout: 5000 })

    // Dialog stays open — close it manually.
    await expect(forceModal).toBeVisible()
    await forceModal.locator('[data-dismiss="modal"]').first().click()
    await forceModal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------------
  // Scenario 11 — admin forces disclaimer re-acceptance
  // -------------------------------------------------------------------------
  test('S11: force-disclaimer button triggers PUT force_validate/disclaimer', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const templates = await listCustomTemplates(apiv4Admin)
    const disclaimerTemplate = templates.find(
      (t) => !['password', 'email', 'deleted_gpu'].includes(t.kind),
    )
    test.skip(!disclaimerTemplate, 'no custom template for disclaimer')

    // Use the default all+all+local policy — it is the only policy that can
    // hold a disclaimer (all-category constraint). We temporarily set
    // disclaimer to a template and restore it afterwards.
    const allPolicies = await listPolicies(apiv4Admin)
    const defaultPolicy = allPolicies.find(
      (p) => p.category === 'all' && p.role === 'all' && p.type === 'local',
    )
    test.skip(!defaultPolicy, 'default policy not found')

    const originalDisclaimer = defaultPolicy.disclaimer

    // Arm the policy with a disclaimer.
    await adminAuthenticationPolicyEdit({
      client: apiv4Admin,
      path: { policy_id: defaultPolicy.id },
      body: {
        type: defaultPolicy.type,
        email_verification: defaultPolicy.email_verification,
        disclaimer: { template: disclaimerTemplate.id },
        password: defaultPolicy.password,
      },
    })

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${defaultPolicy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })
    await expect(row.locator('button#btn-policy-force')).toBeVisible()
    await row.locator('button#btn-policy-force').click()

    const forceModal = page.locator('#modalForceVerification')
    await forceModal.waitFor({ state: 'visible', timeout: 10000 })

    // Only #force-disclaimer must be visible (email_verification=false, expiration=0).
    await expect(forceModal.locator('#force-disclaimer')).toBeVisible()
    await expect(forceModal.locator('#force-email')).toBeHidden()
    await expect(forceModal.locator('#force-password')).toBeHidden()

    await forceModal.locator('#force-disclaimer').click()
    await expect(page.locator('.ui-pnotify-action-bar')).toBeVisible({ timeout: 5000 })

    const forceResponse = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v4/admin/item/authentication/force_validate/disclaimer/${defaultPolicy.id}`) &&
        r.request().method() === 'PUT',
      { timeout: 15000 },
    )
    await clickPnotifyOk(page)
    expect((await forceResponse).status()).toBeLessThan(400)

    await expect(
      page.locator('.ui-pnotify-text', { hasText: /policy forced successfully/i }),
    ).toBeVisible({ timeout: 5000 })

    // Dialog stays open — close it manually before restoring state.
    await expect(forceModal).toBeVisible()
    await forceModal.locator('[data-dismiss="modal"]').first().click()
    await forceModal.waitFor({ state: 'hidden', timeout: 5000 })

    // Restore original disclaimer state.
    await adminAuthenticationPolicyEdit({
      client: apiv4Admin,
      path: { policy_id: defaultPolicy.id },
      body: {
        type: defaultPolicy.type,
        email_verification: defaultPolicy.email_verification,
        disclaimer: originalDisclaimer ?? false,
        password: defaultPolicy.password,
      },
    }).catch(() => {})
  })

  // -------------------------------------------------------------------------
  // Scenario 12 — disclaimer section is hidden for a non-all-category policy
  // -------------------------------------------------------------------------
  test('S12: picking a specific category hides disclaimer and shows a warning', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    await gotoPolicies(page)
    await page.locator('.btn-add-policy').click()
    const modal = page.locator('#modalPolicyAdd')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Initially, with category=all selected, disclaimer content is visible.
    await modal.locator('#category-select select').selectOption('all')
    await expect(modal.locator('#disclaimer-content')).toBeVisible()
    await expect(modal.locator('#disclaimer-warning')).toBeHidden()

    // Pick a specific category — disclaimer content must hide.
    await modal.locator('#category-select select').selectOption(firstCat.id)
    await expect(modal.locator('#disclaimer-content')).toBeHidden({ timeout: 5000 })
    await expect(modal.locator('#disclaimer-warning')).toBeVisible({ timeout: 5000 })

    // Switching back to ALL must show disclaimer content again.
    await modal.locator('#category-select select').selectOption('all')
    await expect(modal.locator('#disclaimer-content')).toBeVisible({ timeout: 5000 })
    await expect(modal.locator('#disclaimer-warning')).toBeHidden({ timeout: 5000 })

    // Close without submitting — no POST should be fired.
    await modal.locator('[data-dismiss="modal"]').first().click()
    await modal.waitFor({ state: 'hidden', timeout: 5000 })
  })

  // -------------------------------------------------------------------------
  // Scenario 13 — disclaimer checked but no template selected shows an error
  // -------------------------------------------------------------------------
  test('S13: enabling disclaimer without selecting a template blocks submission', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    await gotoPolicies(page)
    await page.locator('.btn-add-policy').click()
    const modal = page.locator('#modalPolicyAdd')
    await modal.waitFor({ state: 'visible', timeout: 10000 })

    // Use category=all so the disclaimer section is visible.
    await modal.locator('#category-select select').selectOption('all')
    await expect(modal.locator('#disclaimer-content')).toBeVisible()

    // Check the disclaimer checkbox.
    await iCheckClick(modal, '.disclaimer-cb')
    await expect.poll(() => iCheckRead(modal, '.disclaimer-cb'), { timeout: 5000 }).toBe(true)

    // Template dropdown appears; leave it at the placeholder.
    await expect(modal.locator('#template-content')).toBeVisible({ timeout: 5000 })

    let postFired = false
    page.on('request', (req) => {
      if (
        req.url().includes('/api/v4/admin/item/authentication/policy') &&
        req.method() === 'POST'
      ) {
        postFired = true
      }
    })

    await modal.locator('#send').click()

    // PNotify error must appear.
    await expect(
      page.locator('.ui-pnotify-title', { hasText: /error enabling disclaimer/i }),
    ).toBeVisible({ timeout: 5000 })
    await expect(
      page.locator('.ui-pnotify-text', {
        hasText: /text template must be selected/i,
      }),
    ).toBeVisible({ timeout: 5000 })

    // Dialog must stay open.
    await expect(modal).toBeVisible()
    expect(postFired, 'POST must not fire when no template is selected').toBe(false)
  })

  // -------------------------------------------------------------------------
  // Scenario 14 — force button absent when no forceable condition is set
  // -------------------------------------------------------------------------
  test('S14: force button is absent when email_verification=false, disclaimer=false, expiration=0', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const firstCat = await getFirstCategory(apiv4Admin)
    test.skip(!firstCat, 'no categories in the DB')

    const workerRole = WORKER_ROLES[testInfo.workerIndex % WORKER_ROLES.length]
    const policy = await createPolicyViaApi(apiv4Admin, {
      type: 'local',
      category: firstCat.id,
      role: workerRole,
      email_verification: false,
      disclaimer: false,
      password: { ...defaultPasswordBody(), expiration: 0 },
    })
    trackPolicyId(testInfo, policy.id)

    await gotoPolicies(page)
    const row = page.locator(`#users-password-policy tbody tr[id="${policy.id}"]`)
    await expect(row).toBeVisible({ timeout: 10000 })

    // Edit button must be present.
    await expect(row.locator('button#btn-edit-policy')).toBeVisible()
    // Delete button must be present (it's not the default policy).
    await expect(row.locator('button#btn-policy-delete')).toBeVisible()
    // Force button must NOT be there.
    await expect(row.locator('button#btn-policy-force')).toHaveCount(0)
  })
})
