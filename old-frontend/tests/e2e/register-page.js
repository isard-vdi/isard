import { expect } from '@playwright/test'

export class PageRegister {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor (page) {
    this.page = page
    this.formInputs = {
      code: page.getByPlaceholder('Sign up code'),
      signup: page.getByRole('button', { name: 'Sign up' })
    }
  }

  async goto () {
    await this.page.waitForURL('/register')

    await expect(this.page.getByRole('heading', { name: 'Sign Up' })).toBeVisible()
  }

  /**
   * @param {string} code
   */
  async register (code) {
    this.formInputs.code.fill(code)
    this.formInputs.signup.click()
  }

  async finished () {
    // This is because the login reload bug in the frontend
    await this.page.waitForURL('/desktops')

    await expect(this.page.getByAltText('Logo')).toBeVisible()
    await expect(this.page).toHaveURL('/desktops')
  }
}
