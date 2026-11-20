// E2E tests for Config → Frontend (/isard-admin/admin/frontend_mode).
// Spec: testing/e2e/specs/webapp/frontend_mode_rules.md — SECTION A only.
// Sections B (API contract) and C (effect of the rule on the user) are
// covered apart.
//
// Conventions:
//   - The rules are global configuration: the file runs serially and every
//     rule targets the dedicated `fmre2e` seed accounts, which no spec
//     logs in with, so no parallel spec ever changes frontend.
//   - Rules are tracked via testInfo.annotations ('frontend-mode-rule-id')
//     and deleted in afterEach, even when assertions fail. Names carry the
//     `e2e-fmr-` prefix so beforeAll can purge the leftovers of an aborted
//     run.
//   - iCheck hides the real <input>: the alloweds checkboxes are toggled
//     through the sibling <ins class="iCheck-helper"> and read back from
//     the native input state.
//   - "Without reloading the page" is asserted with a marker set on
//     `window` after the first load: it only survives if the table was
//     refreshed in place.

import {
  test,
  expect,
  apiv4ClientForPage,
  track,
  cleanupTrackedResources,
  E2E_FRONTEND_MODE_RULE_PREFIX,
  listFrontendModeRules,
  findFrontendModeRuleByName,
  nextFrontendModeRulePriority,
  createFrontendModeRuleAndTrack,
  purgeE2eFrontendModeRules,
} from '../../fixtures/apiv4/index.js'
import { bridgeAdminSession } from '../../fixtures/common.js'
import { deleteFrontendModeRule, getFrontendModeRule } from '../../src/gen/apiv4/sdk.gen'

const FRONTEND_MODE_URL = '/isard-admin/admin/frontend_mode'
const RULES_API = '/api/v4/items/frontend-mode-rules'
const RULE_API = '/api/v4/item/frontend-mode-rule'
const ALLOWED_TABLE_API = '/api/v4/item/allowed/table/frontend_mode_rules'
const ALLOWED_UPDATE_API = '/api/v4/item/allowed/update/frontend_mode_rules'

const TABLE = '#frontend-mode-rules-table'
const RULE_MODAL = '#modalFrontendModeRule'
const ALLOWEDS_MODAL = '#modalAlloweds'
const DIMENSIONS = ['roles', 'categories', 'groups', 'users']

const MODE_DESCRIPTIONS = {
  deprecated: 'Only the old frontend is allowed',
  actual: 'Only the new frontend is allowed',
  all: 'Both frontends are allowed, with a switch in the UI',
  hidden: 'Both frontends are allowed, without the UI switch',
}

const DUPLICATED_PRIORITY = 'Another rule already has this priority.'

// Seeded in testing/src/isardvdi_testing/data (category `fmre2e`).
const USER_A = { id: 'fmre2e-user-a', name: 'FMR E2E User A' }
const USER_B = { id: 'fmre2e-user-b', name: 'FMR E2E User B' }
const GROUP_B = { id: 'fmre2e-group-b', name: 'FMR E2E Group B' }

const NO_ALLOWED = { users: false, groups: false, categories: false, roles: false }

function ruleName(scenario) {
  return `${E2E_FRONTEND_MODE_RULE_PREFIX}${scenario}-${Date.now()}`
}

const pathOf = (url) => new URL(url).pathname
const isRulesList = (r) => pathOf(r.url()) === RULES_API && r.request().method() === 'GET'
const isRuleCreate = (r) => pathOf(r.url()) === RULE_API && r.request().method() === 'POST'

// Counts the requests matching `predicate` from now on.
function countRequests(page, predicate) {
  const seen = { count: 0 }
  page.on('request', (req) => {
    if (predicate(req)) seen.count += 1
  })
  return seen
}

const createRequests = (page) =>
  countRequests(page, (req) => pathOf(req.url()) === RULE_API && req.method() === 'POST')

const isRuleRequest = (id, method) => (r) =>
  pathOf(r.url()) === `${RULE_API}/${id}` && r.request().method() === method

const updateRequests = (page) => countRequests(page, (req) => req.method() === 'PUT')

async function gotoFrontendMode(page) {
  const listResp = page.waitForResponse(isRulesList, { timeout: 15000 })
  await page.goto(FRONTEND_MODE_URL)
  expect((await listResp).status()).toBeLessThan(400)
  await page.locator(`${TABLE} tbody tr`).first().waitFor({ state: 'visible', timeout: 15000 })
  await page.evaluate(() => {
    window.__e2eFrontendModeLoaded = true
  })
}

async function expectNoPageReload(page) {
  expect(
    await page.evaluate(() => window.__e2eFrontendModeLoaded === true),
    'the page must not be reloaded',
  ).toBe(true)
}

const ruleRow = (page, id) => page.locator(`${TABLE} tbody tr[id="${id}"]`)
const ruleRowByName = (page, name) =>
  page.locator(`${TABLE} tbody tr`).filter({ has: page.getByRole('cell', { name, exact: true }) })

async function tableRowIds(page) {
  return page.locator(`${TABLE} tbody tr`).evaluateAll((rows) => rows.map((row) => row.id))
}

async function openAddDialog(page) {
  await page.locator('.btn-add-frontend-mode-rule').click()
  const modal = page.locator(RULE_MODAL)
  await modal.waitFor({ state: 'visible', timeout: 10000 })
  return modal
}

async function fillRuleForm(modal, { name, description, mode, priority }) {
  if (name !== undefined) await modal.locator('#name').fill(name)
  if (description !== undefined) await modal.locator('#description').fill(description)
  if (mode !== undefined) await modal.locator('#frontend_mode').selectOption(mode)
  if (priority !== undefined) await modal.locator('#priority').fill(String(priority))
}

// Presses #btn-edit on a row and waits for the GET that pre-fills the dialog.
async function openEditDialog(page, id) {
  const prefillResp = page.waitForResponse(isRuleRequest(id, 'GET'), { timeout: 15000 })
  await ruleRow(page, id).locator('#btn-edit').click()
  const prefill = await prefillResp
  const modal = page.locator(RULE_MODAL)
  await modal.waitFor({ state: 'visible', timeout: 10000 })
  return { modal, prefill }
}

async function submitAndUpdate(page, modal, id) {
  const updateResp = page.waitForResponse(isRuleRequest(id, 'PUT'), { timeout: 15000 })
  await modal.locator('#send').click()
  return updateResp
}

async function cancelRuleDialog(modal) {
  await modal.locator('.modal-footer button', { hasText: 'Cancel' }).click()
  await modal.waitFor({ state: 'hidden', timeout: 10000 })
}

async function submitAndCreate(page, modal) {
  const createResp = page.waitForResponse(isRuleCreate, { timeout: 15000 })
  await modal.locator('#send').click()
  return createResp
}

const allowedCheckbox = (scope, dimension) => scope.locator(`#a-${dimension}-cb`)
const allowedSelect = (scope, dimension) => scope.locator(`#a-${dimension}`)

async function toggleAllowed(scope, dimension) {
  await scope.locator(`#${dimension}_pannel ins.iCheck-helper`).last().click()
}

// Searches `item` in the dimension's Select2 and picks it, as a user would.
async function pickAllowed(page, scope, dimension, item) {
  const panel = scope.locator(`#${dimension}_pannel`)
  const search = panel.locator('.select2-search__field')
  await search.click()
  await search.pressSequentially(item.name)
  await page
    .locator('.select2-results__option', { hasText: item.name })
    .first()
    .click({ timeout: 10000 })
  await expect(allowedSelect(scope, dimension)).toHaveValues([item.id])
}

async function expectAllDimensionsUnchecked(scope) {
  for (const dimension of DIMENSIONS) {
    await expect(allowedCheckbox(scope, dimension)).not.toBeChecked()
  }
}

// Opens the shared alloweds dialog of a row and waits for its pre-fill.
async function openAllowedsDialog(page, id) {
  const prefillResp = page.waitForResponse(
    (r) => pathOf(r.url()) === ALLOWED_TABLE_API && r.request().method() === 'POST',
    { timeout: 15000 },
  )
  await ruleRow(page, id).locator('#btn-alloweds').click()
  const prefill = await prefillResp
  const modal = page.locator(ALLOWEDS_MODAL)
  await modal.waitFor({ state: 'visible', timeout: 10000 })
  return { modal, prefill }
}

async function saveAlloweds(page, modal) {
  const updateResp = page.waitForResponse(
    (r) => pathOf(r.url()) === ALLOWED_UPDATE_API && r.request().method() === 'POST',
    { timeout: 15000 },
  )
  await modal.locator('#send').click()
  const response = await updateResp
  await modal.waitFor({ state: 'hidden', timeout: 10000 })
  return response
}

const confirmNotice = (page) => page.locator('.ui-pnotify', { hasText: 'Confirmation Needed' })

async function answerConfirm(page, answer) {
  await confirmNotice(page)
    .locator('.ui-pnotify-action-button', { hasText: new RegExp(`^${answer}$`, 'i') })
    .click({ timeout: 5000 })
  await expect(confirmNotice(page)).toBeHidden({ timeout: 5000 })
}

async function getRule(client, id) {
  return getFrontendModeRule({ client, path: { rule_id: id } })
}

test.describe('Config — Frontend mode rules (admin webapp)', () => {
  test.describe.configure({ mode: 'serial' })

  test.beforeAll(async ({ authenticatedContext }) => {
    const page = await authenticatedContext.newPage()
    try {
      // Leftovers of an aborted run would shift the priorities and the rows.
      await purgeE2eFrontendModeRules(apiv4ClientForPage(page))
    } finally {
      await page.close()
    }
  })

  test.afterEach(async ({ apiv4Admin }, testInfo) => {
    await cleanupTrackedResources(apiv4Admin, testInfo)
  })

  test.afterAll(async ({ authenticatedContext }) => {
    const page = await authenticatedContext.newPage()
    try {
      const rules = await listFrontendModeRules(apiv4ClientForPage(page))
      const leftovers = rules.filter((rule) => rule.name.startsWith(E2E_FRONTEND_MODE_RULE_PREFIX))
      expect(leftovers.map((rule) => rule.name), 'no e2e rule may outlive the spec').toEqual([])
    } finally {
      await page.close()
    }
  })

  // ── SECTION A — Managing rules from Config → Frontend ─────────────────────

  test('A1: admin opens the page and sees the rules by priority', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const priority = await nextFrontendModeRulePriority(apiv4Admin)
    const low = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a1-low'),
      frontend_mode: 'hidden',
      priority,
      allowed: { users: [USER_A.id] },
    })
    const high = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a1-high'),
      frontend_mode: 'deprecated',
      priority: priority + 1,
      allowed: { users: [USER_A.id] },
    })

    await page.goto('/isard-admin/admin/hypervisors')
    const sidebarLink = page.locator(`a[href="${FRONTEND_MODE_URL}"]`)
    await page
      .locator('#sidebar-menu li', {
        has: page.locator(`> ul.child_menu > li > a[href="${FRONTEND_MODE_URL}"]`),
      })
      .locator('> a')
      .click()

    const listResp = page.waitForResponse(isRulesList, { timeout: 15000 })
    await sidebarLink.click()
    expect((await listResp).status()).toBeLessThan(400)
    await expect(page).toHaveURL(new RegExp(`${FRONTEND_MODE_URL}$`))

    await expect(page.locator(`${TABLE} thead th`)).toHaveText([
      'Name',
      'Description',
      'Frontend Mode',
      'Priority',
      'Action',
    ])

    await expect(ruleRow(page, low.id)).toBeVisible({ timeout: 10000 })
    await expect(ruleRow(page, high.id)).toBeVisible()
    const ids = await tableRowIds(page)
    expect(ids.indexOf(high.id)).toBeLessThan(ids.indexOf(low.id))

    for (const rule of [low, high]) {
      const row = ruleRow(page, rule.id)
      await expect(row.locator('td').nth(0)).toHaveText(rule.name)
      await expect(row.locator('td').nth(1)).toHaveText(rule.description)
      await expect(row.locator('td').nth(3)).toHaveText(String(rule.priority))
      await expect(row.locator('#btn-edit')).toBeVisible()
      await expect(row.locator('#btn-alloweds')).toBeVisible()
      await expect(row.locator('#btn-delete')).toBeVisible()

      const label = row.locator('td').nth(2).locator('span.label')
      await expect(label).toHaveText(rule.frontend_mode)
      await expect(label).toHaveAttribute('title', MODE_DESCRIPTIONS[rule.frontend_mode])
    }

    const warning = page.locator('#frontend-mode-warning')
    await expect(warning).toBeVisible()
    await expect(warning).toContainText('only the one with the highest priority applies')
    await expect(warning).toContainText('deletes their temporary desktops')
  })

  test('A2: admin creates a rule and sees it listed without reloading', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = ruleName('a2')
    const description = 'created by e2e'
    const priority = await nextFrontendModeRulePriority(apiv4Admin)

    await gotoFrontendMode(page)
    const modal = await openAddDialog(page)

    await expect(modal.locator('#name')).toHaveValue('')
    await expect(modal.locator('#description')).toHaveValue('')
    await expect(modal.locator('#frontend_mode')).toHaveValue('')
    await expect(modal.locator('#priority')).toHaveValue('')
    await expect(modal.locator('#allowed-title h4')).toContainText('Applies to')
    await expect(modal.locator('#alloweds_panel')).toBeVisible()
    await expectAllDimensionsUnchecked(modal)

    await fillRuleForm(modal, { name, description, mode: 'deprecated', priority })
    await toggleAllowed(modal, 'users')
    await expect(allowedCheckbox(modal, 'users')).toBeChecked()
    await pickAllowed(page, modal, 'users', USER_A)

    const reloadResp = page.waitForResponse(isRulesList, { timeout: 15000 })
    const createResp = await submitAndCreate(page, modal)
    const created = await findFrontendModeRuleByName(apiv4Admin, name)
    if (created) track(testInfo, 'frontend-mode-rule-id', created.id)

    expect(createResp.status()).toBe(204)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })
    await expect(
      page.locator('.ui-pnotify-text', { hasText: 'Rule added successfully' }),
    ).toBeVisible({ timeout: 8000 })
    expect((await reloadResp).status()).toBeLessThan(400)

    expect(created).not.toBeNull()
    expect(created.id).toBeTruthy()
    expect(created).toMatchObject({
      name,
      description,
      frontend_mode: 'deprecated',
      priority,
      allowed: { ...NO_ALLOWED, users: [USER_A.id] },
    })

    // The new rule outranks every other one, so it lands on the first row.
    const row = ruleRow(page, created.id)
    await expect(row).toBeVisible({ timeout: 10000 })
    await expect(row.locator('td').nth(0)).toHaveText(name)
    await expect(row.locator('td').nth(1)).toHaveText(description)
    await expect(row.locator('td').nth(2)).toHaveText('deprecated')
    await expect(row.locator('td').nth(3)).toHaveText(String(priority))
    expect((await tableRowIds(page))[0]).toBe(created.id)
    await expectNoPageReload(page)
  })

  test('A2b: a rule with only the required fields matches nobody', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = ruleName('a2b')
    const priority = await nextFrontendModeRulePriority(apiv4Admin)

    await gotoFrontendMode(page)
    const modal = await openAddDialog(page)
    await fillRuleForm(modal, { name, mode: 'hidden', priority })

    const createResp = await submitAndCreate(page, modal)
    const created = await findFrontendModeRuleByName(apiv4Admin, name)
    if (created) track(testInfo, 'frontend-mode-rule-id', created.id)

    expect(createResp.status()).toBe(204)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })
    expect(created).toMatchObject({
      name,
      description: '',
      frontend_mode: 'hidden',
      priority,
      allowed: NO_ALLOWED,
    })

    const row = ruleRow(page, created.id)
    await expect(row).toBeVisible({ timeout: 10000 })
    await expect(row.locator('td').nth(1)).toHaveText('')
    await expectNoPageReload(page)
  })

  test('A3: the frontend mode selector offers the four modes', async ({
    authenticatedPage: page,
  }) => {
    await gotoFrontendMode(page)
    const modal = await openAddDialog(page)

    await expect(modal.locator('#frontend_mode option')).toHaveText([
      'Choose...',
      ...Object.entries(MODE_DESCRIPTIONS).map(([mode, text]) => `${mode}: ${text}`),
    ])
    expect(
      await modal
        .locator('#frontend_mode option')
        .evaluateAll((options) => options.map((option) => option.value)),
    ).toEqual(['', 'deprecated', 'actual', 'all', 'hidden'])
  })

  test('A4: required fields block the creation', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    const name = ruleName('a4')
    await gotoFrontendMode(page)
    const rowsBefore = await tableRowIds(page)
    const creates = createRequests(page)
    const modal = await openAddDialog(page)

    await modal.locator('#send').click()
    for (const field of ['#name', '#frontend_mode', '#priority']) {
      await expect(modal.locator(field)).toHaveClass(/parsley-error/)
    }
    await expect(modal.locator('#description')).not.toHaveClass(/parsley-error/)

    await fillRuleForm(modal, { name, mode: 'hidden', priority: '1.5' })
    await modal.locator('#send').click()
    await expect(modal.locator('#name')).not.toHaveClass(/parsley-error/)
    await expect(modal.locator('#frontend_mode')).not.toHaveClass(/parsley-error/)
    await expect(modal.locator('#priority')).toHaveClass(/parsley-error/)
    await expect(modal.locator('.parsley-errors-list.filled')).toContainText(
      'The priority must be a whole number.',
    )

    await expect(modal).toBeVisible()
    expect(creates.count).toBe(0)
    expect(await tableRowIds(page)).toEqual(rowsBefore)
    expect(await findFrontendModeRuleByName(apiv4Admin, name)).toBeNull()
  })

  test('A5: a priority already listed is rejected in the form (CE-07)', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const existing = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a5-taken'),
      allowed: { users: [USER_A.id] },
    })
    const name = ruleName('a5')

    await gotoFrontendMode(page)
    await expect(ruleRow(page, existing.id)).toBeVisible({ timeout: 10000 })
    const creates = createRequests(page)
    const modal = await openAddDialog(page)

    await fillRuleForm(modal, { name, mode: 'hidden', priority: existing.priority })
    await modal.locator('#send').click()

    await expect(modal.locator('#priority')).toHaveClass(/parsley-error/)
    await expect(modal.locator('.parsley-errors-list.filled')).toHaveText(DUPLICATED_PRIORITY)
    await expect(modal).toBeVisible()
    expect(creates.count).toBe(0)
    expect(await findFrontendModeRuleByName(apiv4Admin, name)).toBeNull()

    await fillRuleForm(modal, { priority: existing.priority + 1 })
    const createResp = await submitAndCreate(page, modal)
    const created = await findFrontendModeRuleByName(apiv4Admin, name)
    if (created) track(testInfo, 'frontend-mode-rule-id', created.id)

    expect(createResp.status()).toBe(204)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })
    expect(created?.priority).toBe(existing.priority + 1)
    await expect(ruleRow(page, created.id)).toBeVisible({ timeout: 10000 })
  })

  test('A6: a priority taken after the table loaded is rejected by the server (CE-07)', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const name = ruleName('a6')
    await gotoFrontendMode(page)

    // Created behind the page's back: the loaded table does not list it,
    // so the form validator lets the priority through.
    const hidden = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a6-taken'),
      allowed: { users: [USER_A.id] },
    })
    await expect(ruleRow(page, hidden.id)).toHaveCount(0)

    const modal = await openAddDialog(page)
    await fillRuleForm(modal, { name, mode: 'hidden', priority: hidden.priority })
    const createResp = await submitAndCreate(page, modal)
    // Must not exist; tracked anyway so a regression does not leak it.
    const leaked = await findFrontendModeRuleByName(apiv4Admin, name)
    if (leaked) track(testInfo, 'frontend-mode-rule-id', leaked.id)

    expect(createResp.status()).toBe(409)
    expect((await createResp.json()).description_code).toBe('duplicated_priority')

    const errors = modal.locator('.parsley-errors-list.filled')
    await expect(errors).toHaveText(DUPLICATED_PRIORITY)
    await expect(modal).toBeVisible()
    await expect(page.locator('.ui-pnotify', { hasText: 'ERROR adding rule' })).toHaveCount(0)

    await modal.locator('#priority').pressSequentially('1')
    await expect(errors).toHaveCount(0)

    const rules = await listFrontendModeRules(apiv4Admin)
    expect(rules.filter((rule) => rule.priority === hidden.priority).map((rule) => rule.id)).toEqual(
      [hidden.id],
    )
    expect(rules.some((rule) => rule.name === name)).toBe(false)
  })

  test('A7: cancelling the dialog creates nothing and resets the form', async ({
    authenticatedPage: page,
    apiv4Admin,
  }) => {
    const name = ruleName('a7')
    const priority = await nextFrontendModeRulePriority(apiv4Admin)

    await gotoFrontendMode(page)
    const rowsBefore = await tableRowIds(page)
    const creates = createRequests(page)

    let modal = await openAddDialog(page)
    // Leave a validation message behind before filling the form.
    await modal.locator('#send').click()
    await expect(modal.locator('#name')).toHaveClass(/parsley-error/)
    await fillRuleForm(modal, { name, description: 'never saved', mode: 'actual', priority })
    await toggleAllowed(modal, 'users')
    await pickAllowed(page, modal, 'users', USER_A)

    await modal.locator('.modal-footer button', { hasText: 'Cancel' }).click()
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    expect(creates.count).toBe(0)
    expect(await tableRowIds(page)).toEqual(rowsBefore)
    expect(await findFrontendModeRuleByName(apiv4Admin, name)).toBeNull()

    modal = await openAddDialog(page)
    await expect(modal.locator('#name')).toHaveValue('')
    await expect(modal.locator('#description')).toHaveValue('')
    await expect(modal.locator('#frontend_mode')).toHaveValue('')
    await expect(modal.locator('#priority')).toHaveValue('')
    await expect(modal.locator('.parsley-error')).toHaveCount(0)
    await expect(modal.locator('.parsley-errors-list.filled')).toHaveCount(0)
    await expectAllDimensionsUnchecked(modal)
    await expect(allowedSelect(modal, 'users')).toHaveValues([])
  })

  test.describe('A8: HTML in the name is shown as text', () => {
    // 36 chars: the prefix keeps it purgeable and the name fits in 50.
    const HTML_NAME = `${E2E_FRONTEND_MODE_RULE_PREFIX}<img src=x onerror=alert(1)>`

    async function createHtmlRule(page, client, testInfo) {
      const dialogs = []
      page.on('dialog', async (dialog) => {
        dialogs.push(dialog.message())
        await dialog.dismiss()
      })
      const rule = await createFrontendModeRuleAndTrack(client, testInfo, {
        name: HTML_NAME,
        allowed: { users: [USER_A.id] },
      })
      await gotoFrontendMode(page)
      await expect(ruleRow(page, rule.id)).toBeVisible({ timeout: 10000 })
      return { rule, dialogs }
    }

    test('A8: the table and the delete confirmation show the name literally', async ({
      authenticatedPage: page,
      apiv4Admin,
    }, testInfo) => {
      const { rule, dialogs } = await createHtmlRule(page, apiv4Admin, testInfo)
      const row = ruleRow(page, rule.id)

      await expect(row.locator('td').nth(0)).toHaveText(HTML_NAME)

      await row.locator('#btn-delete').click()
      await expect(confirmNotice(page)).toContainText(`delete rule "${HTML_NAME}"`)
      await expect(page.locator('img[src="x"]')).toHaveCount(0)
      await answerConfirm(page, 'cancel')

      expect(dialogs).toEqual([])
    })

    test('A8b: the alloweds dialog title shows the name literally', async ({
      authenticatedPage: page,
      apiv4Admin,
    }, testInfo) => {
      // Known issue 1: modalAllowedsFormShow sets #alloweds_name with
      // .html(data.name), so the markup is injected into the dialog title.
      test.fail(true, 'the shared alloweds dialog renders the rule name as HTML')

      const { rule, dialogs } = await createHtmlRule(page, apiv4Admin, testInfo)
      const { modal } = await openAllowedsDialog(page, rule.id)

      await expect(modal.locator('#alloweds_name')).toHaveText(HTML_NAME, { timeout: 3000 })
      await expect(page.locator('img[src="x"]')).toHaveCount(0)
      expect(dialogs).toEqual([])
    })
  })

  test('A9: admin deletes a rule with confirmation', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const kept = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a9-kept'),
      allowed: { users: [USER_A.id] },
    })
    const doomed = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a9-doomed'),
      allowed: { users: [USER_A.id] },
    })

    await gotoFrontendMode(page)
    const row = ruleRow(page, doomed.id)
    await expect(row).toBeVisible({ timeout: 10000 })
    await row.locator('#btn-delete').click()

    await expect(confirmNotice(page)).toContainText(
      `Are you sure you want to delete rule "${doomed.name}"?`,
    )
    await expect(confirmNotice(page)).toContainText(
      'Its users will get the next rule that matches them or, if none does, the global frontend mode.',
    )

    const deleteResp = page.waitForResponse(
      (r) => pathOf(r.url()) === `${RULE_API}/${doomed.id}` && r.request().method() === 'DELETE',
      { timeout: 15000 },
    )
    const reloadResp = page.waitForResponse(isRulesList, { timeout: 15000 })
    await answerConfirm(page, 'ok')

    expect((await deleteResp).status()).toBe(204)
    await expect(
      page.locator('.ui-pnotify-text', {
        hasText: `Rule "${doomed.name}" deleted successfully`,
      }),
    ).toBeVisible({ timeout: 8000 })
    expect((await reloadResp).status()).toBeLessThan(400)

    await expect(row).toHaveCount(0)
    await expect(ruleRow(page, kept.id)).toBeVisible()
    await expectNoPageReload(page)

    expect((await getRule(apiv4Admin, doomed.id)).response.status).toBe(404)
    expect((await getRule(apiv4Admin, kept.id)).response.status).toBe(200)
  })

  test('A10: admin cancels a deletion', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const rule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a10'),
      allowed: { users: [USER_A.id] },
    })

    await gotoFrontendMode(page)
    const row = ruleRow(page, rule.id)
    await expect(row).toBeVisible({ timeout: 10000 })
    const deletes = countRequests(page, (req) => req.method() === 'DELETE')

    await row.locator('#btn-delete').click()
    await expect(confirmNotice(page)).toContainText(`delete rule "${rule.name}"`)
    await answerConfirm(page, 'cancel')

    await expect(row).toBeVisible()
    expect(deletes.count).toBe(0)
    expect((await getRule(apiv4Admin, rule.id)).response.status).toBe(200)
  })

  test('A11: admin edits a rule and the row shows the new values', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const priority = await nextFrontendModeRulePriority(apiv4Admin)
    const r1 = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a11-r1'),
      description: 'before the edit',
      frontend_mode: 'hidden',
      priority,
      allowed: { users: [USER_A.id] },
    })
    const r2 = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a11-r2'),
      priority: priority + 1,
      allowed: { users: [USER_B.id] },
    })
    const edited = { name: ruleName('a11-edited'), description: 'after the edit' }

    await gotoFrontendMode(page)
    const row = ruleRow(page, r1.id)
    await expect(row).toBeVisible({ timeout: 10000 })

    const { modal, prefill } = await openEditDialog(page, r1.id)
    expect(prefill.status()).toBeLessThan(400)
    await expect(modal.locator('.modal-title')).toContainText('Edit frontend mode rule')
    await expect(modal.locator('#send')).toHaveText('Save changes')
    await expect(modal.locator('#alloweds-frontend-mode-rule')).toBeHidden()
    await expect(modal.locator('#name')).toHaveValue(r1.name)
    await expect(modal.locator('#description')).toHaveValue(r1.description)
    await expect(modal.locator('#frontend_mode')).toHaveValue(r1.frontend_mode)
    await expect(modal.locator('#priority')).toHaveValue(String(r1.priority))

    await fillRuleForm(modal, { ...edited, mode: 'deprecated' })
    const reloadResp = page.waitForResponse(isRulesList, { timeout: 15000 })
    const updateResp = await submitAndUpdate(page, modal, r1.id)

    expect(updateResp.status()).toBe(204)
    // The dialog never sends the alloweds: they have their own dialog.
    expect(updateResp.request().postDataJSON()).toEqual({
      ...edited,
      frontend_mode: 'deprecated',
      priority: r1.priority,
    })
    await modal.waitFor({ state: 'hidden', timeout: 10000 })
    await expect(
      page.locator('.ui-pnotify-text', { hasText: 'Rule updated successfully' }),
    ).toBeVisible({ timeout: 8000 })
    expect((await reloadResp).status()).toBeLessThan(400)

    await expect(row.locator('td').nth(0)).toHaveText(edited.name)
    await expect(row.locator('td').nth(1)).toHaveText(edited.description)
    await expect(row.locator('td').nth(2)).toHaveText('deprecated')
    await expect(row.locator('td').nth(3)).toHaveText(String(r1.priority))
    await expectNoPageReload(page)

    expect((await getRule(apiv4Admin, r1.id)).data).toEqual({
      ...r1,
      ...edited,
      frontend_mode: 'deprecated',
    })
    expect((await getRule(apiv4Admin, r2.id)).data).toEqual(r2)
  })

  test('A11b: the dialog switches cleanly between edit and add', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const rule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a11b'),
      description: 'to be emptied',
      allowed: { users: [USER_A.id] },
    })

    await gotoFrontendMode(page)
    const row = ruleRow(page, rule.id)
    await expect(row).toBeVisible({ timeout: 10000 })
    const updates = updateRequests(page)

    let { modal } = await openEditDialog(page, rule.id)
    await fillRuleForm(modal, { name: ruleName('a11b-never-saved') })
    await cancelRuleDialog(modal)
    expect(updates.count).toBe(0)
    expect((await getRule(apiv4Admin, rule.id)).data).toEqual(rule)

    // Back in add mode nothing of the edit may be left behind.
    modal = await openAddDialog(page)
    await expect(modal.locator('.modal-title')).toContainText('Add frontend mode rule')
    await expect(modal.locator('#send')).toHaveText('Add rule')
    await expect(modal.locator('#name')).toHaveValue('')
    await expect(modal.locator('#description')).toHaveValue('')
    await expect(modal.locator('#frontend_mode')).toHaveValue('')
    await expect(modal.locator('#priority')).toHaveValue('')
    await expect(modal.locator('#alloweds-frontend-mode-rule')).toBeVisible()
    await expect(modal.locator('#alloweds_panel')).toBeVisible()
    await expectAllDimensionsUnchecked(modal)
    await cancelRuleDialog(modal)

    ;({ modal } = await openEditDialog(page, rule.id))
    await expect(modal.locator('#name')).toHaveValue(rule.name)
    await fillRuleForm(modal, { description: '' })
    const reloadResp = page.waitForResponse(isRulesList, { timeout: 15000 })
    const updateResp = await submitAndUpdate(page, modal, rule.id)

    expect(updateResp.status()).toBe(204)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })
    expect((await reloadResp).status()).toBeLessThan(400)
    await expect(row.locator('td').nth(1)).toHaveText('')
    await expectNoPageReload(page)
    expect((await getRule(apiv4Admin, rule.id)).data).toEqual({ ...rule, description: '' })
  })

  test('A11c: editing blocks invalid values', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const rule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a11c'),
      allowed: { users: [USER_A.id] },
    })

    await gotoFrontendMode(page)
    await expect(ruleRow(page, rule.id)).toBeVisible({ timeout: 10000 })
    const updates = updateRequests(page)
    const { modal } = await openEditDialog(page, rule.id)

    await fillRuleForm(modal, { name: '' })
    await modal.locator('#send').click()
    await expect(modal.locator('#name')).toHaveClass(/parsley-error/)
    await expect(modal).toBeVisible()

    await fillRuleForm(modal, { name: rule.name, priority: '1.5' })
    await modal.locator('#send').click()
    await expect(modal.locator('#name')).not.toHaveClass(/parsley-error/)
    await expect(modal.locator('#priority')).toHaveClass(/parsley-error/)
    await expect(modal.locator('.parsley-errors-list.filled')).toContainText(
      'The priority must be a whole number.',
    )

    await expect(modal).toBeVisible()
    expect(updates.count).toBe(0)
    expect((await getRule(apiv4Admin, rule.id)).data).toEqual(rule)
  })

  test('A11d: editing a rule deleted meanwhile reports it and refreshes the table', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const kept = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a11d-kept'),
      allowed: { users: [USER_A.id] },
    })
    const gone = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a11d-gone'),
      allowed: { users: [USER_A.id] },
    })

    await gotoFrontendMode(page)
    const row = ruleRow(page, gone.id)
    await expect(row).toBeVisible({ timeout: 10000 })

    // Deleted behind the page's back: the loaded table still lists it.
    const deleted = await deleteFrontendModeRule({ client: apiv4Admin, path: { rule_id: gone.id } })
    expect(deleted.response.status).toBe(204)

    const prefillResp = page.waitForResponse(isRuleRequest(gone.id, 'GET'), { timeout: 15000 })
    const reloadResp = page.waitForResponse(isRulesList, { timeout: 15000 })
    await row.locator('#btn-edit').click()

    expect((await prefillResp).status()).toBe(404)
    await expect(page.locator('.ui-pnotify', { hasText: 'ERROR loading rule' })).toBeVisible({
      timeout: 8000,
    })
    expect((await reloadResp).status()).toBeLessThan(400)
    await expect(page.locator(RULE_MODAL)).toBeHidden()
    await expect(row).toHaveCount(0)
    await expect(ruleRow(page, kept.id)).toBeVisible()
    await expectNoPageReload(page)
  })

  test('A12: editing a rule to a priority already listed is rejected in the form (CE-07)', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const priority = await nextFrontendModeRulePriority(apiv4Admin)
    const r1 = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a12-r1'),
      priority,
      allowed: { users: [USER_A.id] },
    })
    const r2 = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a12-r2'),
      priority: priority + 1,
      allowed: { users: [USER_A.id] },
    })

    await gotoFrontendMode(page)
    await expect(ruleRow(page, r1.id)).toBeVisible({ timeout: 10000 })
    await expect(ruleRow(page, r2.id)).toBeVisible()
    const updates = updateRequests(page)
    const { modal } = await openEditDialog(page, r1.id)

    await fillRuleForm(modal, { priority: r2.priority })
    await modal.locator('#send').click()
    await expect(modal.locator('#priority')).toHaveClass(/parsley-error/)
    await expect(modal.locator('.parsley-errors-list.filled')).toHaveText(DUPLICATED_PRIORITY)
    await expect(modal).toBeVisible()
    expect(updates.count).toBe(0)

    // Its own priority is not a duplicate.
    await fillRuleForm(modal, { priority: r1.priority })
    const updateResp = await submitAndUpdate(page, modal, r1.id)
    expect(updateResp.status()).toBe(204)
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    expect((await getRule(apiv4Admin, r1.id)).data.priority).toBe(r1.priority)
    expect((await getRule(apiv4Admin, r2.id)).data.priority).toBe(r2.priority)
  })

  test('A12b: a priority taken after the table loaded is rejected by the server on edit (CE-07)', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const r1 = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a12b-r1'),
      allowed: { users: [USER_A.id] },
    })

    await gotoFrontendMode(page)
    await expect(ruleRow(page, r1.id)).toBeVisible({ timeout: 10000 })

    // Created behind the page's back: the loaded table does not list it,
    // so the form validator lets the priority through.
    const hidden = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a12b-taken'),
      priority: r1.priority + 5,
      allowed: { users: [USER_A.id] },
    })
    await expect(ruleRow(page, hidden.id)).toHaveCount(0)

    const { modal } = await openEditDialog(page, r1.id)
    await fillRuleForm(modal, { priority: hidden.priority })
    const updateResp = await submitAndUpdate(page, modal, r1.id)

    expect(updateResp.status()).toBe(409)
    expect((await updateResp.json()).description_code).toBe('duplicated_priority')

    const errors = modal.locator('.parsley-errors-list.filled')
    await expect(errors).toHaveText(DUPLICATED_PRIORITY)
    await expect(modal).toBeVisible()
    await expect(page.locator('.ui-pnotify', { hasText: 'ERROR updating rule' })).toHaveCount(0)

    await modal.locator('#priority').pressSequentially('1')
    await expect(errors).toHaveCount(0)

    expect((await getRule(apiv4Admin, r1.id)).data.priority).toBe(r1.priority)
    expect((await getRule(apiv4Admin, hidden.id)).data.priority).toBe(hidden.priority)
  })

  test('A13: admin edits the alloweds of a rule', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const rule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a13'),
      frontend_mode: 'deprecated',
      allowed: { users: [USER_A.id] },
    })

    await gotoFrontendMode(page)
    await expect(ruleRow(page, rule.id)).toBeVisible({ timeout: 10000 })

    const { modal, prefill } = await openAllowedsDialog(page, rule.id)
    expect(prefill.status()).toBeLessThan(400)
    expect(prefill.request().postDataJSON()).toEqual({ id: rule.id })

    await expect(modal.locator('.modal-title')).toHaveText(`Edit "${rule.name}" permissions`)
    await expect(modal.locator('#allowed-title h4')).toContainText('Applies to')
    await expect(modal.locator('#allowed-warning')).toBeHidden()

    await expect(allowedCheckbox(modal, 'users')).toBeChecked()
    await expect(allowedSelect(modal, 'users')).toHaveValues([USER_A.id])
    await expect(
      modal.locator('#users_pannel .select2-selection__choice', { hasText: USER_A.name }),
    ).toBeVisible()
    for (const dimension of ['roles', 'categories', 'groups']) {
      await expect(allowedCheckbox(modal, dimension)).not.toBeChecked()
    }

    await toggleAllowed(modal, 'groups')
    await expect(allowedCheckbox(modal, 'groups')).toBeChecked()
    await pickAllowed(page, modal, 'groups', GROUP_B)

    const updateResp = await saveAlloweds(page, modal)
    expect(updateResp.status()).toBe(204)
    await expect(
      page.locator('.ui-pnotify-title', { hasText: 'Alloweds updated successfully' }),
    ).toBeVisible({ timeout: 8000 })

    const { data: stored } = await getRule(apiv4Admin, rule.id)
    expect(stored).toEqual({
      ...rule,
      allowed: { ...NO_ALLOWED, users: [USER_A.id], groups: [GROUP_B.id] },
    })

    // The row is still there and the dialog reads the stored alloweds back.
    await expectNoPageReload(page)
    const row = ruleRow(page, rule.id)
    await expect(row.locator('td').nth(0)).toHaveText(rule.name)
    await expect(row.locator('td').nth(2)).toHaveText(rule.frontend_mode)
    await expect(row.locator('td').nth(3)).toHaveText(String(rule.priority))
    const reopened = await openAllowedsDialog(page, rule.id)
    await expect(allowedCheckbox(reopened.modal, 'users')).toBeChecked()
    await expect(allowedSelect(reopened.modal, 'users')).toHaveValues([USER_A.id])
    await expect(allowedCheckbox(reopened.modal, 'groups')).toBeChecked()
    await expect(allowedSelect(reopened.modal, 'groups')).toHaveValues([GROUP_B.id])
    await expect(
      reopened.modal.locator('#groups_pannel .select2-selection__choice', {
        hasText: GROUP_B.name,
      }),
    ).toBeVisible()
  })

  test('A13b: unchecking a dimension stores it as false', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const rule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a13b'),
      allowed: { users: [USER_A.id], groups: [GROUP_B.id] },
    })

    await gotoFrontendMode(page)
    await expect(ruleRow(page, rule.id)).toBeVisible({ timeout: 10000 })

    const { modal } = await openAllowedsDialog(page, rule.id)
    await expect(allowedCheckbox(modal, 'groups')).toBeChecked()
    await expect(allowedSelect(modal, 'groups')).toHaveValues([GROUP_B.id])
    await expect(allowedCheckbox(modal, 'users')).toBeChecked()

    await toggleAllowed(modal, 'groups')
    await expect(allowedCheckbox(modal, 'groups')).not.toBeChecked()

    const updateResp = await saveAlloweds(page, modal)
    expect(updateResp.status()).toBe(204)
    expect(updateResp.request().postDataJSON().allowed).toEqual({
      ...NO_ALLOWED,
      users: [USER_A.id],
    })

    const { data: stored } = await getRule(apiv4Admin, rule.id)
    expect(stored.allowed).toEqual({ ...NO_ALLOWED, users: [USER_A.id] })

    const reopened = await openAllowedsDialog(page, rule.id)
    await expect(allowedCheckbox(reopened.modal, 'users')).toBeChecked()
    await expect(allowedSelect(reopened.modal, 'users')).toHaveValues([USER_A.id])
    await expect(allowedCheckbox(reopened.modal, 'groups')).not.toBeChecked()
    await expect(allowedSelect(reopened.modal, 'groups')).toHaveValues([])
  })

  test('A13c: closing the alloweds dialog without saving changes nothing', async ({
    authenticatedPage: page,
    apiv4Admin,
  }, testInfo) => {
    const rule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a13c'),
      allowed: { users: [USER_A.id] },
    })
    const other = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
      name: ruleName('a13c-other'),
      allowed: { users: [USER_B.id] },
    })

    await gotoFrontendMode(page)
    await expect(ruleRow(page, rule.id)).toBeVisible({ timeout: 10000 })
    const updates = countRequests(
      page,
      (req) => pathOf(req.url()) === ALLOWED_UPDATE_API && req.method() === 'POST',
    )

    const { modal } = await openAllowedsDialog(page, rule.id)
    await expect(allowedCheckbox(modal, 'users')).toBeChecked()
    await toggleAllowed(modal, 'groups')
    await pickAllowed(page, modal, 'groups', GROUP_B)

    await modal.locator('.modal-footer button', { hasText: 'Cancel' }).click()
    await modal.waitFor({ state: 'hidden', timeout: 10000 })

    expect(updates.count).toBe(0)
    const { data: stored } = await getRule(apiv4Admin, rule.id)
    expect(stored.allowed).toEqual({ ...NO_ALLOWED, users: [USER_A.id] })

    const otherDialog = await openAllowedsDialog(page, other.id)
    await expect(otherDialog.modal.locator('.modal-title')).toHaveText(
      `Edit "${other.name}" permissions`,
    )
    await expect(allowedCheckbox(otherDialog.modal, 'users')).toBeChecked()
    await expect(allowedSelect(otherDialog.modal, 'users')).toHaveValues([USER_B.id])
    await expect(allowedCheckbox(otherDialog.modal, 'groups')).not.toBeChecked()
    await expect(allowedSelect(otherDialog.modal, 'groups')).toHaveValues([])
  })

  test('A14: non-admins cannot open the page', async ({ managerE2EPage: page }) => {
    const lists = countRequests(page, (req) => pathOf(req.url()) === RULES_API)

    await page.goto('/isard-admin/admin/domains/render/Desktops')
    await expect(page.locator('#sidebar-menu')).toBeVisible({ timeout: 15000 })
    await expect(page.locator(`a[href="${FRONTEND_MODE_URL}"]`)).toHaveCount(0)

    try {
      await page.goto(FRONTEND_MODE_URL)
      await page.waitForLoadState('domcontentloaded')
      await expect(page.locator(TABLE)).toHaveCount(0)
      await expect(page.locator('.btn-add-frontend-mode-rule')).toHaveCount(0)
      expect(lists.count).toBe(0)
    } finally {
      // @isAdmin logs the Flask session out when it rejects a non-admin, and
      // that session is shared by every manager test of this worker.
      await bridgeAdminSession(page)
    }
  })
})
