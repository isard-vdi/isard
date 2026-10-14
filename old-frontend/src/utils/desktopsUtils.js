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
    const { description, icon, id, name, type, viewers, ip, rdp, template, progress, image, needs_booking: needsBooking, next_booking_start: nextBookingStart, next_booking_end: nextBookingEnd, booking_id: bookingId, editable, scheduled, server, server_autostart: serverAutostart, tag, reservables, interfaces, current_action: currentAction, storage, permissions, queue } = item
    const out = {
      description,
      icon: icon === undefined ? undefined : (!icon || !(icon in cardIcons) ? ['fas', 'desktop'] : this.getIcon(icon)),
      id,
      name: name === undefined ? undefined : (name ? name.trim() : ''),
      state: ('state' in item || 'status' in item) ? this.parseState(item) : undefined,
      type,
      ip,
      rdp,
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
      serverAutostart,
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
    const { description, icon, id, name, category, category_name: categoryName, group, group_name: groupName, user_name: userName, image, editable, allowed, enabled, status, progress, reservables } = item
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
      progress,
      reservables
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

  static templateNeedsBooking (item) {
    return !item.state && !!((item.reservables && item.reservables.vgpus) || []).length
  }

  static viewerNeedsIp (viewer) {
    return ['file-rdpgw', 'file-rdpvpn', 'browser-rdp'].includes(viewer)
  }

  static rdpReady (desktop) {
    return !desktop.rdp || ['ready', 'unverified'].includes(desktop.rdp.state)
  }

  // Where a desktop's RDP viewers stand, for the viewer buttons to show it
  // (spinner or warning icon, the text as tooltip and as a notification on
  // click/tap) instead of adding lines to the card. ``blocked`` mirrors the
  // server: only admins and managers may open an RDP that is not verified.
  static get RDP_STATES () {
    return ['pending', 'waiting', 'refused', 'auth_failed', 'unverified']
  }

  // The vpn writes the reason as an internal code: the user gets a translated
  // sentence picked by key, and an unknown code a generic one, never the code.
  static rdpReason (reason) {
    const keys = {
      port_closed: 'port_closed',
      unreachable: 'unreachable',
      not_rdp: 'not_rdp',
      tls_required: 'tls_required',
      tls_not_allowed: 'tls_not_allowed',
      nla_required: 'nla_required',
      certificate_missing: 'certificate',
      certificate_not_allowed: 'certificate',
      security_refused: 'security_refused',
      account_blocked: 'account_blocked',
      no_credentials: 'no_credentials'
    }
    const key = typeof reason === 'string' && Object.prototype.hasOwnProperty.call(keys, reason) ? keys[reason] : 'other'
    return i18n.t(`components.desktop-cards.rdp.reason.${key}`)
  }

  static rdpViewerState (desktop, roleId) {
    const state = ((desktop && desktop.state) || '').toLowerCase()
    if (state === desktopStates.waitingip) {
      return { blocked: true, error: false, text: i18n.t('components.desktop-cards.rdp.waiting_ip') }
    }
    if (state !== desktopStates.started || !desktop.rdp) {
      return { blocked: false, error: false, text: '' }
    }
    const rdp = desktop.rdp
    const pending = !DesktopUtils.rdpReady(desktop)
    const lastFailed = !pending && !!rdp.last && !rdp.last.connected
    let text = ''
    if (lastFailed) {
      text = i18n.t(rdp.last.result === 'auth_failed' ? 'components.desktop-cards.rdp.auth_failed' : 'components.desktop-cards.rdp.last_failed')
    } else if (rdp.state === 'auth_failed' && rdp.reason === 'account_blocked') {
      text = i18n.t('components.desktop-cards.rdp.reason.account_blocked')
    } else if (rdp.state === 'unverified' && rdp.reason === 'no_credentials') {
      text = i18n.t('components.desktop-cards.rdp.reason.no_credentials')
    } else if (rdp.state !== 'ready') {
      text = DesktopUtils.RDP_STATES.includes(rdp.state) ? i18n.t(`components.desktop-cards.rdp.${rdp.state}`, { reason: DesktopUtils.rdpReason(rdp.reason) }) : ''
    }
    return {
      blocked: pending && !['admin', 'manager'].includes(roleId),
      error: ['refused', 'auth_failed'].includes(rdp.state) || lastFailed,
      text
    }
  }

  static networkNeedsIp (interfaces) {
    return (interfaces.includes('wireguard'))
  }
}
