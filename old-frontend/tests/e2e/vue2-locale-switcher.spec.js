// @ts-check
//
// Locale switcher smoke — i18n locale change via the navbar
// language dropdown.
//
// The Language component (old-frontend/src/components/Language.vue)
// renders a 🌐 dropdown with 9 language options. Switching changes
// ``$i18n.locale`` and persists to localStorage. A regression in
// the i18n loader could fail to swap nav text.

import { expect } from '@playwright/test'
import { test } from './login-page'

const NAV_DESKTOPS_BY_LOCALE = {
  ca: /escriptor/i,
  es: /escritorio/i,
  fr: /bureau/i,
  pl: /pulpit/i,
  // English is the default; switching back asserts text contains "Desktops".
  en: /desktops/i
}

test.describe('Vue 2 locale switcher', () => {
  test('switching to Catalan changes navbar text and back', async ({ page, login }) => {
    await page.goto('/desktops')
    await page.waitForLoadState('networkidle')

    // The language dropdown is rendered as a 🌐 button with a
    // language-name label. Find by the globe emoji prefix.
    const langDropdown = page
      .getByRole('button')
      .filter({ hasText: /🌐|english|català|castellano/i })
      .first()
    if (!(await langDropdown.isVisible({ timeout: 5000 }).catch(() => false))) {
      test.skip(true, 'locale switcher button not visible (config flag may hide it)')
      return
    }
    await langDropdown.click()

    // Click the "Català" item.
    const caItem = page.getByRole('menuitem').filter({ hasText: /^Català$/i }).first()
    await caItem.click()

    // Wait for re-render. The Vue 2 i18n loader is sync once the
    // locale file is loaded; a brief idle should suffice.
    await page.waitForTimeout(500)

    // Navbar "Desktops" link text should now be in Catalan.
    const body = (await page.textContent('body')) ?? ''
    expect(
      body,
      'after switching to Catalan, body text should match Catalan locale pattern'
    ).toMatch(NAV_DESKTOPS_BY_LOCALE.ca)

    // Switch back to English.
    await langDropdown.click()
    const enItem = page.getByRole('menuitem').filter({ hasText: /^English$/i }).first()
    await enItem.click()
    await page.waitForTimeout(500)

    const bodyEn = (await page.textContent('body')) ?? ''
    expect(
      bodyEn,
      'after switching back to English, body should match English locale pattern'
    ).toMatch(NAV_DESKTOPS_BY_LOCALE.en)
  })
})
