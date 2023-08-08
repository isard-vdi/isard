// @ts-check
const { test } = require('../navbar')
const { PageAdminDownloads } = require('./downloads-page')

test.beforeEach(async ({ navbar }) => {
  await navbar.administration()
})

test.describe('Downloads', () => {
  test('should download slax correctly', async ({ page }) => {
    const downloads = new PageAdminDownloads(page)
    await downloads.goto()
    await downloads.download('Slax 9.3.0')
  })
})
