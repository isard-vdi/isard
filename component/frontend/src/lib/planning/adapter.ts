import { i18n } from '@/lib/i18n'
import type { CalendarEvent } from '@/lib/booking/adapter'
import { utcToLocalTime } from '@/lib/booking/date-utils'

const t = i18n.global.t

export interface ApiPlan {
  id: string
  start: string
  end: string
  units: number
  subitem_id: string
}

export function toPlanCalendarEvent(plan: ApiPlan): CalendarEvent {
  return {
    id: plan.id,
    itemId: '',
    itemType: '',
    title: `${plan.subitem_id} (${plan.units} ${t('components.bookings.item.units')})`,
    subtitle: '',
    start: utcToLocalTime(plan.start),
    end: utcToLocalTime(plan.end),
    eventType: 'unavailable',
    class: 'unavailable',
    split: 1,
    editable: true,
    units: plan.units
  }
}

export function toPlanCalendarEvents(plans: ApiPlan[] | undefined): CalendarEvent[] {
  return (plans ?? []).map(toPlanCalendarEvent)
}

export interface ApiSubitem {
  id: string
  name: string
  description?: string
  profile?: string
  units?: number
}

export interface ApiReservableItem {
  id: string
  name: string
  model?: string
  brand?: string
  description?: string
}
