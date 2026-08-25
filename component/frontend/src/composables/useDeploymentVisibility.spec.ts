import { describe, expect, it, vi } from 'vitest'

vi.mock('@tanstack/vue-query', () => ({
  useMutation: () => ({}),
  useQueryClient: () => ({})
}))

vi.mock('@/gen/oas/apiv4/@tanstack/vue-query.gen', () => ({
  setDeploymentVisibilityMutation: () => ({}),
  getDeploymentQueryKey: () => [{ _id: 'getDeployment' }],
  getAllDeploymentsQueryKey: () => [{ _id: 'getAllDeployments' }]
}))

import { patchVisibility } from './useDeploymentVisibility'

const cached = () =>
  ({
    info: { id: 'dep-1', tag_visible: true, visible_desktops: 3 },
    users: [
      {
        id: 'u1',
        name: 'alice',
        visible: true,
        desktops: [
          { desktop_id: 'd1', tag_desktop_id: 'r1', visible: true },
          { desktop_id: 'd2', tag_desktop_id: 'r2', visible: true }
        ]
      },
      {
        id: 'u2',
        name: 'bob',
        visible: true,
        desktops: [
          { desktop_id: 'd3', tag_desktop_id: 'r1', visible: true },
          { desktop_id: 'd4', tag_desktop_id: 'r2', visible: false }
        ]
      }
    ]
  }) as never

const visibilityOf = (result: never, id: string) =>
  (result as never as { users: { desktops: { desktop_id: string; visible: boolean }[] }[] }).users
    .flatMap((user) => user.desktops)
    .find((desktop) => desktop.desktop_id === id)?.visible

describe('patchVisibility', () => {
  it('hides every desktop when no selector is given', () => {
    const result = patchVisibility(cached(), { visible: false }) as never
    expect(['d1', 'd2', 'd3', 'd4'].map((id) => visibilityOf(result, id))).toEqual([
      false,
      false,
      false,
      false
    ])
    expect((result as never as { info: { visible_desktops: number } }).info.visible_desktops).toBe(
      0
    )
  })

  it('scopes a desktop column to that desktop across all users', () => {
    const result = patchVisibility(cached(), {
      visible: false,
      tag_desktop_ids: ['r1']
    }) as never
    expect(visibilityOf(result, 'd1')).toBe(false)
    expect(visibilityOf(result, 'd3')).toBe(false)
    expect(visibilityOf(result, 'd2')).toBe(true) // other desktop untouched
  })

  it('scopes a user row to that user', () => {
    const result = patchVisibility(cached(), { visible: false, users: ['u1'] }) as never
    expect(visibilityOf(result, 'd1')).toBe(false)
    expect(visibilityOf(result, 'd3')).toBe(true)
  })

  it('scopes a single cell to one user and one desktop', () => {
    const result = patchVisibility(cached(), {
      visible: false,
      users: ['u1'],
      tag_desktop_ids: ['r1']
    }) as never
    expect(visibilityOf(result, 'd1')).toBe(false)
    expect(['d2', 'd3'].map((id) => visibilityOf(result, id))).toEqual([true, true])
  })

  it('lets desktop_ids win over the rectangle selectors', () => {
    // This is what Undo sends, and it has to restore a non-rectangular state.
    const result = patchVisibility(cached(), {
      visible: false,
      users: ['u2'],
      tag_desktop_ids: ['r2'],
      desktop_ids: ['d1']
    }) as never
    expect(visibilityOf(result, 'd1')).toBe(false)
    expect(visibilityOf(result, 'd4')).toBe(false) // was already hidden
    expect(visibilityOf(result, 'd3')).toBe(true)
  })

  it('derives user and deployment flags as OR, mirroring the server', () => {
    const result = patchVisibility(cached(), {
      visible: false,
      users: ['u1']
    }) as never
    const users = (result as never as { users: { id: string; visible: boolean }[] }).users
    expect(users.find((user) => user.id === 'u1')?.visible).toBe(false)
    // bob keeps one visible desktop, so both he and the deployment stay visible
    expect(users.find((user) => user.id === 'u2')?.visible).toBe(true)
    expect((result as never as { info: { tag_visible: boolean } }).info.tag_visible).toBe(true)
  })

  it('clears the deployment flag once nothing is left visible', () => {
    const result = patchVisibility(cached(), { visible: false }) as never
    expect((result as never as { info: { tag_visible: boolean } }).info.tag_visible).toBe(false)
  })

  it('returns undefined when there is nothing cached', () => {
    expect(patchVisibility(undefined, { visible: true })).toBeUndefined()
  })
})
