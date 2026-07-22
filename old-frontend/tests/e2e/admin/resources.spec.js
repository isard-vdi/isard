// @ts-check
import { test } from '../navbar'
import { PageAdminResources } from './resources-page'

test.describe('ResourcesInterfaces', () => {
  test('should be able to create an interface correctly', async ({ page, administration }) => {
    const resources = new PageAdminResources(page)
    await resources.goto()
    // The interface form needs an admin-managed network resource
    // (only present in USAGE=test or properly seeded staging).
    // Skip if the form's "type" select doesn't expose any options.
    const typeSelect = page.locator('select[name="type"]').first()
    const hasOptions = await typeSelect
      .isVisible({ timeout: 5000 })
      .then(() => typeSelect.locator('option').count())
      .catch(() => 0)
    test.skip(
      !hasOptions,
      'Admin resources interface form unreachable on this stack — bring up with USAGE=test or seed the resources fixture'
    )

    const name = Math.random().toString(36).slice(2)

    await resources.newInterface({ name, description: 'desc', type: 'network', typeOptions: 'interface name', model: 'virtio' })
  })
})
