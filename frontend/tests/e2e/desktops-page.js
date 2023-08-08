// @ts-check
const { expect } = require('@playwright/test')

export class PageDesktops {
  /**
     * @param {import('@playwright/test').Page} page
     */
  constructor (page) {
    this.page = page
    this.search = page.getByLabel('Filter')
  }

  async goto () {
    await this.page.goto('/desktops')
  }

  async template (desktop) {
    await this.search.fill(desktop)
    const card = this.page.locator('.card').filter({ hasText: desktop })

    // Click the three dots
    await card.getByText('more_vert').click()

    // Click the template button
    await card.locator('.fab-item', { has: this.page.locator('.fa-cubes') }).click()

    await expect(this.page).toHaveURL('/templates/new')
  }

  async start (desktop) {

  }
}
