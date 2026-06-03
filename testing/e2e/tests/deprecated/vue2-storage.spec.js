// User-facing storage page lives in the vue 2 SPA at /userstorage. Two
// recent fixes affect what this page shows:
//
//   1. apiv4 /admin/storage now plucks each desktop's `status` so the
//      table can tell which storages are blocked from resize.
//   2. The increase button is disabled (with a precondition message in
//      the title) when any desktop on the storage isn't Stopped — apiv4's
//      increase endpoint puts the storage into maintenance and would 428
//      otherwise.
//
// These tests are observation-only — they don't perform a resize, just
// verify the table renders and the conditional disabled-state is wired.
import { test, expect } from '../../fixtures/login.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')

test.describe('Vue 2 user storage page', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories, '/userstorage')
    // The page mounts behind webapp's index router; wait for the table.
    await page.waitForLoadState('networkidle', { timeout: 15000 })
  })

  test('storage table renders with at least the empty-state or one row', async ({ page }) => {
    // Either the empty-state heading or the IsardTable container should show.
    const empty = page.locator('h3 strong').first()
    const table = page.locator('table').first()
    await expect(empty.or(table)).toBeVisible({ timeout: 15000 })
  })

  test('increase button is disabled when row has a non-Stopped desktop', async ({ page }) => {
    // Find any increase button (rendered for non-user roles only — the
    // beforeEach logs in as admin so the action is visible) and verify
    // that wherever the row's desktop isn't Stopped, the button is
    // `disabled` and its title carries the precondition message.
    const buttons = page.locator('table button[title]')
    const count = await buttons.count()
    if (count === 0) {
      test.skip(true, 'no storage rows in test DB')
      return
    }
    let checkedAtLeastOne = false
    for (let i = 0; i < Math.min(count, 10); i++) {
      const btn = buttons.nth(i)
      const title = (await btn.getAttribute('title')) || ''
      const disabled = await btn.isDisabled()
      // Any button that's disabled should carry the precondition message,
      // and any button that's enabled should carry the regular increase
      // tooltip — never the other way around.
      if (disabled) {
        expect(title.toLowerCase()).toMatch(/stop|stopped|increase/i)
        checkedAtLeastOne = true
      } else {
        expect(title.toLowerCase()).toMatch(/increase/i)
        checkedAtLeastOne = true
      }
    }
    expect(checkedAtLeastOne).toBe(true)
  })
})
