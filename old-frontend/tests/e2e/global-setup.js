// @ts-check
//
// Pre-seed a pool of admin users so each Playwright worker gets
// its own credentials. This eliminates the cross-worker JWT
// shadowing in ``isard-sessions`` (the service invalidates older
// sessions when the same user logs in twice in quick succession),
// which previously capped useful parallelism at 2 workers on a
// shared admin login.
//
// The pool is created with bootstrap admin credentials and
// referenced by ``api-fixture.js`` via ``testInfo.workerIndex``.
// ``global-teardown.js`` removes the users after the run.

import { ApiHelper } from './helpers/api.js'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const POOL_SIZE = Number(process.env.E2E_ADMIN_POOL_SIZE ?? 16)
const ADMIN_PASSWORD = process.env.E2E_ADMIN_POOL_PASSWORD ?? 'e2e_admin_pw'

export default async function globalSetup () {
  const baseURL =
    process.env.E2E_BASE_URL ?? (process.env.DOCKER ? 'https://host.docker.internal' : 'https://localhost')

  const bootstrap = new ApiHelper(baseURL)
  await bootstrap.login(
    process.env.E2E_ADMIN_USERNAME ?? 'admin',
    process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI'
  )

  const created = []
  for (let i = 0; i < POOL_SIZE; i++) {
    const username = `e2e_admin_${i}`
    // Best-effort delete in case a prior aborted run left it behind.
    try {
      const existing = await bootstrap._authFetch('GET', `/api/v4/admin/user/${username}/raw`)
      if (existing?.id) {
        await bootstrap._authFetch('DELETE', '/api/v4/admin/user', {
          user: [existing.id],
          delete_user: true
        })
      }
    } catch (e) { /* user did not exist */ }

    try {
      const user = await bootstrap.createUser(
        username,
        'default',
        'default-default',
        'admin',
        ADMIN_PASSWORD
      )
      created.push(user.id)
    } catch (e) {
      console.warn(`global-setup: failed to seed ${username}: ${e.message}`)
    }
  }

  // Stash created ids in a sidecar so global-teardown can clean up
  // even if the suite aborts mid-run.
  const fs = await import('fs/promises')
  const path = await import('path')
  await fs.writeFile(
    path.resolve('tests/e2e/.e2e-admin-pool.json'),
    JSON.stringify({ created, password: ADMIN_PASSWORD }, null, 2)
  )
}
