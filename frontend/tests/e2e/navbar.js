// @ts-check
const { test } = require('./login-page')
const { expect } = require('@playwright/test')

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

exports.test = test.extend({
  navbar: async ({ page }, use) => {
    const navbar = new Navbar(page)
    await navbar.goto()

    await use(navbar)
  }
})
