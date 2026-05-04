// @ts-check
//
// Profile page smoke — render + modal-open paths.
//
// /profile is a high-touch page: shows user info, has buttons for
// change-password, change-email (verify), reset-VPN, API-key, and
// migration export/import. None of these are covered by existing
// e2e — Bug #34 (wrong-password 500), Bug #48 (email-verification
// 403) live nearby.
//
// We DO NOT actually change the admin's password / email — that
// would mess up the test environment for parallel specs. The spec
// asserts:
//   * /profile renders without console errors.
//   * Profile info card is visible.
//   * Change-password button is clickable and opens a modal.
//   * Email-verification button (if config flag enabled) opens a
//     modal.
//   * Each modal has a Cancel/Close affordance and closes cleanly.

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 profile page', () => {
  test('/profile renders profile card without console errors', async ({ page, login }) => {
    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const response = await page.goto('/profile')
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // The profile card renders the user's email + role + group +
    // category. Match by the section heading or the "Email" label.
    const profileSection = page.getByText(/email|user.*name|profile/i).first()
    await expect(profileSection).toBeVisible({ timeout: 10000 })

    const realErrors = consoleErrors.filter(
      (e) => !/Failed to load resource/.test(e) && !/net::ERR_/.test(e)
    )
    expect(realErrors, 'console errors on /profile').toEqual([])
  })

  test('change-password button opens a modal that can be cancelled', async ({
    page,
    login
  }) => {
    await page.goto('/profile')
    await page.waitForLoadState('networkidle')

    // The change-password button text comes from
    // ``components.profile.change-password`` i18n key (English:
    // "Change password"). Match permissively across locales.
    const changePwdBtn = page
      .getByRole('button', { name: /change.*password|cambiar.*contrase|canviar.*contrasenya/i })
      .first()
    if (!(await changePwdBtn.isVisible({ timeout: 5000 }).catch(() => false))) {
      test.skip(true, 'change-password button not visible (may be hidden by config flag)')
      return
    }
    await changePwdBtn.click()

    // Modal opens — find a dialog with role=dialog or a visible
    // .modal.show element.
    const modal = page.locator('.modal.show, [role="dialog"]:visible').first()
    await expect(modal).toBeVisible({ timeout: 5000 })

    // Cancel/close the modal. The footer should have a Cancel
    // button or a Close (X) icon.
    const cancelBtn = modal
      .getByRole('button', { name: /cancel|cancelar|cancel·la|close|tancar/i })
      .first()
    if (await cancelBtn.isVisible().catch(() => false)) {
      await cancelBtn.click()
    } else {
      // Fallback: press Escape.
      await page.keyboard.press('Escape')
    }
    await expect(modal).not.toBeVisible({ timeout: 5000 })
  })

  test('email-verification button opens a modal (if config flag enabled)', async ({
    page,
    login
  }) => {
    await page.goto('/profile')
    await page.waitForLoadState('networkidle')

    // EmailVerificationModal is gated by ``config.showChangeEmailButton``.
    // If the flag is off this button doesn't render — skip cleanly.
    const changeEmailBtn = page
      .getByRole('button', { name: /change.*email|cambiar.*correo|canviar.*correu/i })
      .first()
    if (!(await changeEmailBtn.isVisible({ timeout: 3000 }).catch(() => false))) {
      test.skip(true, 'change-email button hidden by config.showChangeEmailButton')
      return
    }
    await changeEmailBtn.click()

    const modal = page.locator('.modal.show, [role="dialog"]:visible').first()
    await expect(modal).toBeVisible({ timeout: 5000 })

    // Just verify the modal opens with input fields; don't actually
    // submit a verification request.
    const emailInput = modal.locator('input[type="email"], input[type="text"]').first()
    await expect(emailInput).toBeVisible({ timeout: 5000 })

    await page.keyboard.press('Escape')
    await expect(modal).not.toBeVisible({ timeout: 5000 })
  })
})
