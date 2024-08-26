import { DateUtils } from '@/utils/dateUtils'
import { filter } from 'lodash'
import { eventsTitles } from '../shared/constants'
import i18n from '@/i18n'

export class BookingUtils {
  static parsePriority (item) {
    const { forbid_time: forbidTime, max_time: maxTime, max_items: maxItems } = item
    return {
      forbidTime,
      maxTime,
      maxItems
    }
  }

  static parseEvents (items) {
    return items.map((item) => {
      return BookingUtils.parseEvent(item)
    }) || []
  }

  static parseEvent (item) {
    const { item_id: itemId, title, item_type: itemType, event_type: eventType, start, end, id, units } = item
    return {
      id,
      itemId,
      itemType,
      title: item.event_type === 'event' ? title : this.getItemTitle(item.event_type),
      subtitle: i18n.t('components.bookings.item.enough-units'),
      start: DateUtils.utcToLocalTime(start),
      end: DateUtils.utcToLocalTime(end),
      eventType,
      class: item.event_type,
      split: item.event_type === 'event' ? 2 : 1,
      editable: item.event_type === 'event',
      units: units
    }
  }

  static parseStartNowModal (item) {
    const { max_booking_date: maxBookingDate, showProfileDropdown, reservables_available: availableProfiles, show, profile, action } = item
    return {
      show,
      showProfileDropdown, // if the profile select must be shown
      selected: {
        profile,
        endDate: null,
        action
      },
      data: {
        availableProfiles: showProfileDropdown ? this.formatAvailableProfilesDropdown(availableProfiles) : [], // if the profile select must be shown
        availableTimes: DateUtils.breakTimeInChunks(DateUtils.dateToMoment(new Date()), DateUtils.stringToDate(DateUtils.utcToLocalTime(maxBookingDate)), 30, 'minutes'),
        maxBookingDate
      }
    }
  }

  static formatAvailableProfilesDropdown (profiles) {
    return profiles.map((item) => {
      return {
        text: item.name,
        value: { id: item.id, maxBookingDate: item.max_booking_date },
        maxBookingDate: item.max_booking_date
      }
    }) || []
  }

  static priorityAllowed (payload, priority) {
    const checkForbidTime = this.checkForbidTime(payload.start, priority.forbidTime)
    const checkMaxTime = payload.end ? this.checkMaxTime(payload.start, payload.end, priority.maxTime) : true

    if (!checkForbidTime) {
      return { priorityAllowed: false, error: i18n.t('components.bookings.errors.forbid') }
    } else if (!checkMaxTime) {
      return { priorityAllowed: false, error: i18n.t('components.bookings.errors.maximum-time') }
    }

    return { priorityAllowed: checkForbidTime && checkMaxTime, error: '' }
  }

  static checkForbidTime (date, forbidTime) {
    return date > new Date().addMinutes(parseInt(forbidTime))
  }

  static checkMaxTime (start, end, maxTime) {
    return DateUtils.getMinutesBetweenDates(start, end) <= maxTime
  }

  static canCreate (event, events) { // check if event doesn't overlap
    const filteredEvents = filter(events, function (o) { return !event.id || o.id !== event.id })

    return filteredEvents.every(item => {
      if (['available', 'overridable'].includes(item.eventType)) {
        return true
      } else if (event.end === '') { // Single click
        return DateUtils.dateIsBefore(event.start, item.start) || DateUtils.dateIsAfter(event.start, item.end)
      } else { // Click and drag or modal return
        const eventIsBefore = DateUtils.dateIsBefore(event.end, item.start)
        const eventIsAfter = DateUtils.dateIsAfter(event.start, item.end)

        return eventIsBefore || eventIsAfter
      }
    })
  }

  static getItemTitle (itemType) {
    return eventsTitles[itemType]
  }
}
