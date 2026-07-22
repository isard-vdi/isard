// @ts-check
import { fixture as baseFixture } from './base'
import { test as base } from '@playwright/test'

export class PageLogin {
  /**
   * @param {import('@playwright/test').Page} page
   *
   * The login page is served by the Vue 3 frontend (`component/frontend/`).
   * After a successful POST the Vue 3 app sets the auth cookie, does a
   * `window.location = '/'`, and the router then lands the user on whichever
   * default their role permits (admins → Vue 2 `/desktops`, users → same).
   * Selectors below target the Vue 3 login DOM — role-based + type-based so
   * they survive the old-InputField-without-name-attribute branch and the
   * post-fix branch.
   */
  constructor (page) {
    this.page = page
    this.formInputs = {
      usr: page.getByRole('textbox', { name: /^username$/i }).first(),
      pwd: page.locator('input[type="password"]').first(),
      saml: page.getByRole('button', { name: /saml/i }),
      // Matches both "Login" (Vue 3) and "Log in" (legacy Vue 2 copy).
      login: page.getByRole('button', { name: /^log ?in$/i }).first()
    }
  }

  async goto () {
    await this.page.goto('/isard-admin/logout')
    await this.page.goto('/login/default')
    await this.formInputs.usr.waitFor({ state: 'visible', timeout: 10000 })
  }

  /**
   * @param {string} usr
   * @param {string} pwd
   */
  async form (usr, pwd) {
    await this.formInputs.usr.fill(usr)
    await this.formInputs.pwd.fill(pwd)
    await this.formInputs.login.click()
  }

  /**
   * @param {string} usr
   * @param {string} pwd
   */
  async saml (usr, pwd) {
    await this.formInputs.saml.click()

    await this.page.getByLabel('Username').fill(usr)
    await this.page.getByLabel('Password').fill(pwd)
    await this.page.getByRole('button', { name: 'Login' }).click()
  }

  async finished () {
    // Wait for ANY path outside `/login/*`. Admins may land on
    // `/isard-admin/admin/landing`, users on `/desktops`, maintenance users
    // on `/maintenance`. Pinning a specific URL here would re-introduce the
    // brittleness we hit when login moved to Vue 3.
    await this.page.waitForURL((u) => !/\/login(\/|$|\?)/.test(u.toString()), {
      timeout: 15000
    })
  }
}

// Each worker uses the admin from the pool created in
// ``global-setup.js`` so concurrent UI logins don't shadow each
// other's sessions. Falls back to the bootstrap admin when the
// pool isn't seeded (single-spec invocations).
const POOL_PASSWORD = process.env.E2E_ADMIN_POOL_PASSWORD ?? 'e2e_admin_pw'

export const fixture = {
  login: async ({ page }, use, testInfo) => {
    const login = new PageLogin(page)
    await login.goto()
    const poolUser = `e2e_admin_${testInfo.workerIndex}`
    try {
      await login.form(poolUser, POOL_PASSWORD)
      await login.finished()
    } catch (e) {
      // Re-arm: load /login afresh and try the bootstrap admin.
      await login.goto()
      await login.form(
        process.env.E2E_ADMIN_USERNAME ?? 'admin',
        process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI'
      )
      await login.finished()
    }

    await use(login)
  },
  ...baseFixture
}

export const test = base.extend(fixture)
