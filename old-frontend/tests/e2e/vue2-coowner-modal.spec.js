// @ts-check
//
// Regression for round-3 Bug #47 — co-owner deployment modal hides
// the "Update co-owners" footer button for non-owners.
//
// Before commit 382ef48ce, ``DeploymentModal.vue`` declared
// ``isOwner`` as a plain function. Vue evaluated ``v-if="isOwner"``
// against the function reference (always truthy in JavaScript), so
// the "Update co-owners" footer button was visible to every viewer
// of the modal — including co-owners. Clicking it as a non-owner
// got a 403 from the backend (server-side enforcement was correct)
// but the UX was misleading.
//
// The fix converted ``isOwner`` to ``computed`` and null-guarded
// ``getCoOwners.owner.id``. This spec pins it: log in as a
// co-owner, open the deployment co-owners modal, assert the
// "Update co-owners" footer button is hidden.
//
// Fixture: admin (via API) creates an advanced user + a deployment
// whose ``co_owners`` list contains that user. UI logs in as the
// co-owner and exercises the modal.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { PageLogin } from './login-page'
import { test } from './api-fixture'

// One serial describe block — the seeded user + deployment are
// shared across the test (and only assertion). Parallel runs would
// race on the user-name uniqueness check.
test.describe.configure({ mode: 'serial' })

test.describe('Bug #47 regression — co-owner cannot click Update co-owners', () => {
  /** @type {string} */
  let coownerUserId
  /** @type {string} */
  let coownerUsername
  const coownerPassword = 'coown1234'
  /** @type {string} */
  let deploymentId
  /** @type {string} */
  let deploymentName

  test.beforeAll(async ({ baseURL }) => {
    const seed = new ApiHelper(baseURL ?? 'https://localhost')
    await seed.login()

    // Find a Stopped+enabled template the deployment can be built
    // from. Bail out cleanly if the test stack hasn't seeded any —
    // the spec is a regression guard, not a stack-bring-up smoke.
    const templates = await seed.getTemplates()
    const tpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!tpl) {
      test.skip(true, 'no Stopped+enabled template seeded; run seed-fixtures.py first')
      return
    }

    // Create the co-owner user. Role ``advanced`` so they can see
    // /deployments at all. Unique suffix on the username so parallel
    // CI runs don't collide on the unique-username constraint.
    const ts = Date.now()
    coownerUsername = `coown_e2e_${ts}`
    const userResp = await seed.createUser(
      coownerUsername,
      'default',
      'default-default',
      'advanced',
      coownerPassword
    )
    coownerUserId = userResp.id

    // Deployment owned by admin, with the new user as a co-owner.
    // The ``allowed`` block grants the co-owner read access to the
    // deployment row itself; without it /deployments wouldn't list
    // it for them.
    deploymentName = `coown-bug47-${ts}`
    const depResp = await seed.createDeployment(
      deploymentName,
      tpl.id,
      {
        roles: false,
        categories: false,
        groups: false,
        users: [coownerUserId]
      },
      [coownerUserId]
    )
    deploymentId = depResp.id
  })

  test.afterAll(async ({ baseURL }) => {
    if (!deploymentId && !coownerUserId) return
    const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
    await cleanup.login()
    if (deploymentId) {
      try {
        await cleanup.deleteDeployment(deploymentId)
      } catch (e) {
        // Best-effort cleanup; the deployment may already be in the
        // recycle bin if a prior run trashed it.
        console.warn(`afterAll: deleteDeployment failed: ${e.message}`)
      }
    }
    if (coownerUserId) {
      try {
        await cleanup.deleteUser(coownerUserId)
      } catch (e) {
        console.warn(`afterAll: deleteUser failed: ${e.message}`)
      }
    }
  })

  test('Update co-owners footer button is hidden when viewer is a co-owner (not owner)', async ({
    page
  }) => {
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')

    // UI login as the co-owner. Reuses the existing PageLogin fixture
    // pattern but doesn't go through the admin-login fixture (we
    // need a specific non-admin user).
    const login = new PageLogin(page)
    await login.goto()
    await login.form(coownerUsername, coownerPassword)
    await login.finished()

    // Land on /deployments — this is where the co-owner sees the
    // shared deployment in their list. Advanced users default to
    // /desktops on login; navigate explicitly.
    await page.goto('/deployments')
    await page.waitForLoadState('networkidle')

    // Find the deployment row by its name. Vue 2 renders an
    // IsardTable wrapping a BootstrapVue ``b-table`` whose rows
    // expose role="row" — but if the row's accessible name doesn't
    // include the deployment text (icons inflate the name), fall
    // back to a text-based locator.
    let row = page.getByRole('row', { name: new RegExp(deploymentName) })
    if (!(await row.isVisible({ timeout: 10000 }).catch(() => false))) {
      row = page.locator('tr').filter({ hasText: deploymentName }).first()
    }
    if (!(await row.isVisible({ timeout: 5000 }).catch(() => false))) {
      test.skip(true, `co-owner did not see deployment row '${deploymentName}' on /deployments — listing scope or visibility config differs on this stack`)
      return
    }

    // The co-owners button is the green person-fill icon in the
    // actions column (Deployments.vue:50-59). Its ``title`` attr is
    // the i18n key resolution — match by title text.
    const coOwnersBtn = row.getByTitle(/co-?owners/i).first()
    await expect(coOwnersBtn).toBeVisible({ timeout: 5000 })
    await coOwnersBtn.click()

    // Modal opens with the DeploymentCoOwnersForm. The body shows
    // the warning alert "you can only view, not edit". Wait for the
    // modal title to confirm we're in the right state.
    const modal = page.locator('.modal.show').filter({
      hasText: /co-?owners/i
    })
    await expect(modal).toBeVisible({ timeout: 5000 })

    // The actual regression assertion: the footer ``Update
    // co-owners`` button must NOT be visible for a co-owner who is
    // not the owner. Before the fix, ``v-if="isOwner"`` evaluated
    // the function reference which is always truthy and the button
    // showed.
    //
    // The button's text comes from the i18n key
    // ``views.deployment.modal.confirmation.co-owners`` which
    // resolves to "Update co-owners" in en/es-ES (and equivalents
    // in eu/ca/pl). Match by role+name with a permissive regex.
    const updateBtn = modal
      .getByRole('button')
      .filter({ hasText: /update.*co-?owners|actualitzar.*copropietaris|actualizar.*copropietarios/i })
    await expect(
      updateBtn,
      'Update co-owners button must be hidden for non-owner co-owner viewer; ' +
        'isOwner is now a computed and v-if unwraps the value, so it returns ' +
        'false when getCoOwners.owner.id !== getUser.user_id.'
    ).toHaveCount(0)

    // The Cancel button MUST still be visible — the modal isn't
    // empty, the user can still close it. Sanity check on the
    // assertion above.
    const cancelBtn = modal.getByRole('button').filter({ hasText: /cancel|cancela/i })
    await expect(cancelBtn).toBeVisible()
  })
})
