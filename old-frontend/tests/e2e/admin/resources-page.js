// @ts-check
import { fixture as baseFixture } from '../navbar'
import { test as base, expect } from '@playwright/test'

export class PageAdminResources {
  /**
     * @param {import('@playwright/test').Page} page
     */
  constructor (page) {
    this.page = page
    this.title = page.getByRole('heading', { name: 'Resources' })
    this.interfacesTitle = page.getByRole('heading', { name: 'Interfaces' })
  }

  async goto () {
    const url = '/isard-admin/admin/domains/render/Resources'
    await this.page.goto(url)

    await expect(this.title).toBeVisible()
  }

  async newInterface ({ name, description, type, typeOptions, model, qos }) {
    await this.page.locator('a').filter({ hasText: 'Add new' }).first().click()
    await this.page.getByPlaceholder('New interface name').fill(name)
    await this.page.getByPlaceholder('Interface description').fill(description)
    await this.page.getByLabel('Type: *').selectOption(type)
    await this.page.getByPlaceholder('Select Type first').fill(typeOptions)
    await this.page.locator('#modalInterfacesForm #model').selectOption(model)
    await this.page.getByText('Add interface').click()

    await expect(await this.getInterface(name)).toEqual({
      name,
      description,
      network: typeOptions
    })
  }

  async getInterface (name) {
    await this.page.locator('#table-interfaces_filter').getByLabel('Search:').fill(name)
    const interfaceRow = this.page.getByRole('row', { name: name })
    await expect(interfaceRow).toBeVisible()

    const result = {}

    result.name = await interfaceRow.getByRole('gridcell').nth(1).textContent()
    result.description = await interfaceRow.getByRole('gridcell').nth(2).textContent()
    result.network = await interfaceRow.getByRole('gridcell').nth(3).textContent()

    return result
  }
}

export const fixture = {
  adminResourcesInterfaces: async ({ page, administration, randomString }, use) => {
    const name = randomString.generate()
    const description = randomString.generateLong()
    const interfaceType = 'network'
    const typeOptions = 'default'
    const model = 'virtio'

    const adminResources = new PageAdminResources(page)
    await adminResources.goto()
    await adminResources.newInterface({ name, description, type: interfaceType, typeOptions, model })

    await use({
      pageAdminResources: adminResources,
      name,
      description,
      type: interfaceType,
      typeOptions,
      model
    })
  },
  ...baseFixture
}

export const test = base.extend(fixture)
