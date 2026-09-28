// Regression spec: a desktop whose disk cannot come back must not come back
// looking startable -- and a recoverable disk must still be allowed to.

import {
  test,
  expect,
  createDesktopAndTrack,
  waitForDesktopStopped,
} from '../../fixtures/apiv4/index.js'

// Seeded template with a ready storage in the default category (populate_test_db.py).
const TEMPLATE_ID = 'template-test-001'
// Terminal: nothing carries the row back to `ready`. `maintenance` is the
// counterpart the engine is still right to wait for.
const TERMINAL = 'deleted'
const RECOVERABLE = 'maintenance'

async function firstDiskId(page, domainId) {
  const resp = await page.request.get(
    `/api/v4/admin/item/domain/storage/${domainId}`,
  )
  expect(resp.ok(), `domain storage returned ${resp.status()}`).toBeTruthy()
  const disks = await resp.json()
  expect(Array.isArray(disks) && disks.length).toBeTruthy()
  return disks[0].id
}

async function setStatus(page, table, id, status) {
  const resp = await page.request.put(
    `/api/v4/admin/item/table/update/${table}`,
    { data: { id, status } },
  )
  expect(
    resp.ok(),
    `setting ${table}.${id} to ${status} returned ${resp.status()}`,
  ).toBeTruthy()
}

// The listing the dashboard renders the badge from. It carries no detail, which
// is the whole point: the status itself has to tell the truth.
async function listedStatus(page, domainId) {
  const resp = await page.request.get('/api/v4/items/desktops')
  if (!resp.ok()) return null
  const body = await resp.json()
  const rows = Array.isArray(body) ? body : body.desktops || []
  return rows.find((d) => d.id === domainId)?.status ?? null
}

async function waitForListed(page, domainId, status, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs
  let seen = null
  while (Date.now() < deadline) {
    seen = await listedStatus(page, domainId)
    if (seen === status) return seen
    await new Promise((r) => setTimeout(r, 1500))
  }
  return seen
}

async function detailOf(page, domainId) {
  const resp = await page.request.get(
    `/api/v4/admin/items/table/domains?id=${domainId}`,
  )
  expect(resp.ok(), `domains row returned ${resp.status()}`).toBeTruthy()
  return (await resp.json())?.detail ?? ''
}

test.describe('A desktop whose disk is terminal is not startable', () => {
  test('a start over a terminal disk answers Failed, and retry refuses', async ({
    apiv4Admin,
    authenticatedPage,
  }, testInfo) => {
    test.setTimeout(300000)
    const page = authenticatedPage

    const created = await createDesktopAndTrack(apiv4Admin, testInfo, {
      template_id: TEMPLATE_ID,
      name: `e2eterm-${Date.now().toString().slice(-6)}`,
      description: 'a terminal disk must not look startable',
    })
    expect(
      await waitForDesktopStopped(apiv4Admin, created.id, { timeoutMs: 120000 }),
    ).toBe('Stopped')
    const diskId = await firstDiskId(page, created.id)

    try {
      await setStatus(page, 'storage', diskId, TERMINAL)
      // The engine acts on the Stopped -> Starting transition, which is what
      // every caller of a start ultimately writes.
      await setStatus(page, 'domains', created.id, 'Starting')

      expect(
        await waitForListed(page, created.id, 'Failed'),
        'a desktop whose disk will never be ready must not read as startable',
      ).toBe('Failed')

      const detail = await detailOf(page, created.id)
      expect(detail).toContain(TERMINAL)
      expect(detail).toContain('will not become ready')

      const retry = await page.request.put(
        `/api/v4/item/desktop/${created.id}/retry`,
      )
      expect(
        retry.status(),
        'retry must not hand the engine a desktop it will bounce',
      ).toBe(428)
      expect(await listedStatus(page, created.id)).toBe('Failed')

      // The control: without it a spec that only ever asserts Failed would pass
      // on an engine that failed everything.
      await setStatus(page, 'storage', diskId, RECOVERABLE)
      await setStatus(page, 'domains', created.id, 'Stopped')
      await setStatus(page, 'domains', created.id, 'Starting')
      expect(
        await waitForListed(page, created.id, 'Stopped'),
        'a disk that can still become ready must keep the desktop Stopped',
      ).toBe('Stopped')
      expect(await detailOf(page, created.id)).not.toContain(
        'will not become ready',
      )
    } finally {
      await setStatus(page, 'storage', diskId, 'ready')
      await setStatus(page, 'domains', created.id, 'Stopped')
    }
  })
})
