import { describe, it, expect } from 'vitest'
import {
  MAX_VGPU_PROFILES,
  commonHypervisorGroups,
  isVgpuSelectable,
  type VgpuLike
} from './vgpuSelection'

const opts: VgpuLike[] = [
  { id: 'a', hypervisor_groups: [1, 2] },
  { id: 'b', hypervisor_groups: [2, 3] },
  { id: 'c', hypervisor_groups: [4] }, // disjoint from a/b
  { id: 'd' } // no group info
]

describe('commonHypervisorGroups', () => {
  it('is null when nothing is selected', () => {
    expect(commonHypervisorGroups([], opts)).toBeNull()
  })

  it('is the single profile groups when one is selected', () => {
    expect([...(commonHypervisorGroups(['a'], opts) ?? [])].sort()).toEqual([1, 2])
  })

  it('intersects groups across the selection', () => {
    expect([...(commonHypervisorGroups(['a', 'b'], opts) ?? [])]).toEqual([2])
  })

  it('is empty when the selection cannot co-locate', () => {
    expect(commonHypervisorGroups(['a', 'c'], opts)?.size).toBe(0)
  })

  it('is null (unconstrained) when selected profiles carry no group info', () => {
    expect(commonHypervisorGroups(['d'], opts)).toBeNull()
  })
})

describe('isVgpuSelectable', () => {
  it('always allows deselecting an already-selected profile', () => {
    expect(isVgpuSelectable(opts[2], ['a', 'c'], opts)).toBe(true) // c selected, disjoint
  })

  it('allows any profile when nothing is selected', () => {
    expect(isVgpuSelectable(opts[2], [], opts)).toBe(true)
  })

  it('blocks a profile that cannot co-locate with the selection', () => {
    expect(isVgpuSelectable(opts[2], ['a'], opts)).toBe(false) // c [4] vs common {1,2}
  })

  it('allows a co-locatable profile', () => {
    expect(isVgpuSelectable(opts[1], ['a'], opts)).toBe(true) // b shares group 2 with a
  })

  it('allows a profile without group info regardless of selection', () => {
    expect(isVgpuSelectable(opts[3], ['a'], opts)).toBe(true) // d has no groups
  })

  it('enforces the max-profile count', () => {
    const selected = ['a', 'b', 'd']
    expect(isVgpuSelectable({ id: 'e', hypervisor_groups: [2] }, selected, opts, 3)).toBe(false)
  })

  it('uses MAX_VGPU_PROFILES = 4 by default', () => {
    expect(MAX_VGPU_PROFILES).toBe(4)
    const selected = ['a', 'b', 'd', 'x']
    expect(
      isVgpuSelectable({ id: 'y', hypervisor_groups: [2] }, selected, [
        ...opts,
        { id: 'x', hypervisor_groups: [2] },
        { id: 'y', hypervisor_groups: [2] }
      ])
    ).toBe(false)
  })
})
