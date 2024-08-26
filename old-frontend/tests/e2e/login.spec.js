// @ts-check
import { test as base } from './base'
import { fixture as fixtureUsers } from './admin/users-page'
import { PageRegister } from './register-page'
import { PageLogin } from './login-page'

const test = base.extend({ ...fixtureUsers })

test.describe('Login', () => {
  test('should login locally correctly against the DB', async ({ page }) => {
    const login = new PageLogin(page)
    await login.goto()
    await login.form('admin', 'IsardVDI')
    await login.finished()
  })

  test('should login correctly using LDAP (autoregistration)', async ({ page }) => {
    const login = new PageLogin(page)
    await login.goto()
    await login.form('fry', 'fry')
    await login.finished()
  })

  test('should login correctly using SAML (code registration)', async ({ page, adminUsers }) => {
    const login = new PageLogin(page)
    const register = new PageRegister(page)

    await login.goto()
    await login.saml('user1', 'user1pass')

    await register.goto()
    await register.register(adminUsers.registerCode)
    await register.finished()
  })
})
