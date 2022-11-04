import i18n from '@/i18n'
import { DateUtils } from './dateUtils'

export class DirectViewerUtils {
  static parseDirectViewer (item) {
    const { vmName: name, vmDescription: description, viewers, vmState: state, scheduled, jwt, desktopId, needs_booking: needsBooking, next_booking_start: nextBookingStart, next_booking_end: nextBookingEnd } = item
    return {
      name,
      description,
      viewers,
      state,
      shutdown: scheduled && scheduled.shutdown ? i18n.t('message-modal.messages.desktop-time-limit', { name: name, date: DateUtils.formatAsTime(DateUtils.utcToLocalTime(scheduled.shutdown)) }) : false,
      jwt,
      desktopId,
      needsBooking,
      nextBookingStart: nextBookingStart ? DateUtils.utcToLocalTime(nextBookingStart) : '',
      nextBookingEnd: nextBookingEnd ? DateUtils.utcToLocalTime(nextBookingEnd) : ''
    }
  }
}
