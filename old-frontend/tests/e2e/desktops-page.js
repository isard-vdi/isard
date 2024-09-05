import { PageTemplates } from './templates-page'

// @ts-check
import { expect } from '@playwright/test'

export class PageDesktops {
  /**
     * @param {import('@playwright/test').Page} page
     */
  constructor (page) {
    this.page = page
    this.pageTemplates = new PageTemplates(page)
  }

  async goto () {
    await this.page.goto('/desktops')
  }

  static getSearch (page) {
    return page.getByLabel('Filter')
  }

  static getCard (page, name) {
    return page.locator('.card').filter({ hasText: name })
  }

  static async waitForState (page, name, state) {
    await PageDesktops.getSearch(page).fill(name)

    await page.waitForSelector(`.text-state:has-text('${state}')`)
  }

  async template (desktop, name, description) {
    await PageDesktops.getSearch(this.page).fill(desktop)
    const card = PageDesktops.getCard(this.page, desktop)

    // Click the three dots
    await card.getByText('more_vert').click()

    // Click the template button
    await card.locator('.fab-item', { has: this.page.locator('.fa-cubes') }).click()

    await expect(this.page).toHaveURL('/templates/new')

    await this.pageTemplates.new(desktop, name, description)
  }

  async new ({ name, description, template, networks }) {
    await this.page.getByRole('button', { name: 'New Desktop' }).click()

    await this.page.getByLabel('Name').fill(name)
    await this.page.getByLabel('Description').fill(description)

    await this.page.getByText('Advanced options').click()

    await this.page.getByPlaceholder('Type to search').fill(template)
    await this.page.getByRole('cell', { name: template }).click()

    for (const network of networks) {
      const interfaces = this.page.locator('#interfaces')
      await interfaces.click()
      await interfaces.fill(network)
      await this.page.getByRole('option', { name: network }).click()
    }

    await this.page.getByText('Hardware').click()

    await this.page.getByRole('button', { name: 'Create' }).click()

    await this.page.waitForURL('/desktops')

    await PageDesktops.waitForState(this.page, name, 'Stopped')
  }

  async start (desktop) {

  }
}
