import { expect } from '@playwright/test'

const commonHelpers = {
  async checkNoRouterErrors(page) {
    const pageTitle = await page.title()
    expect(pageTitle).not.toContain('router.titles')
  },
}

// Bridge a Vue 3 login session into the Flask webapp's flask-login so that
// `/isard-admin/*` endpoints see an authenticated user. Vue 3's
// LoginView.vue fires this same POST on login success, but the fetch is
// async and not awaited in `loginHelpers.login`, so protected admin routes
// hit a race. We repeat the POST from inside the browser context (so
// cookies land in the page's jar, not a detached API context) and wait
// for the `{success: true}` body.
//
// The Flask bridge reads a Bearer token from the Authorization header
// (not from a cookie). Vue 3 stores the JWT in the `authorization` /
// `isardvdi_session` cookie — these are HttpOnly so `document.cookie`
// can't see them; read via Playwright's context API which has raw access,
// then pass through as an explicit header.
async function bridgeAdminSession(page) {
  const ctx = page.context()
  const cookies = await ctx.cookies()
  const jwtCookie = cookies.find(
    (c) => c.name === 'authorization' || c.name === 'isardvdi_session',
  )
  if (!jwtCookie) {
    throw new Error(
      `admin session bridge: no JWT cookie on context (have: ${cookies
        .map((c) => c.name)
        .join(', ')})`,
    )
  }
  const bearer = jwtCookie.value.replace(/^Bearer\s+/i, '')

  const response = await page.request.post('/isard-admin/login', {
    headers: { Authorization: 'Bearer ' + bearer },
  })
  if (!response.ok()) {
    throw new Error(
      `admin session bridge failed: status=${response.status()} ${response.statusText()}`,
    )
  }
  const body = await response.json().catch(() => null)
  if (!body || !body.success) {
    throw new Error(`admin session bridge: no success body (got ${JSON.stringify(body)})`)
  }
}

export { commonHelpers, bridgeAdminSession }
