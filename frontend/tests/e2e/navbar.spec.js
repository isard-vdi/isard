// @ts-check
const { test } = require('./login-page')
const { Navbar } = require('./navbar')

test.describe('Navbar', () => {
  test('the profile should work correctly', async ({ page }) => {
    const navbar = new Navbar(page)
    await navbar.goto()
    await navbar.profile('Administrator [admin]')
  })

  test('the administration should work correctly', async ({ page }) => {
    const navbar = new Navbar(page)
    await navbar.goto()
    await navbar.administration()
  })
})
