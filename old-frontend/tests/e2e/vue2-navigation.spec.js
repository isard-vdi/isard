// @ts-check
//
// Vue 2 navigation smoke. Analogue of testing/e2e/tests/vue3-navigation.spec.js
// but against the live production Vue 2 user frontend at old-frontend/.
//
// Intent: log in once, visit every authenticated route, and assert:
//   1. no HTTP error page (status 4xx/5xx on the nav response)
//   2. no raw i18n-key leak in <title> (e.g. "router.desktops.title")
//   3. no Vue warning / uncaught console error
//
// Routes derived from old-frontend/src/router/index.js (2026-04-13).
//
// Admin credentials: uses the existing `PageLogin` fixture, which hardcodes
// admin/IsardVDI. When CI gets env-var support for Vue 2, thread
// E2E_ADMIN_USERNAME / E2E_ADMIN_PASSWORD here too.

import { expect } from '@playwright/test'
import { test } from './login-page'

const AUTHENTICATED_ROUTES = [
  { path: '/desktops', name: 'Desktops' },
  { path: '/desktops/new', name: 'New Desktop' },
  { path: '/templates', name: 'Templates' },
  { path: '/media', name: 'Media' },
  { path: '/deployments', name: 'Deployments' },
  { path: '/userstorage', name: 'User Storage' },
  { path: '/profile', name: 'Profile' },
  { path: '/planning', name: 'Planning' }
]

// Routes that should redirect unauthenticated visitors to /login.
const AUTH_GUARDED = ['/desktops', '/profile', '/deployments']

test.describe('Vue 2 navigation smoke', () => {
  for (const route of AUTHENTICATED_ROUTES) {
    test(`${route.path} loads without error`, async ({ page, login }) => {
      const consoleErrors = []
      page.on('console', (msg) => {
        if (msg.type() === 'error') consoleErrors.push(msg.text())
        if (msg.type() === 'warning' && /\[Vue warn\]/.test(msg.text())) {
          consoleErrors.push(msg.text())
        }
      })

      const response = await page.goto(route.path)
      // goto returns null for same-document nav; treat that as OK.
      if (response) {
        expect(response.status(), `nav status for ${route.path}`).toBeLessThan(400)
      }

      // i18n key must resolve — if `document.title` is literally
      // "router.<section>.title" then <head> is rendering the raw key.
      const title = await page.title()
      expect(title, `title for ${route.path}`).not.toMatch(/^router\./)

      // Fail the test on any Vue warn / console error logged during the load.
      // Ignore known network-origin noise that isn't a Vue bug.
      const realErrors = consoleErrors.filter(
        (e) => !/Failed to load resource/.test(e) && !/net::ERR_/.test(e)
      )
      expect(realErrors, `console errors on ${route.path}`).toEqual([])
    })
  }
})

test.describe('Vue 2 route guards', () => {
  for (const path of AUTH_GUARDED) {
    test(`${path} redirects to /login when unauthenticated`, async ({ page }) => {
      // Fresh context via explicit logout — skip the `login` fixture.
      await page.goto('/isard-admin/logout')
      await page.goto(path)
      await expect(page).toHaveURL(/\/login/)
    })
  }
})
