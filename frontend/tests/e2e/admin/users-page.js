// @ts-check
import { fixture as baseFixture } from '../navbar'
import { test as base, expect } from '@playwright/test'

export class PageAdminUsers {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor (page) {
    this.page = page
    this.title = page.getByRole('heading', { name: 'Management' }).or(page.getByRole('heading', { name: 'Domains' }))
    this.groupsSection = page.getByText('Groups Add new CSV')
  }

  async goto () {
    await this.page.goto('/isard-admin/admin/users/Management')
    await expect(this.title).toBeVisible()
  }

  /**
   * @param {string} group The group name
   * @param {"manager"|"advanced"|"user"} role The role that the key will be generated
   * @returns {Promise<string>} The register key
   */
  async groupEnrollmentKey (group, role) {
    // TODO: Filter by group
    const searchBox = this.groupsSection.getByRole('searchbox', { name: 'Search:' })
    await expect(searchBox).toBeVisible()
    await searchBox.fill(group)

    const row = this.groupsSection.getByRole('row', { name: group })
    await expect(row).toBeVisible()

    // Click on the '+' icon
    await row.getByRole('button').click()

    // Click on the enrollment key button
    const enrollment = this.groupsSection.getByRole('button', { name: 'Enrollment' })
    await expect(enrollment).toBeVisible()
    await enrollment.click()

    const modal = this.page.getByText('Close Enrollment keys Managers Advanced Users')
    await expect(modal).toBeVisible()

    let check
    let key
    if (role === 'manager') {
      check = modal.locator('.col-md-4').filter({ hasText: 'Managers' }).locator('.checkbox')
      key = modal.getByPlaceholder('Manager enrollment key')
    } else if (role === 'advanced') {
      check = modal.locator('.col-md-4').filter({ hasText: 'Advanced' }).locator('.checkbox')
      key = modal.getByPlaceholder('Advanced enrollment key')
    } else if (role === 'user') {
      check = modal.locator('.col-md-4').filter({ hasText: 'Users' }).locator('.checkbox')
      key = modal.getByPlaceholder('User enrollment key')
    } else {
      throw Error('Unknown role: ' + role)
    }

    await check.click() // If the check is already checked, it will return a confirmation modal, we can ignore it

    await expect(key).toBeVisible()

    return await key.inputValue()
  }
}

export const fixture = {
  adminUsers: async ({ page, administration }, use) => {
    const group = 'default'
    const role = 'advanced'

    const adminUsers = new PageAdminUsers(page)
    await adminUsers.goto()
    const registerCode = await adminUsers.groupEnrollmentKey(group, role)

    await use({
      pageAdminUsers: adminUsers,
      registerCode
    })
  },
  ...baseFixture
}

export const test = base.extend(fixture)
