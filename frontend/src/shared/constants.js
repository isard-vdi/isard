import i18n from '@/i18n'

export const apiV3Segment = '/api/v3'
export const apiWebSockets = '/api/v3/socket.io'
export const apiAdminSegment = '/isard-admin'
export const authenticationSegment = '/authentication'
export const appTitle = 'IsardVDI'

export const cardIcons = {
  default: ['fas', 'desktop'],
  windows: ['fab', 'windows'],
  ubuntu: ['fab', 'ubuntu'],
  fedora: ['fab', 'fedora'],
  linux: ['fab', 'linux'],
  centos: ['fab', 'centos']
}

export const desktopStates = {
  not_created: 'notCreated',
  failed: 'failed',
  started: 'started',
  stopped: 'stopped',
  waitingip: 'waitingip',
  working: 'working',
  'shutting-down': 'shutting-down',
  downloading: 'downloading'
}

export const status = {
  notCreated: {
    icon: ['fas', 'play'],
    variant: 'success'
  },
  started: {
    action: 'stop',
    icon: 'stop',
    variant: 'danger'
  },
  waitingip: {
    action: 'stop',
    icon: 'stop',
    variant: 'danger'
  },
  stopped: {
    action: 'start',
    icon: 'play',
    variant: 'success'
  },
  failed: {
    action: 'start',
    icon: 'play'
  },
  'shutting-down': {
    action: 'stop',
    icon: 'power',
    variant: 'danger'
  },
  working: {
    action: '',
    icon: ''
  },
  downloading: {
    action: '',
    icon: ''
  }
}

export const eventsTitles = {
  available: i18n.t('components.bookings.item.event-titles.available'),
  unavailable: i18n.t('components.bookings.item.event-titles.unavailable'),
  overridable: i18n.t('components.bookings.item.event-titles.overridable')
}

export const mediaStatus = {
  DownloadFailed: i18n.t('views.media.status.download-failed'),
  Downloaded: i18n.t('views.media.status.downloaded'),
  Downloading: i18n.t('views.media.status.downloading'),
  Deleting: i18n.t('views.media.status.deleting')
}
