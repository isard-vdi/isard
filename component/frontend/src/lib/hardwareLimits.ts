export interface LimitedHardwareValue {
  old_value: unknown
  new_value: unknown
}

export type LimitedHardware = Record<string, LimitedHardwareValue>

/** Values arrive as scalars, `{id, name}` objects or arrays of either. */
export function formatLimitedValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => formatLimitedValue(item)).join(', ')
  }
  if (value && typeof value === 'object') {
    const item = value as Record<string, unknown>
    return String(item.name ?? item.id ?? '')
  }
  return value === undefined || value === null ? '' : String(value)
}

export function limitedValueCount(value: unknown): number {
  if (Array.isArray(value)) return value.length
  return value === undefined || value === null ? 0 : 1
}

/**
 * The API empties the list instead of swapping a value when the restricted item
 * has no fallback (interfaces, ISOs, floppies).
 */
export function isLimitedRemoval(limited: LimitedHardwareValue): boolean {
  return limitedValueCount(limited.new_value) === 0
}
