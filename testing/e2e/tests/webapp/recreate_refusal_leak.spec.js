// Regression spec: a refused recreate must leave no storage row behind.
// A refused recreate must leave no storage row behind.

import {
  test,
  expect,
  createDesktopAndTrack,
  waitForDesktopStopped,
} from '../../fixtures/apiv4/index.js'

// Seeded template with a ready storage in the default category (populate_test_db.py).
const TEMPLATE_ID = 'template-test-001'
const REFUSALS = 3

// `Stopped` says the domain settled, not the disk: the chain that creates the
// qcow2 finishes after it, and a recreate over a disk that is not yet `ready`
// is refused by the same guard this spec is about. Wait for the disk itself.
async function waitForDiskReady(page, domainId, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs
  let last = 'unknown'
  while (Date.now() < deadline) {
    const resp = await page.request.get(
      `/api/v4/admin/item/domain/storage/${domainId}`,
    )
    if (resp.ok()) {
      const disks = await resp.json()
      if (Array.isArray(disks) && disks.length) {
        last = disks[0].status
        // `ready` alone flakes: a disk whose creation chain still holds a pending
        // task answers 428 storage_pending_task, so wait for it to clear too.
        if (disks.every((d) => d.status === 'ready' && !d.has_pending_task))
          return last
      }
    }
    await new Promise((r) => setTimeout(r, 2000))
  }
  return last
}

async function firstDiskId(page, domainId) {
  const resp = await page.request.get(
    `/api/v4/admin/item/domain/storage/${domainId}`,
  )
  expect(resp.ok(), `domain storage returned ${resp.status()}`).toBeTruthy()
  const disks = await resp.json()
  expect(Array.isArray(disks) && disks.length).toBeTruthy()
  return disks[0].id
}

async function nonExistingIds(page) {
  const resp = await page.request.get(
    '/api/v4/admin/items/storage/by-status/non_existing',
  )
  expect(resp.ok(), `by-status returned ${resp.status()}`).toBeTruthy()
  const body = await resp.json()
  const rows = Array.isArray(body) ? body : body.items || []
  return rows.map((r) => r.id).filter(Boolean)
}

async function storageInfo(page, storageId) {
  const resp = await page.request.get(
    `/api/v4/admin/item/storage/info/${storageId}`,
  )
  return resp.ok() ? await resp.json() : null
}

// ``Storage.recreate`` stamps this on the row it allocates, so a leak of THIS
// call is identifiable without counting anything global.
function marker(diskId) {
  return `recreated from ${diskId}`
}

test.describe('A refused recreate leaks no storage row', () => {
  test('clicking recreate again while the disk is parked leaves no row behind', async ({
    apiv4Admin,
    authenticatedPage,
  }, testInfo) => {
    const page = authenticatedPage
    const name = `e2erec-${Date.now().toString().slice(-6)}`

    const created = await createDesktopAndTrack(apiv4Admin, testInfo, {
      template_id: TEMPLATE_ID,
      name,
      description: 'refused recreate must not leak a storage row',
    })
    expect(
      await waitForDesktopStopped(apiv4Admin, created.id, { timeoutMs: 90000 }),
    ).toBe('Stopped')
    expect(
      await waitForDiskReady(page, created.id),
      'the disk must be ready before a recreate can be accepted',
    ).toBe('ready')
    const diskId = await firstDiskId(page, created.id)

    // The leak check reads ``status_logs``; if the field ever stops being
    // exposed the check would pass by finding nothing, so prove it is there.
    expect(
      Array.isArray((await storageInfo(page, diskId))?.status_logs),
      'the leak check needs status_logs exposed on the storage row',
    ).toBe(true)

    // First click is accepted: it parks the disk and starts the replacement.
    const first = await page.request.put(
      `/api/v4/item/desktop/${created.id}/recreate`,
    )
    expect(first.status(), 'the first recreate must be accepted').toBe(200)

    // Taken AFTER the accepted click, so the row that click legitimately
    // allocates is already inside the baseline.
    const before = new Set(await nonExistingIds(page))

    // The user cannot tell the disk is busy, so they click again. Every one of
    // these is refused because the disk is no longer ready.
    const statuses = []
    for (let i = 0; i < REFUSALS; i++) {
      const again = await page.request.put(
        `/api/v4/item/desktop/${created.id}/recreate`,
      )
      statuses.push(again.status())
    }
    expect(
      statuses,
      'a recreate over a parked disk must be refused, not accepted',
    ).toEqual(Array(REFUSALS).fill(428))

    // Counting rows globally made this spec fail whenever a parallel spec had a
    // desktop mid-creation: its transient row landed after the baseline. Ask
    // instead which of the new rows this call wrote, by its own marker.
    const fresh = (await nonExistingIds(page)).filter((id) => !before.has(id))
    const mine = []
    for (const id of fresh) {
      const row = await storageInfo(page, id)
      if ((row?.status_logs || []).some((l) => l.status === marker(diskId)))
        mine.push(id)
    }
    expect(
      mine,
      `${REFUSALS} refused recreates left ${mine.length} storage rows behind; ` +
        'a refusal must write nothing',
    ).toEqual([])
  })
})
