// Frontend-mode-rule helpers: create+track factories, alloweds accessors
// and the leftover purge. The rules are global configuration, so every
// write goes through the `[]` guard below.

import {
  adminAllowedUpdate,
  allowedTable,
  createFrontendModeRule,
  deleteFrontendModeRule,
  getAllFrontendModeRules,
  getUserConfig,
  updateFrontendModeRule as sdkUpdateFrontendModeRule,
} from '../../src/gen/apiv4/sdk.gen'
import { unwrap } from './unwrap.js'
import { registerResource, track } from './resources.js'

// Every rule a spec creates carries this prefix so leftovers of an aborted
// run can be told apart from the rules of the stack.
export const E2E_FRONTEND_MODE_RULE_PREFIX = 'e2e-fmr-'

// Test rules start here so they outrank any rule already in the stack.
const E2E_PRIORITY_FLOOR = 1_000_000

const ALLOWED_TABLE = 'frontend_mode_rules'
const NO_ALLOWED = { users: false, groups: false, categories: false, roles: false }

// Ordered before desktops: section C temporary desktops depend on the mode
// the rule gives their owner.
registerResource('frontend-mode-rule-id', {
  order: 5,
  delete: (client, id) => deleteFrontendModeRule({ client, path: { rule_id: id } }),
})

// An empty list matches every user of the stack, which would change the
// frontend of every spec running in parallel.
function assertAllowedIsScoped(allowed) {
  for (const [dimension, value] of Object.entries(allowed ?? {})) {
    if (Array.isArray(value) && value.length === 0) {
      throw new Error(
        `frontend mode rule: allowed.${dimension} is [], which applies the rule to every user`,
      )
    }
  }
}

export async function listFrontendModeRules(client) {
  const data = await unwrap(getAllFrontendModeRules({ client }))
  return data?.rules ?? []
}

export async function findFrontendModeRuleByName(client, name) {
  const rules = await listFrontendModeRules(client)
  return rules.find((rule) => rule.name === name) ?? null
}

export async function nextFrontendModeRulePriority(client) {
  const rules = await listFrontendModeRules(client)
  return Math.max(E2E_PRIORITY_FLOOR - 1, ...rules.map((rule) => rule.priority)) + 1
}

export async function createFrontendModeRuleAndTrack(client, testInfo, overrides = {}) {
  const body = {
    name: `${E2E_FRONTEND_MODE_RULE_PREFIX}${testInfo.workerIndex}-${Date.now()}`,
    description: 'created by e2e',
    frontend_mode: 'hidden',
    ...overrides,
    allowed: { ...NO_ALLOWED, ...overrides.allowed },
  }
  assertAllowedIsScoped(body.allowed)
  if (body.priority === undefined) body.priority = await nextFrontendModeRulePriority(client)

  await unwrap(createFrontendModeRule({ client, body }))
  // POST answers 204 with no body: resolve the id through the list.
  const rules = await listFrontendModeRules(client)
  const created = rules.find(
    (rule) => rule.name === body.name && rule.priority === body.priority,
  )
  if (!created?.id) {
    throw new Error(`createFrontendModeRule: rule "${body.name}" not found after creating it`)
  }
  track(testInfo, 'frontend-mode-rule-id', created.id)
  return created
}

export async function updateFrontendModeRule(client, id, body) {
  assertAllowedIsScoped(body.allowed)
  return unwrap(sdkUpdateFrontendModeRule({ client, path: { rule_id: id }, body }))
}

export async function setFrontendModeRuleAllowed(client, id, allowed) {
  const full = { ...NO_ALLOWED, ...allowed }
  assertAllowedIsScoped(full)
  return unwrap(
    adminAllowedUpdate({ client, path: { table: ALLOWED_TABLE }, body: { id, allowed: full } }),
  )
}

// Alloweds enriched with names, as the dialog reads them.
export async function getFrontendModeRuleAllowed(client, id) {
  return unwrap(allowedTable({ client, path: { table: ALLOWED_TABLE }, body: { id } }))
}

export async function purgeE2eFrontendModeRules(client) {
  const rules = await listFrontendModeRules(client)
  const leftovers = rules.filter((rule) => rule.name.startsWith(E2E_FRONTEND_MODE_RULE_PREFIX))
  for (const rule of leftovers) {
    await deleteFrontendModeRule({ client, path: { rule_id: rule.id } })
  }
  return leftovers.length
}

// `client` is the target user's client: get-config answers for the caller.
// get-config is cached for up to 60 s, hence the default timeout. The e2e
// stack caches it for 1 s, so the poll is short enough not to be what a
// scenario waits for.
export async function waitForFrontendMode(
  client,
  expected,
  { timeoutMs = 65000, intervalMs = 250 } = {},
) {
  const deadline = Date.now() + timeoutMs
  let last
  for (;;) {
    last = (await unwrap(getUserConfig({ client })))?.frontend_mode
    if (last === expected) return last
    if (Date.now() >= deadline) {
      throw new Error(`frontend_mode is "${last}", expected "${expected}" after ${timeoutMs} ms`)
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
}
