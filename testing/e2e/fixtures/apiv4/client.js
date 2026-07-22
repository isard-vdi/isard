// Bridges the generated apiv4 SDK to Playwright's per-context
// `request`, so the worker's authenticated Authorization header
// (set by loginHelpers.login) flows through transparently.

import { createClient, createConfig } from '../../src/gen/apiv4/client/index'
import { test as baseTest } from '../login.js'

// `new Request(url, init)` rejects relative URLs, so the SDK gets an
// absolute sentinel that the fetch shim strips before delegating to
// `request.fetch` (which honours playwright.config.ts baseURL).
const SDK_BASE_URL = 'http://playwright.local'

// Fetch spec: these statuses MUST NOT carry a body — `new Response(buf, {status})` throws.
const STATUS_NO_BODY = new Set([101, 103, 204, 205, 304])

function collectHeaders(h, into) {
  if (!h) return
  if (h instanceof Headers) h.forEach((v, k) => { into[k] = v })
  else if (Array.isArray(h)) for (const [k, v] of h) into[k] = v
  else if (typeof h === 'object') Object.assign(into, h)
}

function buildFetch(request) {
  return async (input, init = {}) => {
    const isRequest = typeof input !== 'string' && input != null && typeof input === 'object'
    let url = isRequest ? input.url : input
    if (url.startsWith(SDK_BASE_URL)) url = url.slice(SDK_BASE_URL.length)

    const method = (init.method || (isRequest && input.method) || 'GET').toUpperCase()
    const headers = {}
    if (isRequest) collectHeaders(input.headers, headers)
    collectHeaders(init.headers, headers)

    let body = init.body
    if (body == null && isRequest && method !== 'GET' && method !== 'HEAD') {
      try { body = await input.arrayBuffer() } catch { body = undefined }
    }

    const opts = { method, headers }
    if (body != null) opts.data = body instanceof ArrayBuffer ? Buffer.from(body) : body

    const resp = await request.fetch(url, opts)
    const status = resp.status()
    const bodyBuf = STATUS_NO_BODY.has(status) ? null : await resp.body()
    return new Response(bodyBuf, {
      status,
      statusText: resp.statusText(),
      headers: new Headers(resp.headers()),
    })
  }
}

/**
 * Create a typed apiv4 SDK client bound to a Playwright page. The
 * caller must already be logged in (auth headers come from the page's
 * context).
 *
 * @param {import('@playwright/test').Page} page
 */
export function apiv4ClientForPage(page) {
  return createClient(
    createConfig({ baseUrl: SDK_BASE_URL, fetch: buildFetch(page.request) }),
  )
}

export const test = baseTest.extend({
  apiv4: async ({ page }, use) => {
    await use(apiv4ClientForPage(page))
  },
  apiv4Admin: async ({ authenticatedPage }, use) => {
    await use(apiv4ClientForPage(authenticatedPage))
  },
  apiv4User: async ({ userE2EPage }, use) => {
    await use(apiv4ClientForPage(userE2EPage))
  },
  apiv4Advanced: async ({ advancedE2EPage }, use) => {
    await use(apiv4ClientForPage(advancedE2EPage))
  },
  apiv4Manager: async ({ managerE2EPage }, use) => {
    await use(apiv4ClientForPage(managerE2EPage))
  },
  apiv4QleManager: async ({ qle2eManagerPage }, use) => {
    await use(apiv4ClientForPage(qle2eManagerPage))
  },
})

export { expect } from '@playwright/test'
