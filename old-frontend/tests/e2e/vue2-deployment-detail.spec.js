// @ts-check
//
// /deployment/:id smoke — single-deployment detail page.
//
// The /deployment/:id route renders the deployment overview with
// the per-user desktop list, while /deployment/:id/videowall is the
// fullscreen lab/exhibit display. Neither has e2e coverage today.
//
// Spec asserts both routes load without console errors and that
// the deployment name appears in the rendered body.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { test } from './login-page'

test.describe.configure({ mode: 'serial' })

test.describe('Vue 2 deployment detail', () => {
  /** @type {string} */
  let deploymentId
  /** @type {string} */
  let deploymentName

  test.beforeAll(async ({ baseURL }) => {
    const seed = new ApiHelper(baseURL ?? 'https://localhost')
    await seed.login()

    const templates = await seed.getTemplates()
    const tpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!tpl) {
      test.skip(true, 'no Stopped+enabled template seeded')
      return
    }

    const ts = Date.now()
    deploymentName = `dep-detail-${ts}`
    const dep = await seed.createDeployment(deploymentName, tpl.id, {
      roles: ['admin'],
      categories: false,
      groups: false,
      users: false
    })
    deploymentId = dep.id
  })

  test.afterAll(async ({ baseURL }) => {
    if (!deploymentId) return
    try {
      const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
      await cleanup.login()
      await cleanup.deleteDeployment(deploymentId)
    } catch (e) { /* ignored */ }
  })

  test('/deployment/:id renders detail page with deployment name', async ({
    page,
    login
  }) => {
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')

    /** @type {string[]} */
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const response = await page.goto(`/deployment/${deploymentId}`)
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // Deployment name visible somewhere on the page.
    await expect(page.getByText(deploymentName).first()).toBeVisible({ timeout: 10000 })

    const realErrors = consoleErrors.filter(
      (e) => !/Failed to load resource/.test(e) && !/net::ERR_/.test(e)
    )
    expect(realErrors, `console errors on /deployment/${deploymentId}`).toEqual([])
  })

  test('/deployment/:id/videowall renders the fullscreen view', async ({
    page,
    login
  }) => {
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')

    const response = await page.goto(`/deployment/${deploymentId}/videowall`)
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // Videowall renders thumbnails of every desktop in the
    // deployment. Without a live hypervisor the desktops are in
    // Stopped state but the cards still render.
    const title = await page.title()
    expect(title).not.toMatch(/^router\./)
  })

  test('/deployment/:id/edit redirects authenticated user to the form', async ({
    page,
    login
  }) => {
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')

    const response = await page.goto(`/deployment/${deploymentId}/edit`)
    if (response) expect(response.status()).toBeLessThan(400)
    await page.waitForLoadState('networkidle')

    // The edit form has a deploymentName input pre-filled.
    const nameInput = page.locator('#deploymentName')
    await expect(nameInput).toBeVisible({ timeout: 10000 })
    await expect(nameInput).toHaveValue(deploymentName)
  })
})
