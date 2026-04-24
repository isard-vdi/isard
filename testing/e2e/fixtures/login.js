import { test as base } from '@playwright/test'

// User data for testing, extracted from the testing database for e2e tests.
// Admin credentials can be overridden via E2E_ADMIN_USERNAME / E2E_ADMIN_PASSWORD
// so the same specs run against a seeded CI DB (admin/IsardVDI) or a dev DB
// with a different admin password (e.g. the value of WEBAPP_ADMIN_PWD).
const users = {
  admin: {
    username: process.env.E2E_ADMIN_USERNAME || 'admin',
    password: process.env.E2E_ADMIN_PASSWORD || 'IsardVDI',
    category: 'default',
  },
  user01: { username: 'user01', password: 'a?)49hgT', category: 'default' },
  manager01: { username: 'manager01', password: 'LB`*F9Uw', category: 'default' },
  disabled: { username: 'disabled', password: '6S/<d`,+', category: 'default' },
  user02: { username: 'user02', password: 'xu[CN_Fv', category: 'hidden' },
  manager02: { username: 'manager02', password: 'LxlE5sp`', category: 'hidden' },
  user03: { username: 'user03', password: '|bQ(,,e6', category: 'another' },
  manager03: { username: 'manager03', password: ">/Nq'&r9", category: 'another' },
  verified: { username: 'verified', password: '7!#eNF0¿', category: 'email' },
  unverified: { username: 'unverified', password: '$1~!Vl%p', category: 'email' },
  maintenance: { username: 'maintenance', password: '9&tJe2#s', category: 'maintenance' },
  disclaimer: { username: 'disclaimer', password: '5%4hdP!W', category: 'disclaimer' },
  toomanyattempts: { username: 'toomanyattempts', password: 'doesntexist', category: 'default' },
  doesntexist: { username: 'thisuser', password: 'doesntexist', category: 'default' }, // not in the database
  admin_maintenance: {
    username: 'admin_maintenance',
    password: '&Jd9qW?e',
    category: 'maintenance',
  },
  notifications: { username: 'notifications', password: '3x!9T&kL', category: 'notifications' },
  password_reset: { username: 'password_reset', password: 'jh&s90v#', category: 'password_reset' },

  // E2E admin users - one per test to avoid session conflicts with parallel workers
  admin_e2e_01: { username: 'admin_e2e_01', password: 'IsardTest1!', category: 'default' },
  admin_e2e_02: { username: 'admin_e2e_02', password: 'IsardTest1!', category: 'default' },
  admin_e2e_03: { username: 'admin_e2e_03', password: 'IsardTest1!', category: 'default' },
  admin_e2e_04: { username: 'admin_e2e_04', password: 'IsardTest1!', category: 'default' },
  admin_e2e_05: { username: 'admin_e2e_05', password: 'IsardTest1!', category: 'default' },
  admin_e2e_06: { username: 'admin_e2e_06', password: 'IsardTest1!', category: 'default' },
  admin_e2e_07: { username: 'admin_e2e_07', password: 'IsardTest1!', category: 'default' },
  admin_e2e_08: { username: 'admin_e2e_08', password: 'IsardTest1!', category: 'default' },
  admin_e2e_09: { username: 'admin_e2e_09', password: 'IsardTest1!', category: 'default' },
  admin_e2e_10: { username: 'admin_e2e_10', password: 'IsardTest1!', category: 'default' },
  admin_e2e_11: { username: 'admin_e2e_11', password: 'IsardTest1!', category: 'default' },
  admin_e2e_12: { username: 'admin_e2e_12', password: 'IsardTest1!', category: 'default' },
  admin_e2e_13: { username: 'admin_e2e_13', password: 'IsardTest1!', category: 'default' },
  admin_e2e_14: { username: 'admin_e2e_14', password: 'IsardTest1!', category: 'default' },
  admin_e2e_15: { username: 'admin_e2e_15', password: 'IsardTest1!', category: 'default' },

  // E2E user (non-admin) for tests requiring role=user
  user_e2e_01: { username: 'user_e2e_01', password: 'IsardTest1!', category: 'default' },

  // LDAP test users (from planetexpress.com test server)
  ldap_fry: { username: 'fry', password: 'fry', category: 'default' },
  ldap_leela: { username: 'leela', password: 'leela', category: 'default' },
  ldap_bender: { username: 'bender', password: 'bender', category: 'default' },
  ldap_professor: { username: 'professor', password: 'professor', category: 'default' },
  ldap_hermes: { username: 'hermes', password: 'hermes', category: 'default' },
  ldap_zoidberg: { username: 'zoidberg', password: 'zoidberg', category: 'default' },
  ldap_amy: { username: 'amy', password: 'amy', category: 'default' },
}

// SAML test user data for logging in via SAML
const samlUsers = {
  user1: { username: 'user1', password: 'user1pass', categories: ['default', 'another'] },
  user2: { username: 'user2', password: 'user2pass', categories: ['default', 'another'] },
}

// Group codes for registration
const groups = {
  saml_another_advanced: { code: '6x820h', category: 'another', role: 'advanced', name: 'SAML' },
  default_user: { code: 'bj7i32', category: 'default', role: 'user', name: 'Default' }
}

// Categories configuration for login tests
const categories = {
  default: { id: 'default', name: 'Default', url: 'default', frontend: true, maintenance: false },
  disclaimer: {
    id: '4f0408cc-4fd8-4d33-8173-f23f24d79cc3',
    name: 'Disclaimer',
    url: 'disclaimer',
    frontend: false,
    maintenance: false,
  },
  hidden: {
    id: '07962917-9649-436e-b103-559c36c04afd',
    name: 'Hidden',
    url: 'hidden',
    frontend: false,
    maintenance: false,
  },
  email: {
    id: '5389a10b-8509-4b62-b94e-674dfcb372d8',
    name: 'Email',
    url: 'email',
    frontend: false,
    maintenance: false,
  },
  another: {
    id: 'ae26368b-26d3-4692-ba2f-62e99ceb054e',
    name: 'Another category',
    url: 'another',
    frontend: true,
    maintenance: false,
  },
  maintenance: {
    id: '99beca35-1d46-41d8-8319-8cc54dbe3db0',
    name: 'Maintenance',
    url: 'maintenance',
    frontend: true,
    maintenance: true,
  },
  notifications: {
    id: '0efd17b5-2cc6-4f72-bbe1-18958d5b6c73',
    name: 'Notifications',
    url: 'notifications',
    frontend: false,
    maintenance: false,
  },
  password_reset: {
    id: '0519250f-e376-48c4-9609-fdae7d54a353',
    name: 'Password Reset',
    url: 'password_reset',
    frontend: false,
    maintenance: false,
  },
}

const loginHelpers = {
  async goToLoginForCategory(page, categoryKey, categories) {
    const category = categories[categoryKey]

    // If category is hidden (frontend=false), always use direct URL
    if (!category.frontend) {
      await page.goto(`/login/all/${category.url}`)
      return
    }
    // For visible categories (frontend=true), go to main login page and select it from the dropdown
    await page.goto('/login')

    // The dropdown only renders when the backend exposes more than one
    // frontend-visible category, so detect it in the DOM instead of relying
    // on the fixture's hardcoded count.
    const categorySelector = page.locator('[role="combobox"]:has-text("Select a category")').first()
    const selectorVisible = await categorySelector
      .waitFor({ state: 'visible', timeout: 2000 })
      .then(() => true)
      .catch(() => false)
    if (selectorVisible) {
      await categorySelector.click()
      await page.waitForTimeout(500)

      const option = page.locator(`[role="option"]:has-text("${category.name}"), li:has-text("${category.name}")`).first()
      await option.waitFor({ state: 'visible', timeout: 5000 })
      await option.click()
      await page.waitForTimeout(500)
    }
  },

  async fillLoginForm(page, user, options = { submit: true }) {
    // Try form-input selectors in priority order and fall back to the
    // accessibility tree. Vue 3's old InputField wrapper dropped the name
    // attribute (fixed on this branch); the role-based fallback keeps the
    // fixture working against both old and current frontend builds.
    const username = page.getByRole('textbox', { name: /^username$/i }).first()
    const password = page.locator('input[type="password"]').first()

    await username.waitFor({ state: 'visible', timeout: 10000 })
    await username.fill(user.username)
    await password.fill(user.password)
    if (options.submit) {
      // Name matches both "Login" (Vue 3) and "Log in" (Vue 2 old-frontend)
      const submit = page.getByRole('button', { name: /^log ?in$/i }).first()
      await submit.click()
    }
  },

  async login(page, user, categories, redirectPath = null) {
    const category = categories[user.category]

    if (!category.frontend) {
      await page.goto(`/login/all/${category.url}`)
    } else {
      await page.goto('/login')

      // Only probe the dropdown if it's actually rendered — backend may expose
      // a single category, in which case the selector is omitted entirely.
      const categorySelector = page.locator('div[role="combobox"], button:has-text("Select a category")').first()
      const selectorVisible = await categorySelector
        .waitFor({ state: 'visible', timeout: 2000 })
        .then(() => true)
        .catch(() => false)
      if (selectorVisible) {
        await categorySelector.click()
        await page.waitForTimeout(500)
        await page.locator(`li:has-text("${category.name}"), div:has-text("${category.name}")`).first().click()
      }
    }
    await this.fillLoginForm(page, user)

    // The frontend submits the login POST, sets the auth cookie, then does
    // window.location.pathname = '/'. Wait for that to settle before the
    // caller navigates — going to a protected route with a pending login
    // bounces back to /login.
    let urlSettled = true
    await page
      .waitForURL((u) => !/\/login(\/|$|\?)/.test(u.toString()), { timeout: 15000 })
      .catch(() => { urlSettled = false })

    // Under -j 4 the JWT cookie write races with the redirect; downstream
    // helpers (e.g. webapp-admin bridgeAdminSession) read cookies straight
    // away and intermittently see an empty jar. Poll the playwright context
    // cookie jar until the auth cookie is committed before returning.
    // 80 * 250ms = 20s — generous because under heavy parallel load the
    // apiv4 login POST has been observed to take >10s to complete.
    const ctx = page.context()
    let cookieFound = false
    let lastCookieNames = ''
    for (let i = 0; i < 80; i += 1) {
      const cookies = await ctx.cookies()
      lastCookieNames = cookies.map((c) => c.name).join(',')
      if (cookies.find((c) => c.name === 'authorization' || c.name === 'isardvdi_session')) {
        cookieFound = true
        break
      }
      await page.waitForTimeout(250)
    }
    if (!cookieFound) {
      // Surface the failure here instead of letting it cascade as a
      // cryptic "no JWT cookie on context" downstream — the upstream
      // cause is the login itself, not the helper that reads the jar.
      throw new Error(
        `login: JWT cookie did not appear within 20s for user=${user.username} ` +
          `(urlSettled=${urlSettled}, currentURL=${page.url()}, cookies=[${lastCookieNames}])`,
      )
    }

    if (redirectPath) {
      await page.goto(redirectPath)
      await page.waitForLoadState('networkidle')
    } else {
      await page.waitForTimeout(500)
    }
  },

  async loginAsAdmin(page, categories, redirectPath = null) {
    await this.login(page, users.admin, categories, redirectPath)
  }
}

export const test = base.extend({
  users: async ({ }, use) => {
    await use(users)
  },

  samlUsers: async ({ }, use) => {
    await use(samlUsers)
  },

  categories: async ({ }, use) => {
    await use(categories)
  },

  groups: async ({ }, use) => {
    await use(groups)
  },

  loginHelpers: async ({ }, use) => {
    await use(loginHelpers)
  },

  // Returns admin_e2e_NN keyed by the playwright worker index, so each
  // parallel worker logs in as a distinct admin account. The shared
  // `users.admin` contends on Redis session state under -j 4 and the
  // login POST bounces back to /login with no cookies set; the
  // admin_e2e_01..15 accounts are seeded in the testing DB precisely
  // for per-worker isolation.
  adminPerWorker: async ({ }, use, testInfo) => {
    const idx = (testInfo.workerIndex % 15) + 1
    const key = `admin_e2e_${String(idx).padStart(2, '0')}`
    await use(users[key])
  },
})

export { expect } from '@playwright/test'
export { loginHelpers }
