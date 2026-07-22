import { cardIcons, desktopStates, status } from '../shared/constants'
import { DateUtils } from './dateUtils'
import i18n from '@/i18n'

export class DesktopUtils {
  static parseDesktops (items) {
    return items.map((item) => {
      return DesktopUtils.parseDesktop(item)
    }) || []
  }

  static parseDesktop (item, { partial = false } = {}) {
    // ``partial`` controls how the WS update handler folds change-handler
    // payloads into the cache. The change-handler emits with
    // ``model_dump(exclude_none=True)``, so optional fields the row
    // doesn't carry (next_booking_*, server, scheduled) arrive missing
    // from the payload. The full-row branch fills them with computed
    // defaults (icon=['fas','desktop'], name='', viewers=[], state=working,
    // shutdown=false, ...) and ``Object.assign`` then clobbers the
    // cached row. In ``partial`` mode the parser keeps only the keys
    // that were actually present so the merge doesn't lose data.
    // Same pattern that hits templates also hits desktops on partial
    // updates like booking-state changes.
    const { description, icon, id, name, type, viewers, ip, template, progress, image, needs_booking: needsBooking, next_booking_start: nextBookingStart, next_booking_end: nextBookingEnd, booking_id: bookingId, editable, scheduled, server, tag, reservables, interfaces, current_action: currentAction, storage, permissions, queue } = item
    const out = {
      description,
      icon: icon === undefined ? undefined : (!icon || !(icon in cardIcons) ? ['fas', 'desktop'] : this.getIcon(icon)),
      id,
      name: name === undefined ? undefined : (name ? name.trim() : ''),
      state: ('state' in item || 'status' in item) ? this.parseState(item) : undefined,
      type,
      ip,
      viewers: viewers === undefined ? undefined : (viewers === null ? [] : viewers),
      template,
      buttonIconName: ('state' in item || 'status' in item) ? this.buttonIconName(item) : undefined,
      progress,
      image,
      editable,
      bookingId,
      needsBooking,
      nextBookingStart: nextBookingStart === undefined ? undefined : (nextBookingStart ? DateUtils.utcToLocalTime(nextBookingStart) : ''),
      nextBookingEnd: nextBookingEnd === undefined ? undefined : (nextBookingEnd ? DateUtils.utcToLocalTime(nextBookingEnd) : ''),
      // ``scheduled`` is required by the full-row schema; in partial
      // mode the field is optional so the existing cached shutdown
      // string survives.
      shutdown: scheduled === undefined ? undefined : (scheduled.shutdown ? i18n.t('components.desktop-cards.notification-bar.shutdown', { name: name, date: DateUtils.formatAsTime(DateUtils.utcToLocalTime(scheduled.shutdown)) }) : false),
      server,
      tag,
      reservables,
      interfaces,
      currentAction,
      storage,
      permissions,
      queue
    }
    if (!partial) return out
    return Object.fromEntries(Object.entries(out).filter(([, v]) => v !== undefined))
  }

  static parseState (item) {
    const state = item.state || item.status
    return this.getState(state)
  }

  static parseTemplates (items) {
    return items.map((item) => {
      return DesktopUtils.parseTemplate(item)
    }) || []
  }

  static parseTemplate (item, { partial = false } = {}) {
    // ``partial`` controls how the WS update handler folds change-handler
    // payloads into the cache. When the change-handler emits a partial
    // row (e.g. only ``{id, enabled}`` after a visibility flip), the
    // full-row branch fills missing fields with defaults — empty
    // ``name``, default icon, ``status: working`` — and ``Object.assign``
    // then clobbers the cached row ("data disappears from the table"
    // when toggling template visibility). In ``partial`` mode we keep
    // only the keys that were actually present in the payload.
    const { description, icon, id, name, category, category_name: categoryName, group, group_name: groupName, user_name: userName, image, editable, allowed, enabled, status, progress } = item
    const out = {
      description,
      icon: icon === undefined ? undefined : (!icon || !(icon in cardIcons) ? ['fas', 'desktop'] : this.getIcon(icon)),
      id,
      name: name === undefined ? undefined : (name ? name.trim() : ''),
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
      status: status === undefined ? undefined : this.getState(status),
      // Forwarded so Templates.vue can render a progress bar while the
      // apiv4 task chain is creating the template (move/rsync stage).
      progress
    }
    if (!partial) return out
    return Object.fromEntries(Object.entries(out).filter(([, v]) => v !== undefined))
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
    const state = this.getState(item.state || item.status)
    if (!state) return status.stopped.icon
    if (item.type === 'nonpersistent' && [desktopStates.started, desktopStates.waitingip].includes(state.toLowerCase())) {
      return 'trash'
    }

    return state ? (status[state.toLowerCase()] || status.stopped).icon : status.stopped.icon
  }

  static getState (state) {
    // Treat missing/null state as a transient "working" so the card shows the
    // spinner instead of "Temporarily unavailable" during the brief window
    // where a callsite hasn't been handed a state yet.
    if (!state) return desktopStates.working
    return [desktopStates.downloading, desktopStates.started, desktopStates.stopped, desktopStates.failed, desktopStates.waitingip, desktopStates['shutting-down'], desktopStates.paused, desktopStates.maintenance, desktopStates.unknown, desktopStates.verifying, desktopStates.updating, desktopStates.creatingTemplate].includes(state.toLowerCase()) ? state : desktopStates.working
  }

  static viewerNeedsIp (viewer) {
    return ['file-rdpgw', 'file-rdpvpn', 'browser-rdp'].includes(viewer)
  }

  static networkNeedsIp (interfaces) {
    return (interfaces.includes('wireguard'))
  }
}
