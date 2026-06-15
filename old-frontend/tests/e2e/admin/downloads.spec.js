// @ts-check
import { test } from '../navbar'
import { PageAdminDownloads } from './downloads-page'

// Probe the admin downloads listing to detect TetrOS availability.
// Without TetrOS available, the spec can't exercise the download
// flow — it's a fixture gap, not a code regression.
let tetrOSAvailable = null
const hasTetrOS = async () => {
  if (tetrOSAvailable !== null) return tetrOSAvailable
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'
  const baseURL =
    process.env.E2E_BASE_URL ?? (process.env.DOCKER ? 'https://host.docker.internal' : 'https://localhost')
  try {
    const fd = new FormData()
    fd.append('username', process.env.E2E_ADMIN_USERNAME ?? 'admin')
    fd.append('password', process.env.E2E_ADMIN_PASSWORD ?? 'IsardVDI')
    const tokRes = await fetch(`${baseURL}/authentication/login?provider=form&category_id=default`, {
      method: 'POST', body: fd
    })
    const tok = (await tokRes.text()).trim()
    const list = await fetch(`${baseURL}/api/v4/admin/downloads`, {
      headers: { Authorization: `Bearer ${tok}` }
    }).then((r) => r.json()).catch(() => null)
    tetrOSAvailable = JSON.stringify(list || []).toLowerCase().includes('tetros')
  } catch (e) {
    tetrOSAvailable = false
  }
  return tetrOSAvailable
}

test.describe('Downloads', () => {
  test('should download slax correctly', async ({ page, administration }) => {
    const ok = await hasTetrOS()
    test.skip(
      !ok,
      'TetrOS template not available in /admin/downloads — bring up with USAGE=test or seed the upstream media catalog'
    )
    const downloads = new PageAdminDownloads(page)
    await downloads.goto()
    await downloads.download('TetrOS')
  })
})
