// @ts-check
//
// Deployment bastion — full-feature regression for the
// profile-ssh-key + deployment-bastion branch.
//
// Covers, end to end through the real browser + API:
//   * owner enables/disables the deployment bastion through the
//     StatusBar modal (two toggles + ports, no keys/domains UI)
//   * the per-desktop "Bastion info" row button opens the shared
//     BastionModal in READ-ONLY mode (no authorized-keys editor)
//   * the bastion CSV downloads from the StatusBar
//   * the profile "Bastion SSH key" modal saves a key
//   * profile keys are injected into the desktop's bastion target
//     at START: [desktop-owner, deployment-owner, co-owners…],
//     owner-first, deduped
//   * role gates: co-owner has full config access, a plain
//     deployment member gets 403 on every deployment-bastion route
//
// Env-gated: auto-skips when the stack has bastion disabled
// (BASTION_ENABLED env + config.bastion.enabled + alloweds), so the
// suite stays green on stacks without the bastion part.

import { expect } from '@playwright/test'
import { ApiHelper } from './helpers/api'
import { PageLogin } from './login-page'
import { test } from './base'

test.describe.configure({ mode: 'serial' })

const ADMIN_USER = process.env.E2E_ADMIN_USERNAME ?? 'admin'
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI'
const USER_PASSWORD = 'e2e_bastion_pw1'

// Real ed25519 public keys (no private halves anywhere) — the
// backend validates the key format, so these must parse.
const KEY_OWNER =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFI9C9z5YrOUf5jOfirX8SvH6X/1SODWp5cuvjPyzDTI e2eowner@bastion-e2e'
const KEY_CO =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIL85zXdvmmt9zpJMqkWEWGWVwi1WZpFyX2PmTKnhWO0n e2eco@bastion-e2e'
const KEY_MEMBER =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHZLXzsPyH+mwZQK70SIAQ3K9hGBoBJ2B86YyT/fAnfK e2emember@bastion-e2e'
const KEY_PROFILE =
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKPq68Fnz0vSVg7eSUgjrAoIPgT+kyGshR01cXE9BS0P e2eprofile@bastion-e2e'

test.describe('Vue 2 deployment bastion', () => {
  /** @type {boolean} */
  let bastionEnabled = false
  /** @type {string|null} */
  let deploymentId = null
  /** @type {string} */
  let deploymentName
  /** @type {string|null} */
  let memberDesktopId = null
  /** @type {string} */
  let memberUsername
  /** @type {string} */
  let coUsername
  /** @type {string} */
  let profileUsername
  /** @type {string[]} */
  const createdUserIds = []
  /** @type {ApiHelper} */
  let coApi
  /** @type {ApiHelper} */
  let memberApi

  const uiLogin = async (page, username, password) => {
    const login = new PageLogin(page)
    await login.goto()
    await login.form(username, password)
    await login.finished()
  }

  test.beforeAll(async ({ baseURL }) => {
    test.setTimeout(180000)
    const base = baseURL ?? 'https://localhost'
    const seed = new ApiHelper(base)
    await seed.login(ADMIN_USER, ADMIN_PASSWORD)

    // Env gate — bastion must be enabled (env + DB config + alloweds)
    // for any of the UI below to exist.
    const cfg = await seed._authFetch('GET', '/api/v4/item/user/get-config')
    bastionEnabled = cfg?.can_use_bastion === true
    if (!bastionEnabled) return

    const templates = await seed.getTemplates()
    const tpl = (templates || []).find(
      (t) => t.kind === 'template' && t.status === 'Stopped' && t.enabled
    )
    if (!tpl) return

    const ts = Date.now()
    coUsername = `e2e_bast_co_${ts}`
    memberUsername = `e2e_bast_m_${ts}`
    profileUsername = `e2e_bast_p_${ts}`
    const co = await seed.createUser(coUsername, 'default', 'default-default', 'advanced', USER_PASSWORD)
    const member = await seed.createUser(memberUsername, 'default', 'default-default', 'user', USER_PASSWORD)
    const profileUser = await seed.createUser(profileUsername, 'default', 'default-default', 'user', USER_PASSWORD)
    createdUserIds.push(co.id, member.id, profileUser.id)

    // Profile bastion SSH keys: deployment owner (admin), co-owner
    // and the member (= desktop owner). The profile user keeps no
    // key — the profile-modal test sets it through the UI.
    await seed._authFetch('PUT', '/api/v4/item/user/bastion-ssh-key', { ssh_key: KEY_OWNER })
    coApi = new ApiHelper(base)
    await coApi.loginAs(coUsername, USER_PASSWORD)
    await coApi._authFetch('PUT', '/api/v4/item/user/bastion-ssh-key', { ssh_key: KEY_CO })
    memberApi = new ApiHelper(base)
    await memberApi.loginAs(memberUsername, USER_PASSWORD)
    await memberApi._authFetch('PUT', '/api/v4/item/user/bastion-ssh-key', { ssh_key: KEY_MEMBER })

    deploymentName = `bast-e2e-${ts}`
    const dep = await seed.createDeployment(
      deploymentName,
      tpl.id,
      { users: [member.id] },
      [co.id]
    )
    deploymentId = dep.id

    // Wait for the member's deployment desktop to materialise.
    const deadline = Date.now() + 90000
    while (Date.now() < deadline && !memberDesktopId) {
      try {
        const resp = await memberApi._authFetch('GET', '/api/v4/items/desktops')
        const list = Array.isArray(resp) ? resp : resp?.desktops ?? []
        const found = list.find(
          (d) => d.name?.startsWith(`deploy-${deploymentName}`) && d.status === 'Stopped'
        )
        if (found) memberDesktopId = found.id
      } catch (e) { /* listing churn — keep polling */ }
      if (!memberDesktopId) await new Promise((resolve) => setTimeout(resolve, 2000))
    }
  })

  test.afterAll(async ({ baseURL }) => {
    try {
      const cleanup = new ApiHelper(baseURL ?? 'https://localhost')
      await cleanup.login(ADMIN_USER, ADMIN_PASSWORD)
      if (deploymentId) await cleanup.deleteDeployment(deploymentId)
      for (const id of createdUserIds) {
        await cleanup.deleteUser(id).catch(() => {})
      }
      // Drop the admin profile key the seed installed.
      await cleanup._authFetch('DELETE', '/api/v4/item/user/bastion-ssh-key').catch(() => {})
    } catch (e) { /* best-effort cleanup */ }
  })

  test('owner enables the deployment bastion through the statusbar modal', async ({ page }) => {
    test.skip(!bastionEnabled, 'bastion is not enabled on this stack')
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')
    test.skip(!memberDesktopId, 'deployment desktop did not reach Stopped')
    test.setTimeout(90000)

    await uiLogin(page, ADMIN_USER, ADMIN_PASSWORD)
    await page.goto(`/deployment/${deploymentId}`)
    await page.waitForLoadState('networkidle')

    // Opening the modal triggers a GET of the stored config; wait for
    // it so the form hydration can't race the toggle clicks below.
    const cfgLoaded = page.waitForResponse(
      (r) => r.url().includes(`/item/deployment/${deploymentId}/bastion`) && r.request().method() === 'GET',
      { timeout: 15000 }
    )
    await page.locator('button[title="Bastion configuration"]').click()
    await cfgLoaded
    // bootstrap-vue's custom switch hides the real <input>; clicking
    // the label is what flips the v-model (and what a user does).
    const sshSwitch = page.locator('#deploymentBastionSshEnabled')
    await expect(sshSwitch).toBeAttached({ timeout: 15000 })
    // Idempotent across retries: a previous attempt may have left a
    // toggle on already.
    const ensureOn = async (id) => {
      const input = page.locator(`#${id}`)
      if (!(await input.isChecked())) {
        await page.locator(`label[for="${id}"]`).click()
      }
      await expect(input).toBeChecked()
    }
    await ensureOn('deploymentBastionSshEnabled')
    await ensureOn('deploymentBastionHttpEnabled')
    // Port inputs appear once the toggles are on (defaults kept).
    await expect(page.locator('#deploymentBastionSshPort')).toHaveValue('22')
    // Saving flips the modal into its loading spinner while the PUT is
    // in flight (the switches detach immediately), so wait on the PUT
    // response itself — not on the spinner/modal DOM.
    const putDone = page.waitForResponse(
      (r) => r.url().includes(`/item/deployment/${deploymentId}/bastion`) && r.request().method() === 'PUT',
      { timeout: 15000 }
    )
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    expect((await putDone).status()).toBe(204)

    // The modal closes on a successful PUT.
    await expect(page.getByText(/Bastion configuration for/).first()).not.toBeVisible({ timeout: 15000 })

    // Backend state — asserted as the CO-OWNER (admin's API session
    // was shadowed by the UI login; co-owner passes owns_deployment_id).
    const depCfg = await coApi._authFetch('GET', `/api/v4/item/deployment/${deploymentId}/bastion`)
    expect(depCfg.ssh.enabled).toBe(true)
    expect(depCfg.http.enabled).toBe(true)
    // …and it was applied to the member's desktop target immediately.
    const target = await coApi._authFetch(
      'GET',
      `/api/v4/item/deployment/${deploymentId}/desktop/${memberDesktopId}/bastion`
    )
    expect(target.exists).toBe(true)
    expect(target.ssh.enabled).toBe(true)
    expect(target.http.enabled).toBe(true)
  })

  test('per-desktop row button opens the bastion modal in read-only mode', async ({ page }) => {
    test.skip(!bastionEnabled, 'bastion is not enabled on this stack')
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')
    test.skip(!memberDesktopId, 'deployment desktop did not reach Stopped')
    test.setTimeout(90000)

    const target = await coApi._authFetch(
      'GET',
      `/api/v4/item/deployment/${deploymentId}/desktop/${memberDesktopId}/bastion`
    )
    test.skip(!target?.exists, 'previous test did not enable the deployment bastion')

    await uiLogin(page, ADMIN_USER, ADMIN_PASSWORD)
    await page.goto(`/deployment/${deploymentId}`)
    await page.waitForLoadState('networkidle')

    // Two desktops exist (owner's + member's) — open the modal from
    // the MEMBER's row, since the assertions below use its target id.
    await page
      .locator('tr', { hasText: memberUsername })
      .locator('button[title="Bastion info"]')
      .click()

    // The shared BastionModal opens fed by the deployment-scoped
    // endpoint: target id visible… (``toHaveValue`` reads the DOM
    // property — ``input[value=…]`` would only match the attribute,
    // which b-form-input never sets for dynamic values.)
    await expect(page.getByText(/Bastion info for desktop/).first()).toBeVisible({ timeout: 15000 })
    await expect(page.locator('#bastionId input')).toHaveValue(target.id, { timeout: 10000 })
    // …and READ-ONLY: no authorized-keys editor, no update buttons.
    await expect(page.locator('#sshAuthorizedKeysField')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /update authorized keys/i })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /update custom domains/i })).toHaveCount(0)
  })

  test('bastion csv downloads from the statusbar', async ({ page }) => {
    test.skip(!bastionEnabled, 'bastion is not enabled on this stack')
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')
    test.setTimeout(90000)

    await uiLogin(page, ADMIN_USER, ADMIN_PASSWORD)
    await page.goto(`/deployment/${deploymentId}`)
    await page.waitForLoadState('networkidle')

    const downloadPromise = page.waitForEvent('download', { timeout: 15000 })
    await page.locator('button[title="Download bastion access file"]').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${deploymentId}_bastion.csv`)
  })

  test('profile bastion ssh key modal saves a key', async ({ page, baseURL }) => {
    test.skip(!bastionEnabled, 'bastion is not enabled on this stack')
    test.skip(createdUserIds.length === 0, 'beforeAll did not seed users')
    test.setTimeout(90000)

    await uiLogin(page, profileUsername, USER_PASSWORD)
    await page.goto('/profile')
    await page.waitForLoadState('networkidle')

    await page.getByRole('button', { name: 'Bastion SSH key' }).click()
    const input = page.locator('#sshKeyInput')
    await expect(input).toBeVisible({ timeout: 10000 })
    await input.fill(KEY_PROFILE)
    await page.getByRole('button', { name: /^save key$/i }).click()
    await expect(input).not.toBeVisible({ timeout: 10000 })

    // Roundtrip through the API as the same user (UI session ends here,
    // shadowing is fine).
    const check = new ApiHelper(baseURL ?? 'https://localhost')
    await check.loginAs(profileUsername, USER_PASSWORD)
    const stored = await check._authFetch('GET', '/api/v4/item/user/bastion-ssh-key')
    expect(stored.ssh_key).toBe(KEY_PROFILE)
  })

  test('profile keys are injected into the target at desktop start', async () => {
    test.skip(!bastionEnabled, 'bastion is not enabled on this stack')
    test.skip(!memberDesktopId, 'deployment desktop did not reach Stopped')
    test.setTimeout(180000)

    const cfgNow = await coApi._authFetch('GET', `/api/v4/item/deployment/${deploymentId}/bastion`)
    test.skip(!cfgNow?.ssh?.enabled, 'deployment bastion is not enabled (first test skipped?)')

    await memberApi._authFetch('PUT', `/api/v4/item/desktop/${memberDesktopId}/start`)
    try {
      await memberApi.waitForDomainStatus(memberDesktopId, 'Started', 120000)

      // The member owns the desktop, so /items/bastions exposes the
      // full target including authorized_keys.
      const targets = await memberApi._authFetch('GET', '/api/v4/items/bastions')
      const target = (targets || []).find((t) => t.desktop_id === memberDesktopId)
      expect(target, 'member desktop should have a bastion target').toBeTruthy()
      const keys = target.ssh.authorized_keys || []
      // Desktop-owner key first, then deployment owner + co-owner —
      // deduped, in that order.
      expect(keys[0]).toBe(KEY_MEMBER)
      expect(keys).toContain(KEY_OWNER)
      expect(keys).toContain(KEY_CO)
      expect(new Set(keys).size).toBe(keys.length)
    } finally {
      await memberApi._authFetch('PUT', `/api/v4/item/desktop/${memberDesktopId}/stop`).catch(() => {})
    }
  })

  test('role gates: plain member 403s, co-owner has full config access', async ({ baseURL }) => {
    test.skip(!bastionEnabled, 'bastion is not enabled on this stack')
    test.skip(!deploymentId, 'beforeAll did not seed a deployment')
    test.skip(!memberDesktopId, 'deployment desktop did not reach Stopped')
    test.setTimeout(90000)

    // Member: every deployment-bastion route is owner/co-owner only.
    await expect(
      memberApi._authFetch('GET', `/api/v4/item/deployment/${deploymentId}/bastion`)
    ).rejects.toThrow(/\(403\)/)
    await expect(
      memberApi._authFetch('GET', `/api/v4/item/deployment/${deploymentId}/bastion/csv`)
    ).rejects.toThrow(/\(403\)/)
    await expect(
      memberApi._authFetch(
        'GET',
        `/api/v4/item/deployment/${deploymentId}/desktop/${memberDesktopId}/bastion`
      )
    ).rejects.toThrow(/\(403\)/)

    // Co-owner: full read + write. The CSV is text/csv, so bypass
    // the JSON-parsing _authFetch helper.
    const csvRes = await fetch(
      `${baseURL ?? 'https://localhost'}/api/v4/item/deployment/${deploymentId}/bastion/csv`,
      { headers: { Authorization: `Bearer ${coApi.token}` } }
    )
    expect(csvRes.status).toBe(200)
    const csvText = await csvRes.text()
    expect(csvText).toContain('username')
    expect(csvText).toContain(memberUsername)

    await coApi._authFetch('PUT', `/api/v4/item/deployment/${deploymentId}/bastion`, {
      ssh: { enabled: false, port: 22 },
      http: { enabled: false, http_port: 80, https_port: 443 }
    })
    const disabled = await coApi._authFetch('GET', `/api/v4/item/deployment/${deploymentId}/bastion`)
    expect(disabled.ssh.enabled).toBe(false)
    // Disabling preserves the target (and its keys) — only flips flags.
    const target = await coApi._authFetch(
      'GET',
      `/api/v4/item/deployment/${deploymentId}/desktop/${memberDesktopId}/bastion`
    )
    expect(target.exists).toBe(true)
    expect(target.ssh.enabled).toBe(false)
  })
})
