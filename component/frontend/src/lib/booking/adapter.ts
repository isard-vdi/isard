import type {
  AvailabilityResponse,
  BookingEventResponse,
  UserBookingResponse
} from '@/gen/oas/apiv4'
import type { Role } from '@/lib/auth'
import { i18n } from '@/lib/i18n'
import {
  BOOKING_SPLIT_AVAILABILITY,
  BOOKING_SPLIT_EVENTS,
  type BookingEventClass,
  type BookingTimeframe,
  type BookingViewType
} from './constants'
import {
  utcToLocalTime,
  getMinutesBetweenDates,
  addMinutes,
  dateIsBefore,
  dateIsAfter
} from './date-utils'

export interface CalendarEvent {
  id: string
  itemId: string
  itemType: string
  title: string
  subtitle: string
  start: string
  end: string
  eventType: string
  class: BookingEventClass
  split: 1 | 2
  editable: boolean
  units: number
}

export type ApiBookingInput = UserBookingResponse | BookingEventResponse | AvailabilityResponse

interface ApiBookingShape {
  id?: string
  item_id?: string
  item_type?: string
  title?: string
  start: string
  end: string
  event_type?: string
  units: number | 'Enough' | string
}

const t = i18n.global.t

function getItemTitle(eventType: string | undefined): string {
  switch (eventType) {
    case 'available':
      return t('components.bookings.item.event-titles.available')
    case 'unavailable':
      return t('components.bookings.item.event-titles.unavailable')
    case 'overridable':
      return t('components.bookings.item.event-titles.overridable')
    default:
      return ''
  }
}

export function toCalendarEvent(input: ApiBookingInput): CalendarEvent {
  const item = input as ApiBookingShape
  const eventType = item.event_type ?? 'event'
  const eventClass = (
    ['event', 'available', 'overridable', 'unavailable'].includes(eventType) ? eventType : 'event'
  ) as BookingEventClass
  const units = typeof item.units === 'number' ? item.units : 0
  return {
    id: item.id ?? '',
    itemId: item.item_id ?? '',
    itemType: item.item_type ?? '',
    title: eventType === 'event' ? (item.title ?? '') : getItemTitle(eventType),
    subtitle: t('components.bookings.item.enough-units'),
    start: utcToLocalTime(item.start),
    end: utcToLocalTime(item.end),
    eventType,
    class: eventClass,
    split: eventType === 'event' ? BOOKING_SPLIT_EVENTS : BOOKING_SPLIT_AVAILABILITY,
    editable: eventType === 'event',
    units
  }
}

export function toCalendarEvents(items: ApiBookingInput[] | undefined): CalendarEvent[] {
  return (items ?? []).map(toCalendarEvent)
}

export interface BookingPriority {
  forbidTime: number
  maxTime: number
  maxItems: number
}

export function parsePriority(raw: {
  forbid_time?: number
  max_time?: number
  max_items?: number
}): BookingPriority {
  return {
    forbidTime: raw.forbid_time ?? 0,
    maxTime: raw.max_time ?? 0,
    maxItems: raw.max_items ?? 0
  }
}

export function checkForbidTime(start: string | Date, forbidTime: number): boolean {
  return dateIsAfter(start, addMinutes(new Date(), forbidTime))
}

export function checkMaxTime(start: string | Date, end: string | Date, maxTime: number): boolean {
  return getMinutesBetweenDates(start, end) <= maxTime
}

export function priorityAllowed(
  payload: { start: string | Date; end?: string | Date },
  priority: BookingPriority
): { allowed: boolean; error: string } {
  if (!checkForbidTime(payload.start, priority.forbidTime)) {
    return { allowed: false, error: t('components.bookings.errors.forbid') }
  }
  if (payload.end && !checkMaxTime(payload.start, payload.end, priority.maxTime)) {
    return { allowed: false, error: t('components.bookings.errors.maximum-time') }
  }
  return { allowed: true, error: '' }
}

export function canCreate(
  candidate: { id?: string; start: string | Date; end?: string | Date },
  events: CalendarEvent[]
): boolean {
  return events.every((other) => {
    if (candidate.id && other.id === candidate.id) return true
    if (other.eventType === 'available' || other.eventType === 'overridable') return true
    if (!candidate.end) {
      return dateIsBefore(candidate.start, other.start) || dateIsAfter(candidate.start, other.end)
    }
    return dateIsBefore(candidate.end, other.start) || dateIsAfter(candidate.start, other.end)
  })
}

type RolePermissionMatrix = Record<
  Role,
  Record<BookingTimeframe, Record<Exclude<BookingViewType, 'summary'>, boolean>>
>

const uniformRoleMatrix = (value: {
  month: { item: boolean; resume: boolean }
  week: { item: boolean; resume: boolean }
  day: { item: boolean; resume: boolean }
}): RolePermissionMatrix => ({
  admin: value,
  manager: value,
  advanced: value,
  user: value
})

export const bookingEventsSettings = {
  eventClickActive: uniformRoleMatrix({
    month: { item: true, resume: false },
    week: { item: true, resume: false },
    day: { item: true, resume: false }
  }),
  cellDoubleClickActive: uniformRoleMatrix({
    month: { item: false, resume: false },
    week: { item: true, resume: false },
    day: { item: true, resume: false }
  }),
  cellDragActive: uniformRoleMatrix({
    month: { item: false, resume: false },
    week: { item: true, resume: false },
    day: { item: true, resume: false }
  }),
  showAvailabilitySplit: uniformRoleMatrix({
    month: { item: false, resume: false },
    week: { item: true, resume: false },
    day: { item: true, resume: false }
  })
}

export function getPermission(
  kind: keyof typeof bookingEventsSettings,
  role: Role,
  timeframe: BookingTimeframe,
  viewType: Exclude<BookingViewType, 'summary'>
): boolean {
  return bookingEventsSettings[kind][role][timeframe][viewType]
}
