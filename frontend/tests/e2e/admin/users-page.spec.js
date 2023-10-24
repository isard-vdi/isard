// @ts-check
import { test } from '../navbar'
import { PageAdminUsers } from './users-page'

test.describe('Users', () => {
  const roles = ['manager', 'advanced', 'user']
  for (const role of roles) {
    test(`should be able to generate enrollment keys correctly for role '${role}'`, async ({ page, administration }) => {
      const users = new PageAdminUsers(page)
      await users.goto()

      const code = await users.groupEnrollmentKey('default', role)
      test.expect(code).toBeTruthy()
    })
  }
})
