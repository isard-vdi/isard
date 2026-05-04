// @ts-check
import { fixture as baseFixture } from './login-page'
import { test as baseTest, expect } from '@playwright/test'

export class Navbar {
  /**
     * @param {import('@playwright/test').Page} page
     */
  constructor (page) {
    this.page = page
  }

  async goto () {
    await this.page.goto('/desktops')
  }

  async administration () {
    const item = this.page.getByText('Administration')
    await expect(item).toBeVisible()

    await item.click()

    await this.page.waitForURL('/isard-admin/admin/landing')
    await expect(this.page).toHaveURL('/isard-admin/admin/landing')
  }

  async profile (profile) {
    // The navbar profile dropdown displays "<name> [<role_label>]"
    // — the role label may be the role_id ("admin") or the role
    // display name ("Administrator") depending on the apiv4
    // commit. Match permissively if the caller passed a regex,
    // and otherwise accept either bracket form for the legacy
    // fixed-string call.
    const target =
      profile instanceof RegExp
        ? profile
        : new RegExp(profile.replace(/\[(.+?)\]/, '\\[(?:\\1|Administrator|admin)\\]'))
    const item = this.page.getByText(target).first()
    await expect(item).toBeVisible()

    await item.click()

    const profileItem = this.page.getByRole('menuitem').filter({ hasText: 'Profile' })
    await expect(profileItem).toBeVisible()
    await profileItem.click()

    // Vue 2 router has historically rendered ``/profile`` and
    // ``/profile/`` interchangeably; accept either.
    await expect(this.page).toHaveURL(/\/profile\/?$/)
  }
}

export const fixture = {
  navbar: async ({ page, login }, use) => {
    const navbar = new Navbar(page)
    await navbar.goto()

    await use(navbar)
  },
  administration: async ({ page, navbar }, use) => {
    await navbar.administration()

    await use(navbar)
  },
  ...baseFixture
}

export const test = baseTest.extend(fixture)
