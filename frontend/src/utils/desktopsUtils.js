import { cardIcons, desktopStates, status } from '../shared/constants'
import { DateUtils } from './dateUtils'
import i18n from '@/i18n'

export class DesktopUtils {
  static parseDesktops (items) {
    return items.map((item) => {
      return DesktopUtils.parseDesktop(item)
    }) || []
  }

  static parseDesktop (item) {
    const { description, icon, id, name, state, type, viewers, ip, template, progress, image, needs_booking: needsBooking, next_booking_start: nextBookingStart, next_booking_end: nextBookingEnd, booking_id: bookingId, editable, scheduled, server, desktop_size: desktopSize, tag, reservables } = item
    return {
      description,
      icon: !icon || !(icon in cardIcons) ? ['fas', 'desktop'] : this.getIcon(icon),
      id,
      name,
      state: this.getState(state),
      type,
      ip,
      viewers: (viewers !== undefined && viewers !== null) ? viewers : [],
      template,
      buttonIconName: this.buttonIconName(item),
      progress,
      image,
      editable,
      bookingId,
      needsBooking,
      nextBookingStart: nextBookingStart ? DateUtils.utcToLocalTime(nextBookingStart) : '',
      nextBookingEnd: nextBookingEnd ? DateUtils.utcToLocalTime(nextBookingEnd) : '',
      shutdown: scheduled.shutdown ? i18n.t('components.desktop-cards.notification-bar.shutdown', { name: name, date: DateUtils.formatAsTime(DateUtils.utcToLocalTime(scheduled.shutdown)) }) : false,
      server,
      desktopSize,
      tag,
      reservables
    }
  }

  static parseTemplates (items) {
    return items.map((item) => {
      return DesktopUtils.parseTemplate(item)
    }) || []
  }

  static parseTemplate (item) {
    const { description, icon, id, name, category, category_name: categoryName, group, group_name: groupName, user_name: userName, image, editable, allowed, enabled, desktop_size: desktopSize, status } = item
    return {
      description,
      icon: !icon || !(icon in cardIcons) ? ['fas', 'desktop'] : this.getIcon(icon),
      id,
      name,
      type: 'nonpersistent',
      buttonIconName: 'play',
      category,
      categoryName,
      group,
      groupName,
      userName,
      image,
      editable,
      allowed,
      enabled,
      desktopSize,
      status: this.getState(status)
    }
  }

  static getIcon (name) {
    return ['fab', name]
  }

  static hash (term) {
    if (term === null) return 1
    if (term === undefined) return 1

    const H = 48
    let total = 0

    for (let i = 0; i < term.length; i++) {
      total += total + term.charCodeAt(i)
    }

    return total % H + 1
  }

  static filterViewerFromList (viewers, viewer) {
    return viewers.filter(item => item !== viewer)
  }

  static buttonIconName (item) {
    const state = this.getState(item.state)
    if (item.type === 'nonpersistent' && [desktopStates.started, desktopStates.waitingip].includes(state.toLowerCase())) {
      return 'trash'
    }

    return state ? status[state.toLowerCase()].icon : status.stopped.icon
  }

  static getState (state) {
    return [desktopStates.downloading, desktopStates.started, desktopStates.stopped, desktopStates.failed, desktopStates.waitingip, desktopStates['shutting-down'], desktopStates.paused].includes(state.toLowerCase()) ? state : desktopStates.working
  }

  static viewerNeedsIp (viewer) {
    return ['file-rdpgw', 'file-rdpvpn', 'browser-rdp'].includes(viewer)
  }
}
