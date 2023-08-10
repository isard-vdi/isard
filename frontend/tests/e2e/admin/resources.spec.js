// @ts-check
const { test } = require('../navbar')
const { PageAdminResources } = require('./resources-page')

test.describe('ResourcesInterfaces', () => {
  test('should be able to create an interface correctly', async ({ page, administration }) => {
    const resources = new PageAdminResources(page)
    await resources.goto()

    const name = Math.random().toString(36).slice(2)

    await resources.newInterface({ name, description: 'desc', type: 'network', typeOptions: 'interface name', model: 'virtio' })
  })
})
