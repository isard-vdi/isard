// @ts-check
const { test } = require('../navbar')
const { PageAdminDownloads } = require('./downloads-page')

test.describe('Downloads', () => {
  test('should download slax correctly', async ({ page, administration }) => {
    const downloads = new PageAdminDownloads(page)
    await downloads.goto()
    await downloads.download('TetrOS')
  })
})
