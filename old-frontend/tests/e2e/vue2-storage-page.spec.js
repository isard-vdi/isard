// @ts-check
//
// /userstorage smoke — user-storage list with quota gauge + per-row
// percentages.
//
// Storage.vue renders an IsardTable bound to ``getStorage`` and a
// per-row QuotaProgressBar that divides ``actualSize`` by
// ``userQuota.totalSize``. Two regression vectors:
//   * apiv4 storage listing returns a 5xx (data shape mismatch).
//   * userQuota fetch returns null and the percentage column NaNs
//     out.

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 user storage page', () => {
  test('/userstorage loads and renders without errors', async ({ page, login }) => {
    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    /** @type {{ url: string, status: number }[]} */
    const apiResponses = []
    page.on('response', (response) => {
      const url = response.url()
      if (/\/api\/v4\/(items?\/storage|user\/quota)/.test(url)) {
        apiResponses.push({ url, status: response.status() })
      }
    })

    await page.goto('/userstorage')
    await page.waitForLoadState('networkidle')

    // Empty-state title or table either is acceptable.
    const body = (await page.textContent('body')) ?? ''
    expect(
      body,
      '/userstorage should render empty-state heading or storage table'
    ).toMatch(/storage|disk|GB|%/i)

    // No 5xx on storage or quota.
    const errors = apiResponses.filter((r) => r.status >= 500)
    expect(errors, 'storage / quota endpoints must not 5xx').toEqual([])

    // No NaN renders (the percentage column).
    expect(
      body,
      '/userstorage rendered "NaN%" — userQuota.totalSize is null/undefined'
    ).not.toMatch(/NaN/)

    // Console clean (filter network / asset noise).
    const realErrors = consoleErrors.filter(
      (e) => !/Failed to load resource/.test(e) && !/net::ERR_/.test(e)
    )
    expect(
      realErrors,
      `console errors on /userstorage: ${realErrors.join('\n')}`
    ).toEqual([])
  })
})
