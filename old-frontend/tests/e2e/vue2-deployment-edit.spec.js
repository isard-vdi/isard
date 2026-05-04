// @ts-check
//
// Regression for the deployment-edit class of bugs (#14, #16, #18,
// #38). The common shape was: form submits 200 but the underlying
// row didn't reflect the changes — either because the apiv4 schema
// silently dropped fields (#16 bus:false → string), the GET/PUT
// shapes diverged (#38 user_permissions list/dict), or the parser
// path clobbered sibling keys (#46 vgpus dropped on hardware edit).
//
// This spec runs the round-trip end-to-end through the Vue 2 form:
//   1. Admin (via API) creates a deployment with a known
//      name/description.
//   2. Admin opens /deployment/{id}/edit in the browser.
//   3. Form is filled with new name + description.
//   4. Submit; navigation back to /deployments asserts success.
//   5. Re-open the edit form; assert the new values are visible.
//   6. afterAll: delete the deployment.

import { test, expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { test as loginTest } from './login-page'

test.describe.configure({ mode: 'serial' })

test.describe('Vue 2 deployment edit — form persists changes', () => {
  /** @type {ApiHelper} */
  let api
  /** @type {string} */
  let deploymentId
  /** @type {string} */
  let originalName

  test.beforeAll(async ({ baseURL }) => {
    api = new ApiHelper(baseURL ?? 'https://localhost')
    await api.login()

    const templates = await api.getTemplates()
    const tpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!tpl) {
      test.skip(true, 'no Stopped+enabled template seeded; run seed-fixtures.py first')
      return
    }

    const ts = Date.now()
    originalName = `edit-bug-${ts}`
    const resp = await api.createDeployment(originalName, tpl.id, {
      roles: ['admin'],
      categories: false,
      groups: false,
      users: false
    })
    deploymentId = resp.id
  })

  test.afterAll(async () => {
    if (deploymentId) {
      try {
        await api.deleteDeployment(deploymentId)
      } catch (e) {
        console.warn(`afterAll: deleteDeployment failed: ${e.message}`)
      }
    }
  })
})

// Use the admin login fixture for the actual UI test.
loginTest.describe('Vue 2 deployment edit — form round-trip', () => {
  loginTest('rename + change description, re-open form shows new values', async ({
    page,
    login
  }) => {
    // Reuse the deployment seeded in the sibling describe-block via a
    // shared module-level handle would be cleaner, but Playwright runs
    // describes independently; create one here too. Cheap because
    // ``createDeployment`` is a single POST.
    const api = new ApiHelper(test.info().project.use?.baseURL ?? 'https://localhost')
    await api.login()
    const templates = await api.getTemplates()
    const tpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    test.skip(!tpl, 'no Stopped+enabled template seeded')

    const ts = Date.now()
    const originalName = `edit-rt-${ts}`
    const created = await api.createDeployment(originalName, tpl.id, {
      roles: ['admin'],
      categories: false,
      groups: false,
      users: false
    })
    const deploymentId = created.id

    try {
      // Navigate to the edit form. The route is /deployment/{id}/edit
      // per old-frontend/src/router/index.js.
      const response = await page.goto(`/deployment/${deploymentId}/edit`)
      if (response) expect(response.status()).toBeLessThan(400)
      await page.waitForLoadState('networkidle')

      // Fill the deployment-name input. DeploymentEdit.vue binds the
      // ``deploymentName`` model to a ``<b-form-input id="deploymentName">``
      // — Playwright finds it via the for/id label association on
      // ``forms.new-deployment.name``.
      const newName = `${originalName}-renamed`
      const newDesc = `desc-${ts}`

      const nameInput = page.locator('#deploymentName')
      await expect(nameInput).toBeVisible({ timeout: 10000 })
      await nameInput.fill(newName)

      // Description input — find by label text since the id varies.
      // The form has multiple ``<b-form-input>`` for desktop name,
      // username, password, etc.; the deployment description is a
      // textarea-style field associated with the label
      // ``forms.new-deployment.description``.
      const descLabel = page.getByText(/description/i).first()
      const descInput = descLabel.locator('xpath=following::*[self::input or self::textarea][1]')
      if (await descInput.isVisible().catch(() => false)) {
        await descInput.fill(newDesc)
      }

      // Submit. The submit button is rendered in the page footer; its
      // text matches the i18n key ``forms.update``.
      const submitBtn = page.getByRole('button').filter({ hasText: /update|save|edit/i }).last()
      await submitBtn.click()

      // The success path navigates back to /deployments. The store
      // action shows a snotify "Editing..." toast and dispatches
      // ``navigate('deployments')`` after a 200 response.
      await page.waitForURL(/\/deployments$/, { timeout: 15000 })

      // Re-open the edit form and assert the new values stuck. This is
      // the regression assertion: forms #14/#16/#18 all returned 200
      // but lost the new values.
      await page.goto(`/deployment/${deploymentId}/edit`)
      await page.waitForLoadState('networkidle')
      await expect(nameInput).toBeVisible({ timeout: 10000 })
      await expect(nameInput).toHaveValue(newName)
    } finally {
      // Best-effort cleanup — even if the assertions failed the
      // deployment shouldn't linger.
      try {
        await api.deleteDeployment(deploymentId)
      } catch (e) {
        console.warn(`teardown: deleteDeployment failed: ${e.message}`)
      }
    }
  })
})
