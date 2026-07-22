// Manager-role coverage for Domains → Resources.
//
// Goals:
//   - Ensure manager tests run with worker-scoped reused session
//     (managerE2EPage fixture) and no login per test.
//   - Validate that manager can at least load/read the Resources screen.
//   - Validate mutation permissions explicitly: either success (<400) or
//     proper auth denial (401/403), depending on environment policy.

import { test, expect } from '../../fixtures/apiv4/index.js'
import { adminTableInsert, adminTableList } from '../../src/gen/apiv4/sdk.gen'

const RESOURCES_URL = '/isard-admin/admin/domains/render/Resources'

function managerName(testInfo, suffix = '') {
  return `e2e-mgr-${testInfo.workerIndex}-${Date.now()}${suffix ? `-${suffix}` : ''}`
}

async function gotoResourcesAsManager(page) {
  await page.goto(RESOURCES_URL)
}

test.describe('Manager Resources — webapp', () => {
  test.describe.configure({ mode: 'serial' })

  test('M1: manager does not see Resources in sidebar', async ({ managerE2EPage: page }) => {
    await page.goto('/isard-admin/admin')
    await page.waitForLoadState('domcontentloaded')

    await expect(page.locator('a[href*="/admin/domains/render/Resources"]')).toHaveCount(0)
    await expect(page.locator('a:has-text("Resources")')).toHaveCount(0)
  })

  test('M2: manager cannot read Resources datatables (401/403)', async ({ managerE2EPage: page, apiv4Manager }) => {
    await gotoResourcesAsManager(page)
    const redirectedToLogin = /\/login(\/|$|\?)/.test(page.url())

    if (!redirectedToLogin) {
      await expect(page.locator('a[href*="/admin/domains/render/Resources"]')).toHaveCount(0)
    }

    const listResult = await adminTableList({
      client: apiv4Manager,
      path: { table: 'interfaces' },
      body: { order_by: 'name' },
    })

    const status = listResult.response?.status ?? 0
    expect([401, 403]).toContain(status)
  })

  test('M3: manager mutation is denied (401/403)', async ({ apiv4Manager }, testInfo) => {
    const name = managerName(testInfo, 'qosnet')

    const insertResult = await adminTableInsert({
      client: apiv4Manager,
      path: { table: 'qos_net' },
      body: {
        name,
        description: 'manager mutation probe',
        allowed: { roles: false, categories: false, groups: false, users: false },
        bandwidth: {
          inbound: { '@average': 10000, '@peak': 15000, '@floor': 5000, '@burst': 20000 },
          outbound: { '@average': 10000, '@peak': 15000, '@burst': 20000 },
        },
      },
    })

    const status = insertResult.response?.status ?? 0
    expect([401, 403]).toContain(status)
  })
})
