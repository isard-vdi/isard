// @ts-check
//
// Remove the admin pool that ``global-setup.js`` created. Best
// effort — if cleanup fails, the next run will pre-clean its own
// slots.

import { ApiHelper } from './helpers/api.js'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

export default async function globalTeardown () {
  const fs = await import('fs/promises')
  const path = await import('path')
  const sidecar = path.resolve('tests/e2e/.e2e-admin-pool.json')

  let pool = { created: [] }
  try {
    pool = JSON.parse(await fs.readFile(sidecar, 'utf-8'))
  } catch (e) { return }

  if (!pool.created || pool.created.length === 0) return

  const baseURL =
    process.env.E2E_BASE_URL ?? (process.env.DOCKER ? 'https://host.docker.internal' : 'https://localhost')

  const bootstrap = new ApiHelper(baseURL)
  try {
    await bootstrap.login(
      process.env.E2E_ADMIN_USERNAME ?? 'admin',
      process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI'
    )
    await bootstrap._authFetch('DELETE', '/api/v4/admin/user', {
      user: pool.created,
      delete_user: true
    })
  } catch (e) {
    console.warn(`global-teardown: cleanup failed: ${e.message}`)
  }

  try { await fs.unlink(sidecar) } catch (e) { /* ignore */ }
}
