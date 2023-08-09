// @ts-check
import { fixture as baseFixture } from './base'
import { test, expect } from '@playwright/test'

export class PageLogin {
  /**
     * @param {import('@playwright/test').Page} page
     */
  constructor (page) {
    this.page = page
    this.formInputs = {
      usr: page.getByPlaceholder('Username'),
      pwd: page.getByPlaceholder('Password'),
      login: page.getByRole('button', { name: 'Login' })
    }
  }

  async goto () {
    await this.page.goto('/login/default')
    await expect(this.page.getByRole('heading', { name: 'Login' })).toBeVisible()
  }

  async form (usr, pwd) {
    await this.formInputs.usr.fill(usr)
    await this.formInputs.pwd.fill(pwd)
    await this.formInputs.login.click()
  }

  async finished () {
    // This is because the login reload bug in the frontend
    await this.page.waitForURL('/desktops')

    await expect(this.page.getByAltText('Logo')).toBeVisible()
    await expect(this.page).toHaveURL('/desktops')
  }
}

export const fixture = {
  login: async ({ page }, use) => {
    const login = new PageLogin(page)
    await login.goto()
    await login.form('admin', 'IsardVDI')
    await login.finished()

    await use(login)
  },
  ...baseFixture
}

exports.test = test.extend(fixture)
