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
    const item = this.page.getByText(profile, { exact: true })
    await expect(item).toBeVisible()

    await item.click()

    const profileItem = this.page.getByRole('menuitem').filter({ hasText: 'Profile' })
    await expect(profileItem).toBeVisible()
    await profileItem.click()

    await expect(this.page).toHaveURL('/profile/')
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
