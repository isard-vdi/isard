// @ts-check
//
// Vue 2 recycle bin smoke. `/recycleBins` is the listing view; the
// per-item detail at `/recyclebin/:id` needs a seeded recycle entry
// and is skipped here.

import { expect } from '@playwright/test'
import { test } from './login-page'

test.describe('Vue 2 recycle bin', () => {
  test('/recycleBins list page loads', async ({ page, login }) => {
    const response = await page.goto('/recycleBins')
    if (response) expect(response.status()).toBeLessThan(400)

    await expect(page.locator('#content')).toBeVisible()

    const body = (await page.textContent('body')) ?? ''
    expect(body).not.toMatch(/views\.recycle-bin\./)
  })

  test('/recycleBins shows either entries or an empty-state shell', async ({ page, login }) => {
    await page.goto('/recycleBins')
    await page.waitForLoadState('networkidle')

    const hasTable = await page
      .locator('table, [role="table"]')
      .first()
      .isVisible({ timeout: 5000 })
      .catch(() => false)
    const hasContent = await page.locator('#content').isVisible()
    // Either a table appears or the container just renders empty — both
    // are fine, but the container itself must be there.
    expect(hasTable || hasContent).toBeTruthy()
  })
})
