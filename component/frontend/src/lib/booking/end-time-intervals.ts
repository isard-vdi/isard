export interface BookableProfile {
  id: string
  max_booking_date: string
}

// The API sends `+0000`; only `+00:00` is in the ECMAScript date format, so
// other offsets are left to each engine's fallback parser.
const parseBookingDate = (value: string): Date =>
  new Date(value.replace(/([+-]\d{2})(\d{2})$/, '$1:$2'))

export function earliestBookingDate(
  profiles: BookableProfile[],
  selectedIds: string[]
): Date | null {
  const selected = profiles.filter((p) => selectedIds.includes(p.id))
  if (!selected.length) return null
  const earliest = Math.min(...selected.map((p) => parseBookingDate(p.max_booking_date).getTime()))
  return Number.isNaN(earliest) ? null : new Date(earliest)
}

export function getEndTimeIntervals(endTime: Date): Date[] {
  const currentTime = new Date()
  currentTime.setSeconds(0, 0)
  if (endTime <= currentTime) return []

  currentTime.setMinutes(currentTime.getMinutes() + 30)
  if (endTime <= currentTime) return [endTime]

  const intervals: Date[] = []
  while (currentTime < endTime) {
    intervals.push(new Date(currentTime))
    currentTime.setMinutes(currentTime.getMinutes() + 30)
  }
  return intervals
}

export function missingBookableProfiles(
  profiles: BookableProfile[],
  selectedIds: string[]
): string[] {
  const available = new Set(profiles.map((p) => p.id))
  return selectedIds.filter((id) => !available.has(id))
}
