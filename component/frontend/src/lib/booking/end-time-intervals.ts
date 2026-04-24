export function getEndTimeIntervals(endTime: Date): Date[] {
  const currentTime = new Date()
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
