// @ts-check
//
// /profile quota panel — renders user limits as bars without NaN.
//
// Profile.vue mounts ~12 QuotaProgressBar instances (desktops,
// templates, media, isos, vCPUs, memory, storage…). Each takes a
// ``value`` and a ``max``. Bug class: backend returns null/undefined
// for one of the limits and the bar renders NaN/0.
//
// This is a pure UI smoke — load /profile, scroll to the quota
// section, assert no "NaN" or undefined rendered text.

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 quota display', () => {
  test('/profile quota panel renders without NaN/undefined', async ({ page, login }) => {
    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    /** @type {{ url: string, status: number }[]} */
    const apiResponses = []
    page.on('response', (response) => {
      const url = response.url()
      if (/\/api\/v4\/user\/quota/.test(url)) {
        apiResponses.push({ url, status: response.status() })
      }
    })

    await page.goto('/profile')
    await page.waitForLoadState('networkidle')

    // No 5xx on the quota fetch.
    const errors = apiResponses.filter((r) => r.status >= 500)
    expect(errors, 'GET /user/quotas must not return 5xx').toEqual([])

    // Wait long enough for the QuotaProgressBar Vue components to
    // hydrate; backed by the user-quota request.
    await page.waitForTimeout(1500)

    const body = (await page.textContent('body')) ?? ''
    expect(
      body,
      'Profile must render the word "Quota" or limits-related label'
    ).toMatch(/quota|limit|usage|desktop|template|memory/i)
    expect(
      body,
      '/profile rendered NaN — quota fields must not be NaN'
    ).not.toMatch(/NaN/)
    expect(
      body,
      '/profile rendered "undefined" — quota field is missing from API response'
    ).not.toMatch(/\bundefined\b/)

    // Console clean.
    const realErrors = consoleErrors.filter(
      (e) =>
        !/Failed to load resource/.test(e) &&
        !/net::ERR_/.test(e) &&
        !/translation key/i.test(e)
    )
    expect(
      realErrors,
      `console errors on /profile: ${realErrors.join('\n')}`
    ).toEqual([])
  })
})
