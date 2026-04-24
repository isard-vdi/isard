export const BOOKING_SPLIT_AVAILABILITY = 1
export const BOOKING_SPLIT_EVENTS = 2

export const BOOKING_EVENT_CLASSES = ['event', 'available', 'overridable', 'unavailable'] as const
export type BookingEventClass = (typeof BOOKING_EVENT_CLASSES)[number]

export type BookingReturnType = 'all' | 'event' | 'availability'

export type BookingTimeframe = 'month' | 'week' | 'day'
export type BookingViewType = 'item' | 'resume' | 'summary'

export type BookingItemType = 'desktop' | 'deployment' | 'all'
