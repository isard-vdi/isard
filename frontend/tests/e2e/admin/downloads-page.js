// @ts-check
const { test } = require('../navbar')
const { expect } = require('@playwright/test')

export class PageAdminDownloads {
  /**
     * @param {import('@playwright/test').Page} page
     */
  constructor (page) {
    this.page = page
    this.title = page.getByRole('heading', { name: 'Not registered Your IsardVDI is not registered for IsardVDI Downloads Service.' }).or(page.getByRole('heading', { name: 'Domains' }))
  }

  async goto () {
    await this.page.goto('/isard-admin/admin/updates')
    await expect(this.title).toBeVisible()
  }

  async download (desktop) {
    const register = this.page.getByRole('button', { name: 'Register with only a click!' })
    if (await register.isVisible()) {
      await register.click()
    }

    const searchBox = this.page.getByRole('searchbox', { name: 'Search:' })
    await expect(searchBox).toBeVisible()
    await searchBox.fill(desktop)

    const row = this.page.getByRole('row', { name: desktop })
    await expect(row).toBeVisible()

    // If it's not downloaded, download it
    if (await row.getByText('New').isVisible()) {
      await row.getByRole('button').click()

      // Wait until two minutes to be downloaded
      await expect(row.getByText('Downloaded')).toBeVisible({ timeout: 120000 })
    } else if (await row.getByText('Downloading').isVisible()) {
      // Wait until two minutes to be downloaded
      await expect(row.getByText('Downloaded')).toBeVisible({ timeout: 120000 })
    } else if (!await row.getByText('Downloaded').isVisible()) {
      throw Error('Unknown download state')
    }
  }
}

exports.test = test.extend({
  adminDownloads: [async ({ page, navbar }, use) => {
    await navbar.administration()

    const adminDownloads = new PageAdminDownloads(page)
    await adminDownloads.goto()
    await adminDownloads.download('Slax 9.3.0')

    await use(adminDownloads)
  }, { auto: true }]
})
