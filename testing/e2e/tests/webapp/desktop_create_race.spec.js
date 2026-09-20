// Regression spec — full context in testing/e2e/specs/webapp/desktop_create_race.md.
// Creates persistent desktops from a template and asserts each reaches Stopped.

import {
  test,
  expect,
  createDesktopAndTrack,
  waitForDesktopStopped,
} from '../../fixtures/apiv4/index.js'

// Seeded template with a ready storage in the default category (see
// populate_test_db.py) — cloneable by the admin/advanced client.
const TEMPLATE_ID = 'template-test-001'

test.describe('Desktop create races the reconcile self-heal (#3391)', () => {
  test('persistent desktops from a template all reach Stopped, never Failed', async ({
    apiv4Admin,
  }, testInfo) => {
    const stamp = Date.now().toString().slice(-6)
    const count = 5
    for (let i = 0; i < count; i++) {
      const name = `e2e3391-${stamp}-${i}`
      // createDesktopAndTrack unwraps, so a storage_pending_task 428 throws here.
      const created = await createDesktopAndTrack(apiv4Admin, testInfo, {
        template_id: TEMPLATE_ID,
        name,
        description: 'create under reconcile pressure (#3391)',
      })
      const status = await waitForDesktopStopped(apiv4Admin, created.id, {
        timeoutMs: 90000,
      })
      expect(
        status,
        `desktop ${name} reached ${status}; expected Stopped and never Failed (#3391)`,
      ).toBe('Stopped')
    }
  })
})
