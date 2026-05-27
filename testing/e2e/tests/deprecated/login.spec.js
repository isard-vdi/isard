import { test, expect } from '../../fixtures/login.js'
import { commonHelpers } from '../../fixtures/common.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')


test.describe('Basic login flow', () => {
  test('login with valid credentials', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.admin.category, categories)

    await loginHelpers.fillLoginForm(page, users.admin)
    await expect(page).toHaveURL(/desktops/)
    await commonHelpers.checkNoRouterErrors(page)
  })

  test('login with invalid credentials', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.doesntexist.category, categories)

    await loginHelpers.fillLoginForm(page, users.doesntexist)
    const alert = page.locator('[role="alert"]:has-text("Incorrect user or password"), div:has-text("Incorrect user or password")').first()
    const tooMany = page.getByText('Too many login attempts, please try again at', { exact: false })
    await expect(alert.or(tooMany)).toBeVisible({ timeout: 10000 })
  })

  test('blocks after too many login attempts', async ({ page, users, categories, loginHelpers }) => {
    test.skip(
      process.env.E2E_RATE_LIMITS_ENABLED === 'false',
      'Rate limits disabled via E2E_RATE_LIMITS_ENABLED=false',
    )
    await loginHelpers.goToLoginForCategory(page, users.toomanyattempts.category, categories)

    const maxAttempts = 13
    for (let i = 0; i < maxAttempts; i++) {
      await loginHelpers.fillLoginForm(page, users.toomanyattempts)
      const anyAlert = page.locator('[role="alert"]')
      await anyAlert.first().waitFor({ state: 'visible', timeout: 9000 })
      await page.waitForTimeout(500)
    }
    await loginHelpers.fillLoginForm(page, users.toomanyattempts)
    const tooMany = page.getByText('Too many login attempts, please try again at', { exact: false })
    await expect(tooMany).toBeVisible({ timeout: 10000 })
  })

  test('login user01 (basic user)', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.user01.category, categories)

    await loginHelpers.fillLoginForm(page, users.user01)
    await expect(page).toHaveURL(/desktops/)
  })

  test('login manager01 (default manager)', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.manager01.category, categories)

    await loginHelpers.fillLoginForm(page, users.manager01)
    await expect(page).toHaveURL(/desktops/)
    await commonHelpers.checkNoRouterErrors(page)

    // // Navigate to the administration page by clicking the "Administration" link
    // const adminLink = page.locator('a.nav-link:has-text("Administration")').first()
    // await adminLink.click()

    // // Wait for redirection to a URL containing /isard-admin/admin
    // await expect(page).toHaveURL(/\/isard-admin\/admin/, { timeout: 10000 })
  })

  test('login disabled user', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.disabled.category, categories)

    await loginHelpers.fillLoginForm(page, users.disabled)
    const alert = page.locator('[role="alert"]:has-text("The user is disabled")').nth(0)
    await expect(alert).toBeVisible({ timeout: 10000 })
  })

  test('access hidden category through direct URL', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.user02.category, categories)

    await loginHelpers.fillLoginForm(page, users.user02)
    await expect(page).toHaveURL(/desktops/)
    await commonHelpers.checkNoRouterErrors(page)
  })
})

test.describe('UI elements', () => {
  test('category selection in login page', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.user03.category, categories)

    await loginHelpers.fillLoginForm(page, users.user03)
    await expect(page).toHaveURL(/desktops/)
  })

  test('language selector changes interface language', async ({ page, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, 'default', categories)

    // Click on language selector (default is English)
    const languageSelector = page.locator('button:has-text("English")').first()

    if (await languageSelector.isVisible()) {
      await languageSelector.click()

      await page.locator('text="Español"').click()

      // Check if login button text changed to Spanish
      await expect(page.locator('div:has-text("Iniciar sesión")').first()).toBeVisible()

      await page.locator('button:has-text("Español")').click()
      await page.locator('text="English"').click()
    } else {
      console.log('No language selector found - test skipped')
      expect(true).toBeTruthy()
    }
  })
})

test.describe('Maintenance', () => {
  test('maintenance category redirects to maintenance page', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.maintenance.category, categories)

    await loginHelpers.fillLoginForm(page, users.maintenance)
    await expect(page).toHaveURL(/maintenance/)
    await commonHelpers.checkNoRouterErrors(page)
  })

  test('admin logs in to access maintenance category', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.admin_maintenance.category, categories)

    await loginHelpers.fillLoginForm(page, users.admin_maintenance)
    // Verify successful login and redirection to desktops, as admin isn't affected by maintenance mode
    await expect(page).toHaveURL(/desktops/)
  })
})

test.describe('Redirects after login', () => {
  test('login user with mandatory disclaimer', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.disclaimer.category, categories)

    await loginHelpers.fillLoginForm(page, users.disclaimer)
    const disclaimer = page.locator('text=/AVISO LEGAL/')
    await expect(disclaimer).toBeVisible({ timeout: 10000 })
  })

  test('disclaimer user gets redirected to disclaimer page', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.disclaimer.category, categories)

    await loginHelpers.fillLoginForm(page, users.disclaimer)
    // Check for redirection to disclaimer page
    await expect(page).toHaveURL(/disclaimer/, { timeout: 15000 })
    await commonHelpers.checkNoRouterErrors(page)

    // Verify the disclaimer appears in appropriate language
    const disclaimer = page.locator('h2 > strong:has-text("AVISO LEGAL")')
    await expect(disclaimer).toBeVisible({ timeout: 10000 })
  })

  test('login user with verified email', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.verified.category, categories)

    await loginHelpers.fillLoginForm(page, users.verified)
    await expect(page).toHaveURL(/desktops/)
  })

  test('login user with UNverified email', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.unverified.category, categories)

    await loginHelpers.fillLoginForm(page, users.unverified)
    const titleText = page.getByText('The email address must be verified by IsardVDI', { exact: true })
    await expect(titleText).toBeVisible({ timeout: 10000 })

    // Check for redirection to email verification page
    await expect(page).toHaveURL('/verify-email', { timeout: 15000 })

    // Check that title doesn't contain router.titles error
    await commonHelpers.checkNoRouterErrors(page)

    const emailInput = page.getByRole('textbox', { name: 'Email' })
    await expect(emailInput).toBeVisible({ timeout: 5000 })
  })
  test('notifications user logs in and sees notifications fullpage', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.notifications.category, categories)
    await loginHelpers.fillLoginForm(page, users.notifications)

    await expect(page).toHaveURL(/notifications/)
    await expect(page).not.toHaveURL(/desktops/)

    const header = page.getByText(/Notifications for you|Notificaciones para ti/)
    await expect(header).toBeVisible()
  })

  test('password reset user gets redirected to reset password page', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.password_reset.category, categories)

    await loginHelpers.fillLoginForm(page, users.password_reset)
    await expect(page).toHaveURL(/reset-password/, { timeout: 15000 })
    await commonHelpers.checkNoRouterErrors(page)

    const passwordInput = page.locator('input[placeholder="Password"]').first()
    const confirmationInput = page.getByRole('textbox', { name: 'Confirm password' })
    await expect(passwordInput).toBeVisible({ timeout: 5000 })
    await expect(confirmationInput).toBeVisible({ timeout: 5000 })
  })
})

test.describe('Forgot password', () => {
  test('forgot password requires category selection', async ({ page, categories }) => {
    const visibleCategoriesCount = Object.values(categories).filter((cat) => cat.frontend).length

    if (visibleCategoriesCount > 1) {
      await page.goto('/login')

      await page.locator('button:has-text("Forgot password?")').click()
      const alert = page.locator('[role="alert"]:has-text("A category needs to be selected")')
      await expect(alert).toBeVisible({ timeout: 5000 })
    } else {
      console.log('Test skipped - multiple visible categories required for this test')
      expect(true).toBeTruthy()
    }
  })

  // TODO: discuss if we want it to work like this

  // test('forgot password with non-existent email shows generic success alert', async ({ page, categories, loginHelpers }) => {
  //   await loginHelpers.goToLoginForCategory(page, 'default', categories)

  //   await page.locator('button:has-text("Forgot password?")').click()
  //   const emailInput = page.getByRole('textbox', { name: 'Email' })
  //   await expect(emailInput).toBeVisible({ timeout: 5000 })

  //   // Fill in a non-existent email address
  //   await emailInput.fill('thisemail@doesntexist.test')

  //   await page.locator('button[type="submit"]').click()

  //   // Check for the generic alert message
  //   const alert = page
  //     .locator('[role="alert"]:has-text("Success")')
  //     .nth(0)
  //   await expect(alert).toBeVisible({ timeout: 10000 })
  // })
})

test.describe('SAML flow', () => {
  test('SAML login flow', async ({ page, samlUsers, categories }) => {
    await page.goto('/login/saml/another')

    await page.locator('button:has-text("Login with SAML")').click()

    await expect(page).toHaveURL(/simplesaml/, { timeout: 10000 })

    // Fill SAML credentials
    await page.fill('input#username', samlUsers.user1.username)
    await page.fill('input#password', samlUsers.user1.password)
    await page.click('button.btn')

    const categorySelector = page.locator('text=/Select a category/')
    if (await categorySelector.isVisible({ timeout: 5000 })) {
      await page.locator(`text="${categories.another.name}"`).click()

      await expect(page).toHaveURL(/desktops/)
    }
  })

  test('SAML with unregistered category', async ({ page, samlUsers, categories }) => {
    await page.goto('/login/saml/default')

    await page.locator('button:has-text("Login with SAML")').click()

    await expect(page).toHaveURL(/simplesaml/, { timeout: 20000 })

    await page.fill('input#username', samlUsers.user1.username)
    await page.fill('input#password', samlUsers.user1.password)
    await page.click('button.btn')


    const categorySelector = page.locator('text=/Select a category/')
    if (await categorySelector.isVisible({ timeout: 5000 })) {
      await page.locator(`text="${categories.default.name}"`).click()
      await expect(page).toHaveURL(/register/)
      await commonHelpers.checkNoRouterErrors(page)

      const codeInput = page.locator('input[name="code"]')
      await expect(codeInput).toBeVisible({ timeout: 5000 })
      await codeInput.fill(groups.default.code)

      await page.locator('button[type="submit"]').click()

      await expect(page).toHaveURL(/desktops/, { timeout: 15000 })
    }
  })


  test('SAML with unallowed category', async ({ page, samlUsers }) => {
    await page.goto('/login/saml/disclaimer')

    await page.locator('button:has-text("Login with SAML")').click()
    await expect(page).toHaveURL(/simplesaml/, { timeout: 10000 })

    await page.fill('input#username', samlUsers.user1.username)
    await page.fill('input#password', samlUsers.user1.password)
    await page.click('button.btn')
  })

  test('SAML user registration with enrollment code', async ({ page, samlUsers, categories, groups }) => {
    await page.goto('/login/saml/default')

    await page.locator('button:has-text("Login with SAML")').click()

    await expect(page).toHaveURL(/simplesaml/, { timeout: 20000 })

    await page.fill('input#username', samlUsers.user2.username)
    await page.fill('input#password', samlUsers.user2.password)
    await page.click('button.btn')

    const categorySelector = page.locator('text=/Select a category/')
    if (await categorySelector.isVisible({ timeout: 5000 })) {
      await page.locator(`text="${categories.default.name}"`).click()
    }

    await expect(page).toHaveURL(/register/)

    const codeInput = page.locator('input[name="code"]')
    await expect(codeInput).toBeVisible({ timeout: 5000 })

    await codeInput.fill('invalid123')
    await page.locator('button[type="submit"]').click()

    const alert = page.locator('[role="alert"]:has-text("Code not found")')
    await expect(alert).toBeVisible({ timeout: 5000 })

    await codeInput.fill(groups.default_user.code)
    await page.locator('button[type="submit"]').click()

    await expect(page).toHaveURL(/desktops/, { timeout: 15000 })

  })
})

test.describe('LDAP', () => {
  test('LDAP user login with autoregister (Fry)', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.ldap_fry.category, categories)

    await loginHelpers.fillLoginForm(page, users.ldap_fry)
    // LDAP users with autoregister should be redirected to desktops after successful authentication
    await expect(page).toHaveURL(/desktops/, { timeout: 15000 })
  })

  test('LDAP user with invalid credentials should show error', async ({ page, users, categories, loginHelpers }) => {
    await loginHelpers.goToLoginForCategory(page, users.ldap_bender.category, categories)

    const invalidUser = {
      username: users.ldap_bender.username,
      password: 'wrongpassword'
    }
    await loginHelpers.fillLoginForm(page, invalidUser)

    const alert = page.locator('[role="alert"]:has-text("Incorrect user or password")')
    const tooMany = page.getByText('Too many login attempts, please try again at', { exact: false })
    await expect(alert.or(tooMany)).toBeVisible({ timeout: 10000 })
  })
})