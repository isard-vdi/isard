// @ts-check
import { test } from './login-page'
import { Navbar } from './navbar'

test.describe('Navbar', () => {
  test('the profile should work correctly', async ({ page, login }) => {
    const navbar = new Navbar(page)
    await navbar.goto()
    await navbar.profile('Administrator [admin]')
  })

  test('the administration should work correctly', async ({ page, login }) => {
    const navbar = new Navbar(page)
    await navbar.goto()
    await navbar.administration()
  })
})
