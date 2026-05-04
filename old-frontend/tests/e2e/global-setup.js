// @ts-check
//
// Pre-seed a pool of admin users so each Playwright worker gets
// its own credentials. This eliminates the cross-worker JWT
// shadowing in ``isard-sessions`` (the service invalidates older
// sessions when the same user logs in twice in quick succession),
// which previously capped useful parallelism at 2 workers on a
// shared admin login.
//
// Pool is sized to the actual worker count Playwright resolved
// (``config.workers``), so any number of workers is safe — set
// ``--workers=8`` and 8 admins are created, ``--workers=64`` and
// 64 are created. Creation is parallelised in batches so seeding
// is fast even on big pools.
//
// ``global-teardown.js`` removes the users after the run via the
// sidecar file ``tests/e2e/.e2e-admin-pool.json``.

import { ApiHelper } from './helpers/api.js'

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

const ADMIN_PASSWORD = process.env.E2E_ADMIN_POOL_PASSWORD ?? 'e2e_admin_pw'
// How many admin creates to run concurrently. apiv4 + sessions
// service handle small bursts comfortably; 4 is a safe default
// that covers up to ~64 workers in <10 s.
const SETUP_CONCURRENCY = Number(process.env.E2E_ADMIN_POOL_CONCURRENCY ?? 4)

// Pre-fetch the existing admin pool by listing /admin/users once
// instead of probing per-username (the /admin/user/{id}/raw
// endpoint requires the UUID, not the username — stale lookups
// always 404'd, leaving the leftover users behind and causing
// 409 Conflict on re-create).
const fetchExistingPool = async (bootstrap) => {
  const map = {}
  try {
    const list = await bootstrap._authFetch('GET', '/api/v4/admin/users')
    const items = Array.isArray(list) ? list : list?.users ?? []
    for (const u of items) {
      if (u?.username && u.username.startsWith('e2e_admin_')) {
        map[u.username] = u.id
      }
    }
  } catch (e) { /* ignore — we'll create fresh */ }
  return map
}

const seedOne = async (bootstrap, index, existingMap) => {
  const username = `e2e_admin_${index}`

  // If a leftover from a prior aborted run is in the existing
  // map, delete it first.
  if (existingMap[username]) {
    try {
      await bootstrap._authFetch('DELETE', '/api/v4/admin/user', {
        user: [existingMap[username]],
        delete_user: true
      })
    } catch (e) { /* ignore */ }
  }

  try {
    const user = await bootstrap.createUser(
      username,
      'default',
      'default-default',
      'admin',
      ADMIN_PASSWORD
    )
    return user.id
  } catch (e) {
    console.warn(`global-setup: failed to seed ${username}: ${e.message}`)
    return null
  }
}

export default async function globalSetup (config) {
  const baseURL =
    process.env.E2E_BASE_URL ?? (process.env.DOCKER ? 'https://host.docker.internal' : 'https://localhost')

  // Match pool size to the actual worker count. Override via
  // ``E2E_ADMIN_POOL_SIZE`` if you want a larger spare pool.
  const requested = Number(process.env.E2E_ADMIN_POOL_SIZE ?? 0)
  const poolSize = requested > 0
    ? requested
    : Math.max(1, config?.workers ?? 1)

  const bootstrap = new ApiHelper(baseURL)
  await bootstrap.login(
    process.env.E2E_ADMIN_USERNAME ?? 'admin',
    process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI'
  )

  // Single user list scan — saves N round-trips of stale-entry
  // probes, and importantly uses the right endpoint
  // (/admin/users not /admin/user/{name}/raw which expects a
  // UUID, not a username, and always 404'd).
  const existingMap = await fetchExistingPool(bootstrap)

  const indices = Array.from({ length: poolSize }, (_, i) => i)
  const created = []

  // Run in batches of SETUP_CONCURRENCY parallel creates so we
  // don't overwhelm the sessions service with simultaneous
  // bootstrap-admin calls.
  for (let i = 0; i < indices.length; i += SETUP_CONCURRENCY) {
    const batch = indices.slice(i, i + SETUP_CONCURRENCY)
    const ids = await Promise.all(batch.map((idx) => seedOne(bootstrap, idx, existingMap)))
    for (const id of ids) {
      if (id) created.push(id)
    }
  }

  console.log(`global-setup: seeded ${created.length} admin pool users for ${poolSize} workers`)

  const fs = await import('fs/promises')
  const path = await import('path')
  await fs.writeFile(
    path.resolve('tests/e2e/.e2e-admin-pool.json'),
    JSON.stringify({ created, password: ADMIN_PASSWORD, poolSize }, null, 2)
  )
}
