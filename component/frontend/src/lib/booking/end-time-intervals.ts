export interface BookableProfile {
  id: string
  max_booking_date: string
}

export function earliestBookingDate(
  profiles: BookableProfile[],
  selectedIds: string[]
): Date | null {
  const selected = profiles.filter((p) => selectedIds.includes(p.id))
  if (!selected.length) return null
  const earliest = Math.min(...selected.map((p) => new Date(p.max_booking_date).getTime()))
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
