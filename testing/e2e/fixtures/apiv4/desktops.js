// Desktop-domain helpers: polling/retry around apiv4's 428-while-provisioning
// behaviour, plus create+track factories.

import {
  createDesktop,
  createNonpersistentDesktop,
  deleteDesktop,
  editDesktop,
  getDesktopDetails,
  getUserAllowedTemplatesFlat,
  getUserDesktops,
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

// ── Temporary (non-persistent) desktops ─────────────────────────────────────

// Statuses, as the desktops list reports them, that a temporary desktop
// does not leave on its own. `WaitingIP` is a desktop that is `Started` in
// the database, has a wireguard interface and no guest IP yet. Outside
// them the desktop is still being created or started, and new-nonpersistent
// can answer 428 instead of reusing it.
const SETTLED_STATUSES = new Set(['Started', 'WaitingIP', 'Stopped', 'Failed'])

/** First enabled template of the caller that needs no GPU booking to start. */
export async function getTemporaryDesktopTemplate(client) {
  const list = await unwrap(getUserAllowedTemplatesFlat({ client, path: { kind: 'all' } }))
  const template = (list ?? []).find(
    (t) => t.enabled !== false && !(t.reservables?.vgpus ?? []).length,
  )
  if (!template) throw new Error('no allowed template without GPU reservables')
  return template
}

/** The caller's temporary desktops derived from `templateId`. */
export async function listTemporaryDesktops(client, templateId) {
  const data = await unwrap(getUserDesktops({ client }))
  return (data?.desktops ?? []).filter(
    (desktop) => desktop.type === 'nonpersistent' && desktop.template === templateId,
  )
}

/** POST new-nonpersistent as the caller; tracks whatever id comes back. */
export async function createTemporaryDesktopAndTrack(client, testInfo, templateId) {
  const result = await createNonpersistentDesktop({ client, body: { template_id: templateId } })
  if (result.data?.id) track(testInfo, 'desktop-id', result.data.id)
  return result
}

/** Polls the caller's temporary desktops of `templateId` until `predicate` holds. */
export async function waitForTemporaryDesktops(
  client,
  templateId,
  predicate,
  { timeoutMs = 60000, message = 'temporary desktops' } = {},
) {
  const deadline = Date.now() + timeoutMs
  let desktops = []
  for (;;) {
    desktops = await listTemporaryDesktops(client, templateId)
    if (predicate(desktops)) return desktops
    if (Date.now() >= deadline) {
      throw new Error(
        `${message}: condition not met after ${timeoutMs} ms, last: ${JSON.stringify(
          desktops.map((d) => ({ id: d.id, status: d.status })),
        )}`,
      )
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
}

/** Waits until every temporary desktop of `templateId` has settled. */
export async function waitForTemporaryDesktopsSettled(client, templateId, options) {
  return waitForTemporaryDesktops(
    client,
    templateId,
    (desktops) => desktops.every((desktop) => SETTLED_STATUSES.has(desktop.status)),
    { message: 'temporary desktops settled', ...options },
  )
}

/** Deletes the caller's temporary desktops of `templateId` and waits until they are gone. */
export async function deleteTemporaryDesktops(client, templateId) {
  for (const desktop of await listTemporaryDesktops(client, templateId)) {
    await deleteDesktop({ client, path: { desktop_id: desktop.id } })
  }
  return waitForTemporaryDesktops(client, templateId, (desktops) => desktops.length === 0, {
    message: 'temporary desktops deleted',
  })
}
