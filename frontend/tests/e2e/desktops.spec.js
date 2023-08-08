// @ts-check
const { test } = require('./admin/downloads-page')
const { PageDesktops } = require('./desktops-page')

test.describe('Desktops', () => {
  test('should be able to template it correctly', async ({ page, adminDownloads }) => {
    const desktops = new PageDesktops(page)
    await desktops.goto()
    await desktops.template('Slax 9.3.0')
  })
})
