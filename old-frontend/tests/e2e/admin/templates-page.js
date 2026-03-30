// @ts-check
import { fixture as baseFixture } from '../navbar'
import { test as base, expect } from '@playwright/test'

export class PageAdminTemplates {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor (page) {
    this.page = page
  }

  async goto () {
    await this.page.goto('/isard-admin/admin/domains/render/Templates')
    // Wait for the DataTable to be loaded
    await expect(this.page.locator('#table-templates-allowed')).toBeVisible({ timeout: 15000 })
  }

  /**
   * Click the delete button for a template by name
   * @param {string} templateName
   */
  async clickDelete (templateName) {
    // Search for the template
    const searchBox = this.page.locator('#table-templates-allowed_filter input[type="search"]')
    await searchBox.fill(templateName)
    await this.page.waitForTimeout(500) // DataTable filter debounce

    // Find the row and click the delete button
    const row = this.page.locator('#table-templates-allowed tbody tr').filter({ hasText: templateName }).first()
    await expect(row).toBeVisible({ timeout: 5000 })
    await row.locator('.btn-delete-template').click()

    // Wait for modal to appear
    await expect(this.page.locator('#modalDeleteTemplate')).toBeVisible({ timeout: 5000 })
  }

  /**
   * Get the delete modal element
   */
  getDeleteModal () {
    return this.page.locator('#modalDeleteTemplate')
  }

  /**
   * Get all rows in the nested template tree table
   * @returns {Promise<Array<{title: string, kind: string, user: string, category: string, group: string}>>}
   */
  async getTreeRows () {
    const modal = this.getDeleteModal()
    await expect(modal.locator('#nestedTemplateTable')).toBeVisible({ timeout: 5000 })

    // Wait for rows to be populated
    await this.page.waitForTimeout(1000)

    const rows = modal.locator('#nestedTemplateTable tbody tr')
    const count = await rows.count()
    const result = []

    for (let i = 0; i < count; i++) {
      const row = rows.nth(i)
      const cells = row.locator('td')
      result.push({
        title: (await cells.nth(0).textContent() || '').trim(),
        kind: (await cells.nth(1).textContent() || '').trim(),
        duplicate: (await cells.nth(2).textContent() || '').trim(),
        user: (await cells.nth(3).textContent() || '').trim(),
        role: (await cells.nth(4).textContent() || '').trim(),
        category: (await cells.nth(5).textContent() || '').trim(),
        group: (await cells.nth(6).textContent() || '').trim()
      })
    }

    return result
  }

  /**
   * Check if the manager warning is visible (cross-category derivatives)
   */
  async isManagerWarningVisible () {
    return this.getDeleteModal().locator('#manager-warning').isVisible()
  }

  /**
   * Check if the delete button is enabled
   */
  async isDeleteButtonEnabled () {
    const sendBtn = this.getDeleteModal().locator('#send')
    return !(await sendBtn.isDisabled())
  }

  /**
   * Click the delete button in the modal
   */
  async confirmDelete () {
    const sendBtn = this.getDeleteModal().locator('#send')
    await expect(sendBtn).toBeEnabled()
    await sendBtn.click()
  }

  /**
   * Close the delete modal
   */
  async closeDeleteModal () {
    await this.getDeleteModal().locator('button.close, [data-dismiss="modal"]').first().click()
    await expect(this.getDeleteModal()).not.toBeVisible()
  }
}

export const fixture = {
  adminTemplates: async ({ page, administration }, use) => {
    const adminTemplates = new PageAdminTemplates(page)
    await adminTemplates.goto()
    await use(adminTemplates)
  },
  ...baseFixture
}

export const test = base.extend(fixture)
