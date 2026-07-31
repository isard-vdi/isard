// Mirrors webapp's domain_hardware.js and old-frontend's domainsUtils.js tiers.
export interface HardwareTier {
  from: number
  to: number
  step: number
}

export const VCPU_TIERS: HardwareTier[] = [
  { from: 1, to: 16, step: 1 },
  { from: 18, to: 32, step: 2 },
  { from: 36, to: 64, step: 4 },
  { from: 72, to: 128, step: 8 }
]

export const MEMORY_TIERS: HardwareTier[] = [
  { from: 0.5, to: 4, step: 0.5 },
  { from: 5, to: 16, step: 1 },
  { from: 18, to: 32, step: 2 },
  { from: 36, to: 64, step: 4 },
  { from: 72, to: 128, step: 8 },
  { from: 144, to: 256, step: 16 },
  { from: 288, to: 512, step: 32 },
  { from: 576, to: 1024, step: 64 }
]

export function buildTieredOptions(
  quotaMax: number | undefined | null,
  tiers: HardwareTier[]
): number[] {
  if (quotaMax == null || !(quotaMax > 0)) return []
  const result: number[] = []
  for (const { from, to, step } of tiers) {
    const limit = Math.min(to, quotaMax)
    if (from > limit) break
    for (let v = from; v <= limit + 1e-9; v += step) {
      result.push(+v.toFixed(2))
    }
  }
  return result
}

export function roundToNearestTier(value: number, options: number[]): number {
  if (!Number.isFinite(value) || options.length === 0) return value
  return options.reduce(
    (best, opt) => (Math.abs(opt - value) < Math.abs(best - value) ? opt : best),
    options[0]
  )
}
