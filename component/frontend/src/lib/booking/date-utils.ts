const pad2 = (n: number) => String(n).padStart(2, '0')

function toDate(input: string | Date): Date {
  if (input instanceof Date) return input
  // Accept 'YYYY-MM-DD HH:mm', 'YYYY-MM-DDTHH:mm', or any ISO string.
  return new Date(input.replace(' ', 'T'))
}

export function formatAsDate(input: string | Date): string {
  const d = toDate(input)
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

export function formatAsTime(input: string | Date): string {
  const d = toDate(input)
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

export function formatAsLocalDateTime(input: string | Date): string {
  return `${formatAsDate(input)} ${formatAsTime(input)}`
}

export function utcToLocalTime(utc: string): string {
  return formatAsLocalDateTime(new Date(utc))
}

export function localTimeToUtc(input: string | Date): string {
  return toDate(input).toISOString()
}

export function pastMonday(ref: Date = new Date()): Date {
  const d = new Date(ref)
  d.setHours(0, 0, 0, 0)
  const day = d.getDay()
  const diff = day === 0 ? -6 : 1 - day
  d.setDate(d.getDate() + diff)
  return d
}

export function nextSunday(ref: Date = new Date()): Date {
  const d = pastMonday(ref)
  d.setDate(d.getDate() + 6)
  d.setHours(23, 59, 59, 999)
  return d
}

export function getMinutesBetweenDates(start: string | Date, end: string | Date): number {
  return (toDate(end).getTime() - toDate(start).getTime()) / 60_000
}

export function addMinutes(input: string | Date, minutes: number): Date {
  const d = toDate(input)
  return new Date(d.getTime() + minutes * 60_000)
}

export function dateIsBefore(a: string | Date, b: string | Date): boolean {
  return toDate(a).getTime() < toDate(b).getTime()
}

export function dateIsAfter(a: string | Date, b: string | Date): boolean {
  return toDate(a).getTime() > toDate(b).getTime()
}
