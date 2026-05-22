import { computed } from 'vue'

import {
  DesktopStatusEnum,
  type ApiSchemasDomainsDesktopsUserDesktop as UserDesktop
} from '@/gen/oas/apiv4/'

export type UserDesktopWithQueue = UserDesktop & { queue?: number }

export enum DesktopActionsEnum {
  Start = 'desktopStart',
  Stop = 'desktopStop',
  Reset = 'desktopReset',
  AbortOperation = 'desktopAbortOperation',
  UpdateStatus = 'desktopUpdateStatus',
  // StartNow = 'desktopStartNow',
  FetchBooking = 'desktopFetchBooking' // TODO: rename
}

export interface DesktopActionsData {
  actionButton: {
    icon: string
    iconClass?: string
    hierarchy: string // TODO: type this better so typescript doesn't complain
    action: DesktopActionsEnum
    label?: string
  } | null
  viewers: boolean
  text: {
    icon: string
    iconClass?: string
    iconColor: string
  } | null
}
export const desktopActionsData = (
  status: string,
  needsBooking = false,
  directViewer = false
): DesktopActionsData => {
  switch (status) {
    case DesktopStatusEnum.STOPPED:
      if (needsBooking) {
        return {
          actionButton: {
            icon: 'play',
            iconClass: 'fill-current',
            hierarchy: 'tertiary-color',
            action: DesktopActionsEnum.FetchBooking,
            label: 'components.desktops.desktop-card.status.stopped.start-now'
          },
          viewers: false,
          text: null
        }
      }
      return {
        actionButton: {
          icon: 'play',
          iconClass: 'fill-current',
          hierarchy: 'secondary-color',
          action: DesktopActionsEnum.Start
        },
        viewers: false,
        text: null
      }

    case DesktopStatusEnum.CREATING:
    case DesktopStatusEnum.CREATING_AND_STARTING:
    case DesktopStatusEnum.CREATING_DISK_FROM_SCRATCH:
    case DesktopStatusEnum.STARTING:
    case DesktopStatusEnum.STARTING_PAUSED:
    case DesktopStatusEnum.STARTING_DOMAIN_DISPOSABLE:
    case DesktopStatusEnum.STOPPING:
    case DesktopStatusEnum.FORCE_DELETING:
    case DesktopStatusEnum.DOWNLOADING:
    case DesktopStatusEnum.DOWNLOAD_STARTING:
    case DesktopStatusEnum.UPDATING:
    case DesktopStatusEnum.RESETTING:
      return {
        actionButton: null,
        viewers: false,
        text: {
          icon: 'loading-02',
          iconClass: 'animate-spin',
          iconColor: 'gray-600'
        }
      }

    case DesktopStatusEnum.STARTED:
    case DesktopStatusEnum.WAITING_IP:
      if (directViewer) {
        return {
          actionButton: {
            icon: 'refresh-cw-01',
            hierarchy: 'destructive',
            action: DesktopActionsEnum.Reset,
            label: 'components.desktops.desktop-card.actions.reset'
          },
          viewers: true,
          text: null
        }
      }
      return {
        actionButton: {
          icon: 'stop',
          hierarchy: 'destructive',
          action: DesktopActionsEnum.Stop
        },
        viewers: true,
        text: null
      }

    case DesktopStatusEnum.PAUSED:
    case DesktopStatusEnum.SUSPENDED:
      return {
        actionButton: {
          icon: 'stop',
          hierarchy: 'destructive',
          action: DesktopActionsEnum.Stop
        },
        viewers: false,
        text: {
          icon: 'pause-circle',
          iconColor: 'error-600'
        }
      }

    case DesktopStatusEnum.SHUTTING_DOWN:
      return {
        actionButton: {
          icon: 'power-01',
          hierarchy: 'destructive',
          action: DesktopActionsEnum.Stop
        },
        viewers: true,
        text: null
      }

    case DesktopStatusEnum.MAINTENANCE:
      return {
        actionButton: {
          icon: 'minus-circle',
          hierarchy: 'destructive',
          action: DesktopActionsEnum.AbortOperation
        },
        viewers: false,
        text: {
          icon: 'tool-02',
          iconColor: 'warning-600'
        }
      }

    case DesktopStatusEnum.FAILED:
    case DesktopStatusEnum.CRASHED:
      return {
        actionButton: {
          icon: 'refresh-cw-01',
          hierarchy: 'tertiary-color',
          action: DesktopActionsEnum.UpdateStatus
        },
        viewers: false,
        text: {
          icon: 'alert-circle',
          iconColor: 'error-600'
        }
      }

    case DesktopStatusEnum.DOWNLOAD_FAILED:
      return {
        actionButton: null,
        viewers: false,
        text: {
          icon: 'alert-circle',
          iconColor: 'error-600'
        }
      }

    case DesktopStatusEnum.UNKNOWN:
    default:
      return {
        actionButton: null,
        viewers: false,
        text: {
          icon: 'help-circle',
          iconColor: 'error-600'
          // TODO: add tooltip with "contact administrator" and/or the desktop status
        }
      }
  }
}

export const desktopKindStyle = (desktop: UserDesktop) => {
  const desktopKind = computed(() => {
    if (desktop.tag) {
      return 'deployment'
    }

    return desktop.type as 'persistent' | 'nonpersistent'
  })

  switch (desktopKind.value) {
    case 'persistent':
      return {
        color: 'secondary-3-500',
        icon: 'browser',
        iconColor: 'secondary-3-600'
      }
    case 'nonpersistent':
      return {
        color: 'secondary-1-500',
        icon: 'clock',
        iconColor: 'secondary-1-600'
      }
    case 'deployment':
      return {
        color: 'secondary-2-500',
        icon: 'layout-alt-04',
        iconColor: 'secondary-2-600'
      }

    default:
      return {
        color: 'error-500',
        icon: 'help-circle',
        iconColor: 'error-800'
      }
  }
}

export const desktopNeedsBooking = (desktop: UserDesktop) => {
  if (!desktop.needs_booking) {
    return false
  }

  if (desktop.next_booking_start && desktop.next_booking_end) {
    const now = new Date()
    const start = new Date(desktop.next_booking_start)
    const end = new Date(desktop.next_booking_end)

    if (start <= now && now <= end) {
      return false
    }
  }

  return true
}

export const desktopNotificationText = (desktop: UserDesktopWithQueue, t, d) => {
  if (desktop.status === DesktopStatusEnum.MAINTENANCE && desktop.current_action) {
    return t(
      `components.desktops.desktop-card.notification-bar.maintenance.${desktop.current_action}`,
      t(`components.desktops.desktop-card.notification-bar.maintenance.default`)
    )
  }

  const bookingText = desktopBookingNotificationText(desktop, t, d)
  if (bookingText) return bookingText

  if (
    (
      [
        DesktopStatusEnum.STARTED,
        DesktopStatusEnum.WAITING_IP,
        DesktopStatusEnum.STARTING
      ] as DesktopStatusEnum[]
    ).includes(desktop.status) &&
    desktop.scheduled?.shutdown &&
    desktop.needs_booking !== true
  ) {
    const shutdownDate = new Date(desktop.scheduled.shutdown)
    return t('components.desktops.desktop-card.notification-bar.shutdown', {
      date: d(shutdownDate, { dateStyle: 'short' }),
      time: d(shutdownDate, { timeStyle: 'short' })
    })
  }

  if (typeof desktop.queue === 'number' && desktop.queue > 0) {
    return t('components.desktops.desktop-card.notification-bar.queue-position', {
      position: desktop.queue
    })
  }

  return null
}

export interface DesktopNotificationData {
  status: DesktopStatusEnum | string
  needs_booking?: boolean | null
  next_booking_start?: string | null
  next_booking_end?: string | null
  scheduled?: { shutdown?: string | boolean | false | null } | null
  current_action?: string | null
}

export const desktopBookingNotificationText = (
  desktop: DesktopNotificationData,
  t,
  d
): string | null => {
  if (desktop.needs_booking === true && desktop?.next_booking_start && desktop?.next_booking_end) {
    const startDate: Date = new Date(desktop.next_booking_start)
    const endDate: Date = new Date(desktop.next_booking_end)
    const now: Date = new Date()

    if (endDate > now && startDate < now) {
      return t('components.desktops.desktop-card.notification-bar.booking-ends', {
        date: d(endDate, { dateStyle: 'short' }),
        time: d(endDate, { timeStyle: 'short' })
      })
    } else if (startDate > now) {
      return t('components.desktops.desktop-card.notification-bar.next-booking', {
        date: d(startDate, { dateStyle: 'short' }),
        time: d(startDate, { timeStyle: 'short' })
      })
    } else {
      return t('components.desktops.desktop-card.notification-bar.no-next-booking')
    }
  }

  if (desktop.needs_booking === true && desktop.status === DesktopStatusEnum.STOPPED) {
    return t('components.desktops.desktop-card.notification-bar.needs-booking')
  }

  return null
}
