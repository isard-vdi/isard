import { test, expect } from '../../fixtures/login.js'
import { commonHelpers } from '../../fixtures/common.js'

test.skip(true, 'Deprecated test, see specs/ for replacements')

// Smoke coverage for the Vue 3 /notifications/:trigger route, served
// by NotificationsView.vue. The route resolves the user's notification
// list for a given trigger (e.g. "login") in fullpage display mode.
//
// What we pin:
//   1. The route resolves without router-title fallback
//   2. The "Notifications" heading is visible
//   3. The "Go to desktops" escape button is present + functional
//   4. Either the notification list, an empty state, or an error
//      Alert renders — guards against a blank page

const NOTIFICATIONS_URL = '/notifications/login'

test.describe('Vue 3 Notifications view', () => {
  test.beforeEach(async ({ page, adminPerWorker, categories, loginHelpers }) => {
    await loginHelpers.login(page, adminPerWorker, categories, NOTIFICATIONS_URL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    expect(page.url()).toContain(NOTIFICATIONS_URL)
  })

  test('loads without router errors', async ({ page }) => {
    await commonHelpers.checkNoRouterErrors(page)
    expect(page.url()).toContain(NOTIFICATIONS_URL)
  })

  test('renders the Notifications heading', async ({ page }) => {
    const heading = page
      .getByRole('heading', { name: /notification|notificac|notificaci/i })
      .first()
    await expect(heading).toBeVisible({ timeout: 10000 })
  })

  test('go-to-desktops button navigates back', async ({ page }) => {
    const goToDesktops = page
      .getByRole('button', { name: /go.to.desktops|escriptori|escritorios/i })
      .first()
    await expect(goToDesktops).toBeVisible({ timeout: 10000 })
    await goToDesktops.click()
    // The handler does ``window.location.pathname = '/'`` — wait for
    // the SPA shell to land us somewhere outside the notifications
    // route.
    await page.waitForURL((u) => !u.toString().includes('/notifications/'), {
      timeout: 10000,
    })
    expect(page.url()).not.toContain('/notifications/')
  })

  test('renders either notification list, empty state, or error alert', async ({
    page,
  }) => {
    // The view branches on isPending / isError / data.notifications
    // length. Any of the three terminal states is valid for smoke
    // coverage; what we guard against is a blank page (none of them
    // visible).
    const empty = await page
      .getByText(/no.notifications|sense|sin notificac/i)
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false)
    const errorAlert = await page
      .locator('[role="alert"], .alert')
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false)
    const notificationList = await page
      .locator('main')
      .getByRole('region')
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false)

    expect(
      empty || errorAlert || notificationList,
      'Expected one of: empty state, error alert, or notification list',
    ).toBe(true)
  })
})
