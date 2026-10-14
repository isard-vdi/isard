import { QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  setDeploymentVisibilityMutation: () => ({}),
  getDeploymentQueryKey: ({ path }: { path: { deployment_id: string } }) => [
    { _id: 'getDeployment', path }
  ],
  getAllDeploymentsQueryKey: () => [{ _id: 'getAllDeployments' }]
}))

import { deploymentDesktopEventHandlers } from './deployment-desktop'

const DEPLOYMENT_KEY = [{ _id: 'getDeployment', path: { deployment_id: 'dep-1' } }]
const userDesktopsKey = (deploymentId: string) => [
  { _id: 'getDeploymentUserDesktops', path: { deployment_id: deploymentId, user_id: 'u1' } }
]

const cached = () => ({
  info: {
    id: 'dep-1',
    tag_visible: true,
    visible_desktops: 2,
    started_desktops: 0,
    existing_desktops: 2
  },
  users: [
    {
      id: 'u1',
      name: 'alice',
      visible: true,
      last_access: 10,
      desktops_statuses: [{ status: 'Stopped', amount: 1 }],
      desktops: [{ desktop_id: 'd1', tag_desktop_id: 'r1', name: 'one', visible: true }]
    },
    {
      id: 'u2',
      name: 'bob',
      visible: true,
      last_access: null,
      desktops_statuses: [{ status: 'Stopped', amount: 1 }],
      desktops: [{ desktop_id: 'd2', tag_desktop_id: 'r1', name: 'one', visible: true }]
    }
  ]
})

const event = (overrides: Record<string, unknown> = {}) =>
  JSON.stringify({
    id: 'd1',
    tag: 'dep-1',
    user: 'u1',
    name: 'one',
    status: 'Started',
    visible: false,
    accessed: 42,
    ...overrides
  })

let queryClient: QueryClient
let invalidate: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  vi.useFakeTimers()
  queryClient = new QueryClient()
  queryClient.setQueryData(DEPLOYMENT_KEY, cached())
  invalidate = vi.spyOn(queryClient, 'invalidateQueries')
})

const read = () => queryClient.getQueryData(DEPLOYMENT_KEY) as ReturnType<typeof cached> | undefined
const isInvalidated = (key: unknown[]) => !!queryClient.getQueryState(key)?.isInvalidated

describe('deploymentdesktop_update', () => {
  it('folds the event into the cache without refetching it', () => {
    deploymentDesktopEventHandlers.deploymentdesktop_update(queryClient, event())
    vi.advanceTimersByTime(400)

    const users = read().users
    expect(users[0].desktops[0].visible).toBe(false)
    expect(users[0].desktops[0].status).toBe('Started')
    expect(isInvalidated(DEPLOYMENT_KEY)).toBe(false)
  })

  it('still refreshes the other deployment queries in one go', () => {
    queryClient.setQueryData(userDesktopsKey('dep-1'), { desktops: [] })
    for (let i = 0; i < 20; i++) {
      deploymentDesktopEventHandlers.deploymentdesktop_update(queryClient, event())
    }
    vi.advanceTimersByTime(400)

    expect(invalidate).toHaveBeenCalledOnce()
    expect(isInvalidated(userDesktopsKey('dep-1'))).toBe(true)
    expect(isInvalidated(DEPLOYMENT_KEY)).toBe(false)
  })

  it('re-derives the aggregates the API computes', () => {
    deploymentDesktopEventHandlers.deploymentdesktop_update(queryClient, event())
    const patched = read()
    expect(patched.info.visible_desktops).toBe(1)
    expect(patched.info.started_desktops).toBe(1)
    expect(patched.info.tag_visible).toBe(true) // bob still has a visible one
    expect(patched.users[0].visible).toBe(false)
    expect(patched.users[0].desktops_statuses).toEqual([{ status: 'Started', amount: 1 }])
    expect(patched.users[0].last_access).toBe(42)
  })

  it('clears the deployment flag once the last desktop is hidden', () => {
    deploymentDesktopEventHandlers.deploymentdesktop_update(queryClient, event())
    deploymentDesktopEventHandlers.deploymentdesktop_update(
      queryClient,
      event({ id: 'd2', user: 'u2', status: 'Stopped' })
    )
    expect(read().info.tag_visible).toBe(false)
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('keeps a wireguard desktop started while it waits for its guest IP', () => {
    deploymentDesktopEventHandlers.deploymentdesktop_update(
      queryClient,
      event({ status: 'WaitingIP' })
    )
    const patched = read()
    expect(patched.users[0].desktops[0].status).toBe('Started')
    expect(patched.info.started_desktops).toBe(1)
  })

  it('refetches the deployment for a desktop the cache does not know', () => {
    deploymentDesktopEventHandlers.deploymentdesktop_update(queryClient, event({ id: 'd9' }))
    deploymentDesktopEventHandlers.deploymentdesktop_update(queryClient, event())
    vi.advanceTimersByTime(400)
    expect(invalidate).toHaveBeenCalledOnce()
    expect(isInvalidated(DEPLOYMENT_KEY)).toBe(true)
  })

  it('refreshes a participant, who has no deployment to patch', () => {
    queryClient.setQueryData(userDesktopsKey('dep-2'), { desktops: [] })
    deploymentDesktopEventHandlers.deploymentdesktop_update(queryClient, event({ tag: 'dep-2' }))
    vi.advanceTimersByTime(400)
    expect(isInvalidated(userDesktopsKey('dep-2'))).toBe(true)
  })
})

describe('a visibility write of our own in flight', () => {
  it('keeps the optimistic visibility and still takes the rest of the row', () => {
    vi.spyOn(queryClient, 'isMutating').mockReturnValue(1)
    deploymentDesktopEventHandlers.deploymentdesktop_update(
      queryClient,
      event({ visible: false, status: 'Started' })
    )
    const desktop = read().users[0].desktops[0]
    expect(desktop.visible).toBe(true) // held at the optimistic value
    expect(desktop.status).toBe('Started')
  })
})

describe('invalidation', () => {
  it('coalesces a burst of structural events into one refetch', () => {
    for (let i = 0; i < 50; i++) {
      deploymentDesktopEventHandlers.deploymentdesktop_add(queryClient, event({ id: `new-${i}` }))
    }
    vi.advanceTimersByTime(400)
    expect(invalidate).toHaveBeenCalledOnce()
  })
})

describe('deployments_update', () => {
  it('patches the deployment columns without refetching', () => {
    deploymentDesktopEventHandlers.deployments_update(
      queryClient,
      JSON.stringify({ id: 'dep-1', name: 'renamed', description: 'why' })
    )
    vi.advanceTimersByTime(400)
    expect(read().info.name).toBe('renamed')
    expect(invalidate).not.toHaveBeenCalled()
  })
})
