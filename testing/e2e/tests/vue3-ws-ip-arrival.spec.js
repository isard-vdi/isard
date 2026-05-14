// Pin the WS-driven IP-arrival flow on Vue 3's /frontend/desktops.
//
// What this spec defends against (regressed on apiv4-integration as
// of 2026-05-14, fixed in 2ef128f38 + 3180bbd29):
//
//   1. ``ViewerSelect.vue`` used to capture the Viewer object once at
//      setup with a frozen ``loading`` flag. When desktop.ip later
//      arrived via WS, the dropdown kept ``loading=true`` and the RDP
//      button stayed disabled forever. Fix: track id-only, derive the
//      Viewer via ``computed()`` so the loading flag follows props.
//   2. Three modals/components passed ``getXOptions(...)`` (full
//      options object including queryFn) as the ``queryKey`` value.
//      TanStack's ``cloneDeepUnref`` walked into ``queryFn`` and tried
//      to call it with no args, throwing on every render of the page.
//      Fix: use ``getXQueryKey(...)`` instead.
//
// Strategy (fast tier, no real hypervisor):
//   * Seeded fixture: domains.json carries a Started desktop owned
//     by ``local-default-admin-admin`` with wireguard interface and
//     viewer.guest_ip=null (ws-ip-arrival-fixture-0001).
//   * Mutate viewer.guest_ip via ``PUT /admin/table/update/domains``
//     — same RethinkDB row update path the dnsmasq hook drives in
//     production via ``POST /admin/hypervisor/vm/wg_addr``.
//   * Read the TanStack cache for ``getUserDesktops`` to assert the
//     row's ``ip`` flips.
//   * Assert ``pageerror`` count stays zero so we pin the queryKey
//     fix (the broken queryKey throws on every page load).

import { test, expect } from '../fixtures/login.js'

const FIXTURE_ID = 'ws-ip-arrival-fixture-0001'
const FIXTURE_IP = '10.99.99.43'

const desktopsURL = '/frontend/desktops'

const resolveBaseURL = () =>
  process.env.E2E_BASE_URL ??
  (process.env.DOCKER ? 'https://host.docker.internal' : 'https://localhost')

// Stack ships a self-signed cert; Node's global fetch only honours
// the per-context ignoreHTTPSErrors flag on page requests.
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

// Inline auth + admin-table-update helpers. We deliberately do not
// reach into ``old-frontend/tests/e2e/helpers/api.js`` here — the two
// trees have different package.json type fields and crossing them
// via relative import has bitten the suite before.
//
// Login note: the sessions service shadows older logins when the same
// user authenticates twice. The UI ``loginHelpers.login`` call inside
// the test counts as a fresh login and invalidates any API token we
// minted in ``beforeAll``. We therefore mint a fresh token on every
// call rather than caching one.
async function loginAdminToken(baseURL) {
  const username = process.env.E2E_ADMIN_USERNAME ?? 'admin'
  const password = process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI'
  const form = new FormData()
  form.append('username', username)
  form.append('password', password)
  const res = await fetch(
    `${baseURL}/authentication/login?provider=form&category_id=default`,
    { method: 'POST', body: form }
  )
  if (!res.ok) {
    throw new Error(`auth /login failed (${res.status}): ${await res.text()}`)
  }
  return (await res.text()).trim()
}

async function setDesktopGuestIp(baseURL, desktopId, ip) {
  const doRequest = async () => {
    const token = await loginAdminToken(baseURL)
    return fetch(`${baseURL}/api/v4/admin/table/update/domains`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ id: desktopId, viewer: { guest_ip: ip } })
    })
  }
  let res = await doRequest()
  // Cross-process session shadowing: retry once with a fresh token.
  if (res.status === 401) res = await doRequest()
  if (!res.ok) {
    throw new Error(
      `admin/table/update/domains failed (${res.status}): ${await res.text()}`
    )
  }
}

// Read the row's ip from TanStack's cache for ``getUserDesktops``.
// The query is registered with a key whose first segment is
// ``{_id: 'getUserDesktops', ...}`` (see @hey-api/openapi-ts'
// generated createQueryKey helper).
const readCacheIp = async (page, desktopId) =>
  page.evaluate(
    ([id]) => {
      const root = document.querySelector('#app')
      // @ts-ignore — Vue 3 app exposes itself on the root in dev /
      // also in current production build via __vue_app__.
      const provides = root?.__vue_app__?._context?.provides || {}
      let qc = null
      for (const k of Object.keys(provides)) {
        const v = provides[k]
        if (v && typeof v.getQueryCache === 'function') {
          qc = v
          break
        }
      }
      if (!qc) return { error: 'no-querycache' }
      const queries = qc.getQueryCache().getAll()
      const q = queries.find((x) => x.queryKey?.[0]?._id === 'getUserDesktops')
      if (!q) return { error: 'no-query', count: queries.length }
      const data = q.state?.data
      const list = Array.isArray(data) ? data : data?.desktops ?? []
      const found = list.find((d) => d.id === id)
      if (!found) return { missing: true, total: list.length }
      return { ip: found.ip ?? null, status: found.status ?? null }
    },
    [desktopId]
  )

test.describe.configure({ mode: 'serial' })

test.describe('Vue 3 WS desktop IP-arrival', () => {
  /** @type {string} */
  let baseURL

  test.beforeAll(async () => {
    baseURL = resolveBaseURL()
    // Park the fixture at WaitingIP before the test.
    await setDesktopGuestIp(baseURL, FIXTURE_ID, null)
  })

  test.afterAll(async () => {
    if (baseURL) {
      try {
        await setDesktopGuestIp(baseURL, FIXTURE_ID, null)
      } catch (e) {}
    }
  })

  test('IP arrival via WS flips TanStack cache without page errors', async ({
    page,
    users,
    categories,
    loginHelpers
  }) => {
    // Capture pageerrors — the broken queryKey misuse threw on every
    // render. A clean run must end with zero pageerror events.
    /** @type {string[]} */
    const pageErrors = []
    page.on('pageerror', (e) => pageErrors.push(e.message))

    // Capture WS desktop_update frames carrying the fixture id.
    /** @type {string[]} */
    const desktopUpdateFrames = []
    page.on('websocket', (ws) => {
      ws.on('framereceived', (frame) => {
        const payload = typeof frame.payload === 'string'
          ? frame.payload
          : frame.payload?.toString('utf8') ?? ''
        if (/desktop_update/.test(payload) && payload.includes(FIXTURE_ID)) {
          desktopUpdateFrames.push(payload)
        }
      })
    })

    // Login as bootstrap admin (the fixture's owner). The shared
    // adminPerWorker pool can't see the fixture on /frontend/desktops
    // because Vue 3's user-listing endpoint filters by owner.
    await loginHelpers.login(page, users.admin, categories, desktopsURL)
    await page.waitForLoadState('networkidle', { timeout: 15000 })

    // Wait for the fixture to land in the cache (initial REST call
    // resolves a beat after networkidle).
    let snapshot = await readCacheIp(page, FIXTURE_ID)
    for (let i = 0; i < 20 && (snapshot.missing || snapshot.error); i += 1) {
      await page.waitForTimeout(500)
      snapshot = await readCacheIp(page, FIXTURE_ID)
    }
    expect(
      snapshot,
      `fixture ${FIXTURE_ID} must be visible to bootstrap admin in /frontend/desktops cache`
    ).toMatchObject({ ip: null })

    // Drive the wg_addr-equivalent DB update.
    await setDesktopGuestIp(baseURL, FIXTURE_ID, FIXTURE_IP)

    // Wait for the WS pipeline to flip the cache row.
    let after = await readCacheIp(page, FIXTURE_ID)
    for (let i = 0; i < 40 && after.ip !== FIXTURE_IP; i += 1) {
      await page.waitForTimeout(250)
      after = await readCacheIp(page, FIXTURE_ID)
    }
    expect(after).toMatchObject({ ip: FIXTURE_IP })

    // At least one captured WS frame must carry the new IP.
    expect(
      desktopUpdateFrames.some((f) => f.includes(FIXTURE_IP)),
      `expected ≥1 desktop_update WS frame carrying ${FIXTURE_IP}`
    ).toBeTruthy()

    // No page errors at any point — the queryKey misuse used to fire
    // a TypeError on the initial render of the recycle-bin / profile
    // / direct-viewer share-link components reachable from this page.
    expect(
      pageErrors,
      `no page errors expected; got: ${pageErrors.join(' | ')}`
    ).toHaveLength(0)
  })
})
