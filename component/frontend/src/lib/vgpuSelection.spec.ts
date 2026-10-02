import { describe, it, expect } from 'vitest'
import {
  MAX_VGPU_PROFILES,
  commonHypervisorGroups,
  isVgpuSelectable,
  numaSocketHint,
  type VgpuLike,
  type VgpuNumaLike
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

describe('numaSocketHint', () => {
  // Group 1 is a two-socket server, group 2 a single-socket one.
  const numa: VgpuNumaLike[] = [
    { id: 'n0', hypervisor_groups: [1], numa_by_group: { '1': [0] } },
    { id: 'n1', hypervisor_groups: [1], numa_by_group: { '1': [1] } },
    { id: 'both', hypervisor_groups: [1, 2], numa_by_group: { '1': [0, 1], '2': [0] } },
    { id: 'single', hypervisor_groups: [2], numa_by_group: { '2': [0] } },
    { id: 'other', hypervisor_groups: [3] }
  ]

  it('says nothing for fewer than two profiles', () => {
    expect(numaSocketHint([], numa)).toBeNull()
    expect(numaSocketHint(['n0'], numa)).toBeNull()
  })

  it('names the shared socket when every profile has a card on it', () => {
    expect(numaSocketHint(['n1', 'both'], numa)).toEqual({ ok: true, node: 1 })
    expect(numaSocketHint(['n0', 'both'], numa)).toEqual({ ok: true, node: 0 })
  })

  it('warns when only different sockets are possible', () => {
    expect(numaSocketHint(['n0', 'n1'], numa)).toEqual({ ok: false })
  })

  it('says nothing on a single-socket common server', () => {
    expect(numaSocketHint(['both', 'single'], numa)).toBeNull()
  })

  it('says nothing when the profiles share no hypervisor', () => {
    expect(numaSocketHint(['n0', 'other'], numa)).toBeNull()
  })
})
