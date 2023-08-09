// @ts-check
import { PageDesktops } from './desktops-page'
import { fixture as baseFixture } from './admin/downloads-page'
import { test, expect } from '@playwright/test'

export class PageTemplates {
  /**
     * @param {import('@playwright/test').Page} page
     */
  constructor (page) {
    this.page = page
    this.filter = page.getByPlaceholder('Type to search')
    this.yourTemplates = page.getByRole('tab', { name: 'Your templates' })
  }

  async goto () {
    const url = '/templates'
    await this.page.goto(url)

    await expect(this.yourTemplates).toBeVisible()
  }

  async new (desktop, name, description) {
    await this.page.getByLabel('Name').fill(name)
    await this.page.getByLabel('Description').fill(description)
    await this.page.getByRole('button', { name: 'Create' }).click()

    await this.page.waitForURL('/desktops')

    await PageDesktops.waitForState(this.page, desktop, 'Stopped')

    await this.goto()

    // TODO: THIS IS REALLY UGLY AND HACKY. WHY DOES THIS HAPPEN????
    await this.page.reload()
    await this.goto()
    await this.page.reload()
    await this.goto()
    await this.page.reload()
    await this.goto()

    await expect(await this.get(name)).toEqual({
      name,
      description
    })
  }

  async get (name) {
    await this.filter.fill(name)

    return {
      name: await this.page.getByRole('cell').nth(1).textContent().then(name => name.trim()),
      description: await this.page.getByRole('cell').nth(2).textContent().then(description => description.trim())
    }
  }
}

export const fixture = {
  templates: async ({ page, adminDownloads, randomString }, use) => {
    const name = randomString.generate()
    const description = randomString.generateLong()

    const templates = new PageTemplates(page)
    const desktops = new PageDesktops(page)

    await desktops.goto()
    await desktops.template(adminDownloads.name, name, description)

    await use({ pageTemplates: templates, name, description })
  },
  ...baseFixture
}

exports.test = test.extend(fixture)
