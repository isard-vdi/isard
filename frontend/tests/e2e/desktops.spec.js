// @ts-check
import { test as base } from '@playwright/test'
import { fixture as fixtureTemplates } from './templates-page'
import { fixture as fixtureResources } from './admin/resources-page'
import { PageDesktops } from './desktops-page'

const test = base.extend({ ...fixtureTemplates, ...fixtureResources })

test.describe('Desktops', () => {
  test('should be able to template it correctly', async ({ page, randomString, adminDownloads }) => {
    const desktops = new PageDesktops(page)

    const name = randomString.generate()
    const description = randomString.generateLong()

    await desktops.goto()
    await desktops.template(adminDownloads.name, name, description)
  })

  test('should be able to create a desktop correctly', async ({ page, randomString, templates, adminResourcesInterfaces }) => {
    const desktops = new PageDesktops(page)

    const name = randomString.generate()
    const description = randomString.generateLong()

    await desktops.goto()
    await desktops.new({ name, description, template: templates.name, networks: ['Default', adminResourcesInterfaces.name] })
  })
})
