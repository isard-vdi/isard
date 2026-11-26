// E2E tests for the frontend mode rules.
// Spec: testing/e2e/specs/webapp/frontend_mode_rules.md
//   - Section A: managing the rules from Config → Frontend
//     (/isard-admin/admin/frontend_mode).
//   - Section B: the priority uniqueness and the not-found answers of the API.
//   - Section C: the frontend each user gets once a rule applies to them.
//
// Conventions:
//   - The rules are global configuration: the tests run one at a time, in
//     order, and every rule targets the dedicated `fmre2e` seed accounts,
//     which no other spec logs in with, so no parallel spec ever changes
//     frontend. The only rules reaching further (roles:[admin] /
//     roles:[advanced] in C3 and C5) carry the installation mode, so they
//     change nothing for the users outside `fmre2e`.
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
//   - Section C logs the target users in on fresh contexts. Every login ends
//     the user's previous session, so a test first waits for the expected
//     mode through an API-only login and only then logs in with the browser,
//     whose client it keeps using.

import {
  test as base,
  expect,
  apiv4ClientForPage,
  apiv4ClientForRequest,
  track,
  cleanupTrackedResources,
  E2E_FRONTEND_MODE_RULE_PREFIX,
  listFrontendModeRules,
  findFrontendModeRuleByName,
  nextFrontendModeRulePriority,
  createFrontendModeRuleAndTrack,
  purgeE2eFrontendModeRules,
  updateFrontendModeRule,
  waitForFrontendMode,
  getTemporaryDesktopTemplate,
  listTemporaryDesktops,
  createTemporaryDesktopAndTrack,
  waitForTemporaryDesktops,
  waitForTemporaryDesktopsSettled,
  deleteTemporaryDesktops,
} from '../../fixtures/apiv4/index.js'
import { bridgeAdminSession } from '../../fixtures/common.js'
import {
  createFrontendModeRule,
  deleteFrontendModeRule,
  getFrontendModeRule,
  getUserConfig,
  updateFrontendModeRule as sdkUpdateFrontendModeRule,
} from '../../src/gen/apiv4/sdk.gen'

// `targets` logs the fmre2e accounts in, through the API or the browser,
// and closes every context it opened once the test ends.
const test = base.extend({
  targets: async ({ browser, playwright, baseURL, users, categories, loginHelpers }, use) => {
    const opened = []
    await use({
      async api(key) {
        const request = await loginHelpers.apiLogin(playwright, baseURL, users[key], categories)
        opened.push(() => request.dispose())
        return apiv4ClientForRequest(request)
      },
      async browser(key) {
        const context = await browser.newContext({ ignoreHTTPSErrors: true })
        opened.push(() => context.close())
        const page = await context.newPage()
        await loginHelpers.login(page, users[key], categories)
        return { page, client: apiv4ClientForPage(page) }
      },
    })
    for (const close of opened.reverse()) await close().catch(() => {})
  },
})

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
const ADVANCED = { id: 'fmre2e-advanced', name: 'FMR E2E Advanced' }
const MANAGER = { id: 'fmre2e-manager', name: 'FMR E2E Manager' }
const GROUP_A = { id: 'fmre2e-group-a', name: 'FMR E2E Group A' }
const GROUP_B = { id: 'fmre2e-group-b', name: 'FMR E2E Group B' }
const CATEGORY = 'fmre2e'

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
  // The first row can still be the DataTables loading placeholder, which
  // has no id: the rows are only there once its spinner is gone.
  await expect(page.locator(`${TABLE} tbody .fa-spinner`)).toHaveCount(0, { timeout: 15000 })
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
  test.describe.configure({ mode: 'default' })

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

  // ── SECTION B — API contract through the SDK ──────────────────────────────

  test.describe('Section B — API contract', () => {
    test('B1: priorities are unique on create and on edit (CE-07)', async ({
      apiv4Admin,
    }, testInfo) => {
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      const r1 = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('b1-r1'),
        priority,
        allowed: { users: [USER_A.id] },
      })
      const r2 = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('b1-r2'),
        priority: priority + 1,
        allowed: { users: [USER_A.id] },
      })

      const name = ruleName('b1-dup')
      const created = await createFrontendModeRule({
        client: apiv4Admin,
        body: {
          name,
          frontend_mode: 'hidden',
          priority,
          allowed: { ...NO_ALLOWED, users: [USER_A.id] },
        },
      })
      const leaked = await findFrontendModeRuleByName(apiv4Admin, name)
      if (leaked) track(testInfo, 'frontend-mode-rule-id', leaked.id)
      expect(created.response.status).toBe(409)
      expect(created.error?.description_code).toBe('duplicated_priority')
      expect(leaked).toBeNull()

      const moved = await sdkUpdateFrontendModeRule({
        client: apiv4Admin,
        path: { rule_id: r2.id },
        body: { priority },
      })
      expect(moved.response.status).toBe(409)
      expect(moved.error?.description_code).toBe('duplicated_priority')
      expect((await getRule(apiv4Admin, r2.id)).data.priority).toBe(r2.priority)

      const kept = await sdkUpdateFrontendModeRule({
        client: apiv4Admin,
        path: { rule_id: r1.id },
        body: { priority: r1.priority },
      })
      expect(kept.response.status).toBe(204)
      expect((await getRule(apiv4Admin, r1.id)).data).toEqual(r1)
    })

    test('B2: unknown rule ids answer 404', async ({ apiv4Admin }) => {
      const id = crypto.randomUUID()
      expect((await getRule(apiv4Admin, id)).response.status).toBe(404)
      const updated = await sdkUpdateFrontendModeRule({
        client: apiv4Admin,
        path: { rule_id: id },
        body: { description: 'never stored' },
      })
      expect(updated.response.status).toBe(404)
      const deleted = await deleteFrontendModeRule({ client: apiv4Admin, path: { rule_id: id } })
      expect(deleted.response.status).toBe(404)
    })
  })

  // ── SECTION C — Effect of the rule on the user ────────────────────────────

  test.describe('Section C — the frontend each user gets', () => {
    // A rule change can take the whole 60 s of the get-config cache to reach
    // the user (USER_CONFIG_CACHE_TTL, 1 on the e2e stack), and a scenario
    // waits for up to three changes in a row.
    test.describe.configure({ timeout: 300_000 })

    // The mode of a user no rule matches. Read from an fmre2e user before
    // any scenario creates a rule: nothing else reaches that category, while
    // a rule left on the stack by hand may well reach the control user.
    let installationMode
    // What the control user gets, which no scenario may change.
    let controlMode

    test.beforeAll(async ({ userE2EContext, playwright, baseURL, users, categories, loginHelpers }) => {
      const request = await loginHelpers.apiLogin(
        playwright,
        baseURL,
        users.fmre2e_user_b,
        categories,
      )
      try {
        const { data } = await getUserConfig({ client: apiv4ClientForRequest(request) })
        installationMode = data?.frontend_mode
        expect(Object.keys(MODE_DESCRIPTIONS)).toContain(installationMode)
      } finally {
        await request.dispose()
      }

      const page = await userE2EContext.newPage()
      try {
        const { data } = await getUserConfig({ client: apiv4ClientForPage(page) })
        controlMode = data?.frontend_mode
      } finally {
        await page.close()
      }
    })

    // A mode that differs from the installation one and lands on the other
    // frontend after the login, so it can only come from a rule.
    const contrastMode = () => (installationMode === 'actual' ? 'deprecated' : 'actual')

    // When the mode under test is the installation mode, a user no rule
    // matches would get it too. A lower-priority rule on the whole fmre2e
    // category then gives them another one, so the mode can only come from
    // the rule under test. Returns the mode the users get without it.
    // `fallback` is for the scenarios that go through two modes and need a
    // guard that is neither.
    async function guardInstallationMode(
      client,
      testInfo,
      mode,
      priority,
      fallback = mode === 'hidden' ? 'all' : 'hidden',
    ) {
      if (installationMode !== mode) return installationMode
      await createFrontendModeRuleAndTrack(client, testInfo, {
        name: ruleName(`fallback-${fallback}`),
        frontend_mode: fallback,
        priority,
        allowed: { categories: [CATEGORY] },
      })
      return fallback
    }

    // Waits for `mode` through an API-only login, then logs the user in with
    // the browser: the landing is then decided by the rule, not by the cache.
    async function loginWithMode(targets, key, mode) {
      await waitForFrontendMode(await targets.api(key), mode)
      return targets.browser(key)
    }

    async function apiWithMode(targets, key, mode) {
      const client = await targets.api(key)
      await waitForFrontendMode(client, mode)
      return client
    }

    const urlFor = (path) =>
      new RegExp(`^https?://[^/]+${path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/?$`)

    // The old frontend renders its layout only once its router guard, which
    // applies the mode, let the route through.
    async function expectOldFrontend(page, path) {
      await expect(page).toHaveURL(urlFor(path), { timeout: 30000 })
      await expect(page.locator('#main-layout')).toBeVisible({ timeout: 30000 })
      await expect(page).toHaveURL(urlFor(path))
    }

    async function expectNewFrontend(page, path) {
      await expect(page).toHaveURL(urlFor(path), { timeout: 30000 })
      await expect(page.locator('[data-sidebar="sidebar"]').first()).toBeVisible({
        timeout: 30000,
      })
      await expect(page).toHaveURL(urlFor(path))
    }

    // Where the login sends a user without a stored preference.
    async function expectLanding(page, mode) {
      if (mode === 'actual') await expectNewFrontend(page, '/frontend/desktops')
      else await expectOldFrontend(page, '/desktops')
    }

    const oldToggler = (page) => page.locator('.frontend-toggler')
    const newToggler = (page) =>
      page.getByRole('button', { name: /^(Switch to legacy interface|No legacy equivalent)$/ })

    // Absence checks wait for the config queries of the page to finish.
    async function expectNoToggler(page) {
      await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})
      await expect(oldToggler(page)).toHaveCount(0)
      await expect(newToggler(page)).toHaveCount(0)
    }

    const preferredFrontend = (page) =>
      page.evaluate(() => window.localStorage.getItem('preferredFrontend'))

    async function deleteRule(client, id) {
      const { response } = await deleteFrontendModeRule({ client, path: { rule_id: id } })
      expect(response.status).toBe(204)
    }

    // ── Who a rule reaches ──────────────────────────────────────────────────

    test('C1: a category rule reaches its users and nobody else (CE-01)', async ({
      apiv4Admin,
      apiv4User,
      targets,
    }, testInfo) => {
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await guardInstallationMode(apiv4Admin, testInfo, 'all', priority)
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c1'),
        frontend_mode: 'all',
        priority: priority + 1,
        allowed: { categories: [CATEGORY] },
      })

      await apiWithMode(targets, 'fmre2e_user_b', 'all')
      const { page } = await loginWithMode(targets, 'fmre2e_user_a', 'all')
      await expectLanding(page, 'all')
      await expect(oldToggler(page)).toBeVisible({ timeout: 15000 })

      expect((await getUserConfig({ client: apiv4User })).data.frontend_mode).toBe(
        controlMode,
      )
    })

    test('C2: a group rule reaches only the members of the group', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      const mode = contrastMode()
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c2'),
        frontend_mode: mode,
        allowed: { groups: [GROUP_A.id] },
      })

      await apiWithMode(targets, 'fmre2e_advanced', mode)
      await apiWithMode(targets, 'fmre2e_user_b', installationMode)
      const { page } = await loginWithMode(targets, 'fmre2e_user_a', mode)
      await expectLanding(page, mode)
    })

    test('C3: a role rule reaches the users of the role', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      // roles:[advanced] reaches every advanced user of the stack, so it
      // carries the installation mode: it changes nothing for them. The
      // lower rule gives fmre2e-advanced another mode, which it only gets
      // while the role rule does not apply.
      const mode = contrastMode()
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c3-user'),
        frontend_mode: mode,
        priority,
        allowed: { users: [ADVANCED.id] },
      })
      const roleRule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c3-role'),
        frontend_mode: installationMode,
        priority: priority + 1,
        allowed: { roles: ['advanced'] },
      })

      const { page, client } = await loginWithMode(targets, 'fmre2e_advanced', installationMode)
      await expectLanding(page, installationMode)

      await deleteRule(apiv4Admin, roleRule.id)
      await waitForFrontendMode(client, mode)
      await page.goto('/')
      await expectLanding(page, mode)
    })

    test('C4: a user rule reaches only that user', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      const mode = contrastMode()
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c4'),
        frontend_mode: mode,
        allowed: { users: [USER_A.id] },
      })

      await apiWithMode(targets, 'fmre2e_user_b', installationMode)
      const { page } = await loginWithMode(targets, 'fmre2e_user_a', mode)
      await expectLanding(page, mode)
    })

    test('C5: matching one dimension is enough (CE-09)', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      // categories:[fmre2e] + roles:[admin]: fmre2e-user-a is no admin. The
      // rule carries the installation mode, so the admins of the stack it
      // also reaches see no change; the lower rule shows when it stops
      // applying.
      const mode = contrastMode()
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c5-user'),
        frontend_mode: mode,
        priority,
        allowed: { users: [USER_A.id] },
      })
      const anyRule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c5-any'),
        frontend_mode: installationMode,
        priority: priority + 1,
        allowed: { categories: [CATEGORY], roles: ['admin'] },
      })

      const { page, client } = await loginWithMode(targets, 'fmre2e_user_a', installationMode)
      await expectLanding(page, installationMode)

      await deleteRule(apiv4Admin, anyRule.id)
      await waitForFrontendMode(client, mode)
      await page.goto('/')
      await expectLanding(page, mode)
    })

    test('C6: the highest priority wins (CE-08)', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await guardInstallationMode(apiv4Admin, testInfo, 'all', priority)
      const categoryRule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c6-category'),
        frontend_mode: 'all',
        priority: priority + 1,
        allowed: { categories: [CATEGORY] },
      })
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c6-user'),
        frontend_mode: 'actual',
        priority: priority + 11,
        allowed: { users: [USER_A.id] },
      })

      await apiWithMode(targets, 'fmre2e_user_b', 'all')
      const { page, client } = await loginWithMode(targets, 'fmre2e_user_a', 'actual')
      await expectLanding(page, 'actual')

      // The category rule now outranks the user rule.
      await updateFrontendModeRule(apiv4Admin, categoryRule.id, { priority: priority + 21 })
      await waitForFrontendMode(client, 'all')
      await page.goto('/')
      await expectLanding(page, 'all')
      await expect(oldToggler(page)).toBeVisible({ timeout: 15000 })
    })

    test('C7: a user no rule matches gets the installation mode', async ({
      apiv4Admin,
      apiv4User,
      targets,
    }, testInfo) => {
      const mode = contrastMode()
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c7'),
        frontend_mode: mode,
        allowed: { users: [USER_B.id] },
      })

      await apiWithMode(targets, 'fmre2e_user_b', mode)
      const { page } = await loginWithMode(targets, 'fmre2e_user_a', installationMode)
      await expectLanding(page, installationMode)
      if (installationMode === 'all') await expect(oldToggler(page)).toBeVisible()
      else await expectNoToggler(page)

      expect((await getUserConfig({ client: apiv4User })).data.frontend_mode).toBe(
        controlMode,
      )
    })

    // ── One scenario per mode ───────────────────────────────────────────────

    test('C8: `deprecated` sends the user to the old frontend (CE-11)', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await guardInstallationMode(apiv4Admin, testInfo, 'deprecated', priority)
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c8'),
        frontend_mode: 'deprecated',
        priority: priority + 1,
        allowed: { users: [USER_A.id] },
      })

      const { page } = await loginWithMode(targets, 'fmre2e_user_a', 'deprecated')
      await expectLanding(page, 'deprecated')
      await expectNoToggler(page)

      await page.goto('/frontend/desktops')
      await expectOldFrontend(page, '/desktops')
      await expectNoToggler(page)

      await page.goto('/frontend/profile')
      await expectOldFrontend(page, '/profile')
    })

    test('C9: `actual` sends the user to the new frontend', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await guardInstallationMode(apiv4Admin, testInfo, 'actual', priority)
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c9'),
        frontend_mode: 'actual',
        priority: priority + 1,
        allowed: { users: [USER_A.id] },
      })

      const { page } = await loginWithMode(targets, 'fmre2e_user_a', 'actual')
      await expectLanding(page, 'actual')
      await expectNoToggler(page)
      expect(await preferredFrontend(page)).toBeNull()

      await page.goto('/desktops')
      await expectNewFrontend(page, '/frontend/desktops')

      await page.goto('/profile')
      await expectNewFrontend(page, '/frontend/profile')
      await expectNoToggler(page)
      expect(await preferredFrontend(page)).toBeNull()
    })

    test('C10: an `actual` user reaches their bookings in the old frontend (CE-03)', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await guardInstallationMode(apiv4Admin, testInfo, 'actual', priority)
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c10'),
        frontend_mode: 'actual',
        priority: priority + 1,
        allowed: { users: [USER_A.id] },
      })

      const { page } = await loginWithMode(targets, 'fmre2e_user_a', 'actual')
      await expectLanding(page, 'actual')

      const bookings = page.waitForResponse(
        (r) => pathOf(r.url()) === '/api/v4/items/bookings' && r.request().method() === 'GET',
        { timeout: 30000 },
      )
      await page.locator('[data-sidebar="sidebar"] a[href="/booking/summary"]').first().click()
      await expectOldFrontend(page, '/booking/summary')
      expect((await bookings).status()).toBe(200)
      await expect(page.locator('#main-layout .calendar-container')).toBeVisible()
      await expectNoToggler(page)
      await expect(page).toHaveURL(urlFor('/booking/summary'))

      await page.goto('/booking/summary')
      await expectOldFrontend(page, '/booking/summary')

      await page.goto('/desktops')
      await expectNewFrontend(page, '/frontend/desktops')
    })

    test('C11: an `actual` manager reaches the planning in the old frontend', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await guardInstallationMode(apiv4Admin, testInfo, 'actual', priority)
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c11'),
        frontend_mode: 'actual',
        priority: priority + 1,
        allowed: { users: [MANAGER.id] },
      })

      const { page } = await loginWithMode(targets, 'fmre2e_manager', 'actual')
      await expectLanding(page, 'actual')

      await page.goto('/planning')
      await expectOldFrontend(page, '/planning')
      await expect(page.locator('#main-layout .reservableItemTitle')).toBeVisible()
      await expectNoToggler(page)
      await expect(page).toHaveURL(urlFor('/planning'))

      await page.goto('/desktops')
      await expectNewFrontend(page, '/frontend/desktops')
    })

    test('C12: `hidden` allows both frontends without the switch (CE-12)', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await guardInstallationMode(apiv4Admin, testInfo, 'hidden', priority)
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c12'),
        frontend_mode: 'hidden',
        priority: priority + 1,
        allowed: { users: [USER_A.id] },
      })

      const { page } = await loginWithMode(targets, 'fmre2e_user_a', 'hidden')
      await expectLanding(page, 'hidden')
      await expectNoToggler(page)

      await page.goto('/frontend/desktops')
      await expectNewFrontend(page, '/frontend/desktops')
      await expectNoToggler(page)

      await page.goto('/desktops')
      await expectOldFrontend(page, '/desktops')
      await expectNoToggler(page)
    })

    test('C13: `all` shows the switch and it changes frontend (CE-01)', async ({
      apiv4Admin,
      targets,
    }, testInfo) => {
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await guardInstallationMode(apiv4Admin, testInfo, 'all', priority)
      await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c13'),
        frontend_mode: 'all',
        priority: priority + 1,
        allowed: { users: [USER_A.id] },
      })

      const { page } = await loginWithMode(targets, 'fmre2e_user_a', 'all')
      await expectLanding(page, 'all')

      await expect(oldToggler(page)).toHaveText('Switch to new interface', { timeout: 15000 })
      await oldToggler(page).click()
      await expectNewFrontend(page, '/frontend/desktops')
      expect(await preferredFrontend(page)).toBe('vue3')

      const toLegacy = page.getByRole('button', { name: 'Switch to legacy interface' })
      await expect(toLegacy).toBeVisible({ timeout: 15000 })
      await toLegacy.click()
      await expectOldFrontend(page, '/desktops')
      expect(await preferredFrontend(page)).toBe('vue2')

      // Not on the edit forms of either frontend.
      await page.goto('/frontend/desktops/new')
      await expectNewFrontend(page, '/frontend/desktops/new')
      await expectNoToggler(page)
      await page.goto('/desktops/new')
      await expectOldFrontend(page, '/desktops/new')
      await expectNoToggler(page)
    })

    test('C14: changing the mode of a rule changes what its users get', async ({
      authenticatedPage: adminPage,
      apiv4Admin,
      targets,
    }, testInfo) => {
      // The rule goes from `hidden` to `deprecated`: the guard must be
      // neither, and at most one of the two calls creates it.
      const priority = await nextFrontendModeRulePriority(apiv4Admin)
      await guardInstallationMode(apiv4Admin, testInfo, 'hidden', priority, 'all')
      await guardInstallationMode(apiv4Admin, testInfo, 'deprecated', priority, 'all')
      const rule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c14'),
        frontend_mode: 'hidden',
        priority: priority + 1,
        allowed: { users: [USER_A.id] },
      })

      const { page, client } = await loginWithMode(targets, 'fmre2e_user_a', 'hidden')
      await page.goto('/frontend/desktops')
      await expectNewFrontend(page, '/frontend/desktops')

      await gotoFrontendMode(adminPage)
      const { modal } = await openEditDialog(adminPage, rule.id)
      await fillRuleForm(modal, { mode: 'deprecated' })
      expect((await submitAndUpdate(adminPage, modal, rule.id)).status()).toBe(204)
      await modal.waitFor({ state: 'hidden', timeout: 10000 })

      await waitForFrontendMode(client, 'deprecated')
      await page.reload()
      await expectOldFrontend(page, '/desktops')
    })

    test('C15: editing the alloweds from the dialog changes who the rule reaches', async ({
      authenticatedPage: adminPage,
      apiv4Admin,
      targets,
    }, testInfo) => {
      const mode = contrastMode()
      const rule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
        name: ruleName('c15'),
        frontend_mode: mode,
        allowed: { users: [USER_B.id] },
      })

      const userA = await apiWithMode(targets, 'fmre2e_user_a', installationMode)
      const userB = await apiWithMode(targets, 'fmre2e_user_b', mode)

      await gotoFrontendMode(adminPage)
      let { modal } = await openAllowedsDialog(adminPage, rule.id)
      await toggleAllowed(modal, 'groups')
      await pickAllowed(adminPage, modal, 'groups', GROUP_A)
      expect((await saveAlloweds(adminPage, modal)).status()).toBe(204)

      await waitForFrontendMode(userA, mode)
      await waitForFrontendMode(userB, mode)

      ;({ modal } = await openAllowedsDialog(adminPage, rule.id))
      await expect(allowedCheckbox(modal, 'groups')).toBeChecked()
      await toggleAllowed(modal, 'groups')
      expect((await saveAlloweds(adminPage, modal)).status()).toBe(204)

      await waitForFrontendMode(userA, installationMode)
      await waitForFrontendMode(userB, mode)
    })

    // ── Temporary desktops ──────────────────────────────────────────────────

    test.describe('temporary desktops', () => {
      // On top of the cache, the desktops have to start; C18 creates four.
      test.describe.configure({ timeout: 420_000 })

      // Leftovers of an aborted run would break the counts.
      async function templateWithoutDesktops(client) {
        const template = await getTemporaryDesktopTemplate(client)
        await deleteTemporaryDesktops(client, template.id)
        return template
      }

      async function createTemporary(client, testInfo, templateId) {
        const result = await createTemporaryDesktopAndTrack(client, testInfo, templateId)
        expect(result.response.status, JSON.stringify(result.error ?? null)).toBeLessThan(400)
        return result.data.id
      }

      test('C16: an `actual` user can hold several temporary desktops (CE-13)', async ({
        apiv4Admin,
        targets,
      }, testInfo) => {
        const priority = await nextFrontendModeRulePriority(apiv4Admin)
        await guardInstallationMode(apiv4Admin, testInfo, 'actual', priority)
        await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
          name: ruleName('c16'),
          frontend_mode: 'actual',
          priority: priority + 1,
          allowed: { users: [USER_A.id] },
        })
        const client = await apiWithMode(targets, 'fmre2e_user_a', 'actual')
        expect((await getUserConfig({ client })).data.multiple_temporal_desktops).toBe(true)
        const template = await templateWithoutDesktops(client)

        const first = await createTemporary(client, testInfo, template.id)
        const second = await createTemporary(client, testInfo, template.id)
        expect(second).not.toBe(first)

        const desktops = await waitForTemporaryDesktops(
          client,
          template.id,
          (list) => list.length === 2,
        )
        expect(desktops.map((d) => d.id).sort()).toEqual([first, second].sort())
      })

      test('C17: choosing the new frontend under `all` does not give the `actual` behaviour (CE-05)', async ({
        apiv4Admin,
        targets,
      }, testInfo) => {
        const priority = await nextFrontendModeRulePriority(apiv4Admin)
        await guardInstallationMode(apiv4Admin, testInfo, 'all', priority)
        await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
          name: ruleName('c17'),
          frontend_mode: 'all',
          priority: priority + 1,
          allowed: { users: [USER_A.id] },
        })

        const { page, client } = await loginWithMode(targets, 'fmre2e_user_a', 'all')
        await expectLanding(page, 'all')
        await expect(oldToggler(page)).toBeVisible({ timeout: 15000 })
        await oldToggler(page).click()
        await expectNewFrontend(page, '/frontend/desktops')
        expect(await preferredFrontend(page)).toBe('vue3')
        expect((await getUserConfig({ client })).data.multiple_temporal_desktops).toBe(false)

        // Sent with the session that just switched: the server decides by
        // the mode, it does not know which frontend is asking.
        const template = await templateWithoutDesktops(client)
        const first = await createTemporary(client, testInfo, template.id)
        // A desktop still being created answers 428 instead of being reused.
        await waitForTemporaryDesktopsSettled(client, template.id)
        const second = await createTemporary(client, testInfo, template.id)
        expect(second).toBe(first)

        const desktops = await listTemporaryDesktops(client, template.id)
        expect(desktops.map((d) => d.id)).toEqual([first])
      })

      test('C18: leaving `actual` collapses the temporary desktops of a template (CE-04)', async ({
        apiv4Admin,
        targets,
      }, testInfo) => {
        const priority = await nextFrontendModeRulePriority(apiv4Admin)
        const baseline = await guardInstallationMode(apiv4Admin, testInfo, 'actual', priority)
        const rule = await createFrontendModeRuleAndTrack(apiv4Admin, testInfo, {
          name: ruleName('c18'),
          frontend_mode: 'actual',
          priority: priority + 1,
          allowed: { users: [USER_A.id] },
        })
        const client = await apiWithMode(targets, 'fmre2e_user_a', 'actual')
        const template = await templateWithoutDesktops(client)

        const previous = []
        for (let i = 0; i < 3; i += 1) {
          previous.push(await createTemporary(client, testInfo, template.id))
        }
        expect(new Set(previous).size).toBe(3)
        await waitForTemporaryDesktops(client, template.id, (list) => list.length === 3)
        await waitForTemporaryDesktopsSettled(client, template.id)

        await deleteRule(apiv4Admin, rule.id)
        await waitForFrontendMode(client, baseline)

        const current = await createTemporary(client, testInfo, template.id)
        expect(previous).not.toContain(current)
        const desktops = await waitForTemporaryDesktops(
          client,
          template.id,
          (list) => list.length === 1,
          { message: 'only the new temporary desktop left' },
        )
        expect(desktops.map((d) => d.id)).toEqual([current])
      })
    })
  })
})
