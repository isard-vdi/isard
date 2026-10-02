// Multi-profile vGPU selection helpers.
//
// A desktop may reserve up to MAX_VGPU_PROFILES vGPU profiles, but they must be
// co-locatable on a single hypervisor: every selected profile has to share at
// least one `hypervisor_groups` index with all the others. The backend enforces
// both rules (errors `too_many_vgpu_profiles`, `vgpu_profiles_different_hypervisors`,
// `duplicate_vgpu_profiles`); this mirrors them client-side so the selector can
// grey out choices that would be rejected — matching the Vue 2 old-frontend.

export const MAX_VGPU_PROFILES = 4

export const NO_VGPU_ID = 'None'

export interface VgpuLike {
  id: string
  hypervisor_groups?: number[]
}

// The hypervisor groups common to every currently-selected profile. `null` means
// "unconstrained" — either nothing is selected yet, or the selected profiles
// carry no group info (so we don't restrict). An empty set means the current
// selection is already not co-locatable (the backend will reject it), so no
// further profile can be added.
export function commonHypervisorGroups(
  selected: string[],
  allOptions: VgpuLike[]
): Set<number> | null {
  const chosen = allOptions.filter((o) => selected.includes(o.id))
  if (chosen.length === 0) return null
  let common: Set<number> | null = null
  let anyGroups = false
  for (const o of chosen) {
    const groups = o.hypervisor_groups ?? []
    if (groups.length === 0) continue
    anyGroups = true
    const set = new Set(groups)
    common = common === null ? set : new Set([...common].filter((x) => set.has(x)))
  }
  // No selected profile advertised groups → can't constrain.
  return anyGroups ? (common ?? new Set<number>()) : null
}

// Whether `option` can be toggled given the current selection. An already-selected
// option is always selectable (so the user can deselect it). Otherwise it must fit
// under the count limit and intersect the common hypervisor groups.
export function isVgpuSelectable(
  option: VgpuLike,
  selected: string[],
  allOptions: VgpuLike[],
  max: number = MAX_VGPU_PROFILES
): boolean {
  if (selected.includes(option.id)) return true
  if (selected.length >= max) return false
  const common = commonHypervisorGroups(selected, allOptions)
  if (common === null) return true // unconstrained
  if (common.size === 0) return false // current selection already not co-locatable
  const groups = option.hypervisor_groups ?? []
  if (groups.length === 0) return true // option has no group info → don't restrict
  return groups.some((g) => common.has(g))
}

export interface VgpuNumaLike extends VgpuLike {
  numa_by_group?: Record<string, number[]>
}

export type NumaSocketHint = { ok: true; node: number } | { ok: false } | null

// Informational only: NUMA placement never blocks a start.
export function numaSocketHint(selected: string[], allOptions: VgpuNumaLike[]): NumaSocketHint {
  const chosen = allOptions.filter((o) => selected.includes(o.id))
  if (chosen.length < 2) return null
  const common = commonHypervisorGroups(selected, allOptions)
  if (!common || common.size === 0) return null
  const serverIsMulti = (g: number) => {
    const nodes = new Set<number>()
    allOptions.forEach((o) => (o.numa_by_group?.[String(g)] ?? []).forEach((n) => nodes.add(n)))
    return nodes.size > 1
  }
  let sawMulti = false
  for (const g of [...common].sort((a, b) => a - b)) {
    if (!serverIsMulti(g)) continue
    sawMulti = true
    let nodes: Set<number> | null = null
    for (const o of chosen) {
      const s = new Set(o.numa_by_group?.[String(g)] ?? [])
      nodes = nodes === null ? s : new Set([...nodes].filter((x) => s.has(x)))
    }
    if (nodes && nodes.size) return { ok: true, node: Math.min(...nodes) }
  }
  return sawMulti ? { ok: false } : null
}
