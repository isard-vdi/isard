import { test, expect } from '../fixtures/login.js'
import { commonHelpers } from '../fixtures/common.js'

// Smoke coverage for the Vue 3 /vw/:token route, served by
// DirectViewerView.vue. The route is `meta.public: true` — no JWT
// required; access is gated by the token in the URL.
//
// What we pin (single-page level — does NOT cover the actual viewer
// streams):
//   1. Route resolves without router-title fallback even for an
//      invalid token (the view renders an error Alert in that case)
//   2. With a clearly invalid token, an error message is rendered
//      (not a blank page or a router crash)
//   3. The route is accessible WITHOUT login (public meta) — pin so a
//      future auth-guard regression that makes /vw/* require a JWT
//      breaks loud here
//
// Coverage of the actual viewer-button rendering, reset modal, RDP/
// SPICE help modals, etc. requires a valid direct-viewer token. The
// component-level Vue 3 spec (DirectViewerView.spec.ts) handles those
// with mocked queries; e2e is deliberately scoped to the route gate.

const INVALID_TOKEN = '00000000-0000-4000-8000-000000000000'
const DIRECT_VIEWER_URL = `/vw/${INVALID_TOKEN}`

test.describe('Vue 3 Direct Viewer view (public route)', () => {
  test('route is reachable WITHOUT login', async ({ page }) => {
    // No loginHelpers.login() call — pin that the public meta works.
    // A future regression that adds a router guard requiring a JWT
    // would redirect to /login and fail this assertion.
    await page.goto(DIRECT_VIEWER_URL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    expect(page.url()).toContain(`/vw/${INVALID_TOKEN}`)
    expect(page.url()).not.toMatch(/\/login(\/|$|\?)/)
  })

  test('loads without router errors', async ({ page }) => {
    await page.goto(DIRECT_VIEWER_URL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })
    await commonHelpers.checkNoRouterErrors(page)
  })

  test('invalid token surfaces an error alert (not a blank page)', async ({
    page,
  }) => {
    await page.goto(DIRECT_VIEWER_URL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })

    // The view branches: skeleton while pending, then either viewer
    // buttons (token valid) or an error Alert (token invalid). For an
    // obviously bogus UUID the apiv4 /item/desktop/token/{token}/
    // get-viewer endpoint 404s, the query goes into error state, and
    // the Alert renders.
    const alert = page.locator('[role="alert"], .alert, .Alert').first()
    const errorText = page.getByText(
      /not.found|invalid|expired|no.encontrad|invàlid/i,
    )
    const someErrorVisible = await Promise.race([
      alert.isVisible({ timeout: 10000 }).catch(() => false),
      errorText
        .first()
        .isVisible({ timeout: 10000 })
        .catch(() => false),
    ])
    expect(
      someErrorVisible,
      'Expected an error alert/message for invalid token, got blank page',
    ).toBe(true)
  })
})
