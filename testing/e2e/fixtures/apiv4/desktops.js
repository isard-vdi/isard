// Desktop-domain helpers: polling/retry around apiv4's 428-while-provisioning
// behaviour, plus create+track factories.

import {
  createDesktop,
  deleteDesktop,
  editDesktop,
  getDesktopDetails,
  getUserAllowedTemplatesFlat,
} from '../../src/gen/apiv4/sdk.gen'
import { unwrap } from './unwrap.js'
import { registerResource, track } from './resources.js'

registerResource('desktop-id', {
  order: 30,
  delete: (client, id) => deleteDesktop({ client, path: { desktop_id: id } }),
})

/**
 * Poll get-details until the desktop reaches Stopped/Failed — apiv4's
 * edit handler returns 428 while the engine is provisioning storage.
 */
export async function waitForDesktopStopped(client, id, { timeoutMs = 60000 } = {}) {
  const deadline = Date.now() + timeoutMs
  let last = null
  while (Date.now() < deadline) {
    try {
      const result = await getDesktopDetails({ client, path: { desktop_id: id } })
      if (result.data) {
        last = result.data.status
        if (last === 'Stopped' || last === 'Failed') return last
      }
    } catch {
      // Endpoint briefly 4xx while the row is being written.
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  throw new Error(`desktop ${id} did not reach Stopped within ${timeoutMs}ms (last status: ${last})`)
}

/** Retry editDesktop while it 428s — the engine flips Stopped → Updating → Stopped between create and edit. */
export async function editDesktopWhenStopped(client, id, body, { timeoutMs = 60000 } = {}) {
  const deadline = Date.now() + timeoutMs
  let last = null
  while (Date.now() < deadline) {
    await waitForDesktopStopped(client, id, { timeoutMs: Math.max(2000, deadline - Date.now()) })
    const result = await editDesktop({ client, path: { desktop_id: id }, body })
    last = result
    if (result.response?.status !== 428) return result
    await new Promise((r) => setTimeout(r, 1000))
  }
  return last
}

export async function getFirstAllowedTemplate(client) {
  const list = await unwrap(getUserAllowedTemplatesFlat({ client, path: { kind: 'all' } }))
  if (!Array.isArray(list) || list.length === 0) {
    throw new Error('getUserAllowedTemplatesFlat returned empty list')
  }
  return list[0]
}

export async function createDesktopAndTrack(client, testInfo, body) {
  const created = await unwrap(createDesktop({ client, body }))
  if (!created?.id) throw new Error('createDesktop: no id in response')
  track(testInfo, 'desktop-id', created.id)
  return created
}
