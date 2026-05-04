// @ts-check
import { test } from './login-page'
import { expect } from '@playwright/test'

/**
 * Regression for round-3 Bug #39 — old-frontend logout JS errors.
 *
 * Before the fix, every logout fired two ``TypeError`` JS console
 * errors:
 *
 *   TypeError: can't access property "role_id", _vm.getUser is null
 *   TypeError: can't access property "name", _vm.getUser is null
 *
 * The store's ``logout`` action calls ``resetStore`` which sets
 * ``state.auth.user = null`` before the navigation away from the
 * authenticated layout fires. The persistent navbar re-renders with
 * ``getUser = null`` and the ``v-if="getUser.role_id !== 'user'"``
 * bindings + the ``{{ getUser.name }} [{{ getUser.role_name }}]``
 * template tripped.
 *
 * The fix (commit 75869eeca) wraps the navbar's ``b-collapse`` in
 * ``v-if="getUser"`` so the whole inner content hides on logout.
 *
 * This spec pins it: log in, click logout, assert no console errors.
 */
test.describe('Bug #39 regression — logout JS console clean', () => {
  test('logout from authenticated session emits zero console errors', async ({
    page,
    login
  }) => {
    // The ``login`` fixture has already logged us in and landed on a
    // post-login page. Now hook the console listener BEFORE clicking
    // logout — we want to capture any errors emitted DURING the
    // navbar re-render and the navigation to ``/login``.
    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(String(err))
    })

    // Click the navbar dropdown that hosts the logout link. The
    // dropdown is button-content slot rendered as a span carrying the
    // user's name; with the b-collapse v-if=getUser fix it stays
    // mounted while the user is logged in.
    const userDropdown = page
      .getByRole('button')
      .filter({ hasText: /\[admin\]|\[manager\]|\[user\]/ })
      .first()
    await userDropdown.click()

    const logoutItem = page.getByRole('menuitem').filter({ hasText: /log ?out/i })
    await logoutItem.click()

    // Wait for the navigation to the login page (or wherever the
    // configured logout redirect lands). The persistent navbar
    // re-renders during this transition — that's where the bug fired.
    await page.waitForURL((u) => /\/login(\/|$|\?)|\/authentication\//.test(u.toString()), {
      timeout: 15000
    })

    // Filter out unrelated noise the dev-mode build emits (e.g. dev
    // server CSP warnings, vue-devtools probes). The bug's specific
    // signature is ``getUser is null``; any other console error
    // would be a different regression and should still fail this
    // test (no allowlist for now).
    const fatalErrors = consoleErrors.filter((e) => {
      // Suppress only noise that's unrelated to navbar re-render and
      // existed before the bug fix.
      if (/source map|sourcemap/i.test(e)) return false
      if (/Failed to load resource:.*404|net::ERR_FAILED/.test(e)) return false
      return true
    })

    expect(
      fatalErrors,
      `expected zero console errors during logout, got:\n${fatalErrors.join('\n')}`
    ).toEqual([])
  })
})
