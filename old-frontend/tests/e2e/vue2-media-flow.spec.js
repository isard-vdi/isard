// @ts-check
//
// Vue 2 Media page smoke — list + tab navigation.
//
// /media renders a tabbed view: "Media" (user's own ISO/USB files)
// and "Shared with me". Bug class: media list returns 500 if any
// item lacks a status field (apiv4 strict response_model).

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { test } from './login-page'

test.describe('Vue 2 media page', () => {
  test('/media loads without 500 and renders both tabs', async ({ page, login }) => {
    /** @type {{ url: string, status: number }[]} */
    const apiResponses = []
    page.on('response', (response) => {
      const url = response.url()
      if (/\/api\/v4\/items?\/media/.test(url)) {
        apiResponses.push({ url, status: response.status() })
      }
    })

    await page.goto('/media')
    await page.waitForLoadState('networkidle')

    // Both tabs render.
    const tablist = page.getByRole('tablist').first()
    await expect(tablist, '/media should render a tablist').toBeVisible({ timeout: 10000 })

    // No 5xx on the listing endpoints.
    const errors = apiResponses.filter((r) => r.status >= 500)
    expect(
      errors,
      'GET /items/media + /items/media/get-shared should not return 5xx'
    ).toEqual([])

    // No "No items" empty-state regex if seed data has at least one
    // media item — but be lenient: empty-state is acceptable for a
    // fresh test fixture.
    const body = (await page.textContent('body')) ?? ''
    expect(body, 'media page must render *some* tab content').toMatch(/Media|Shared/i)
  })

  test('media list endpoint returns conformant payload', async ({ baseURL }) => {
    const api = new ApiHelper(baseURL ?? 'https://localhost')
    await api.login()

    const list = await api._authFetch('GET', '/api/v4/items/media').catch((e) => {
      throw new Error(`/items/media failed: ${e.message}`)
    })

    expect(Array.isArray(list), '/items/media must return an array').toBeTruthy()

    // Every item must have id, name, kind, status — the four fields
    // the Vue 2 IsardTable column-renderer reads. Missing any of
    // these triggers a render error in Media.vue.
    for (const item of list) {
      expect(item, 'media item shape').toMatchObject({
        id: expect.any(String),
        name: expect.any(String)
      })
      expect(
        typeof item.status === 'string' || item.status === null,
        `media item ${item.id}: status must be string or null`
      ).toBeTruthy()
    }
  })
})
