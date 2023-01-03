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
  downloading: 'downloading',
  paused: 'paused'
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
  },
  paused: {
    action: 'stop',
    icon: 'stop',
    variant: 'success'
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

export const availableViewers = [
  {
    id: 'rdp',
    key: 'browser_rdp',
    name: i18n.t('views.select-template.viewer-name.browser-rdp'),
    type: 'browser',
    order: 3,
    needsWireguard: true
  },
  {
    id: 'vnc',
    key: 'browser_vnc',
    name: i18n.t('views.select-template.viewer-name.browser-vnc'),
    type: 'browser',
    order: 1,
    needsWireguard: false
  },
  {
    id: 'rdpgw',
    key: 'file_rdpgw',
    name: i18n.t('views.select-template.viewer-name.file-rdpgw'),
    type: 'file',
    order: 4,
    needsWireguard: true
  },
  {
    id: 'rdpvpn',
    key: 'file_rdpvpn',
    name: i18n.t('views.select-template.viewer-name.file-rdpvpn'),
    type: 'file',
    order: 5,
    needsWireguard: true
  },
  {
    id: 'spice',
    key: 'file_spice',
    name: i18n.t('views.select-template.viewer-name.file-spice'),
    type: 'file',
    order: 2,
    needsWireguard: false
  }
]

export const diskBus = [
  {
    id: 'default',
    name: 'Default'
  },
  {
    id: 'virtio',
    name: 'Virtio'
  },
  {
    id: 'ide',
    name: 'IDE'
  },
  {
    id: 'sata',
    name: 'SATA'
  }
]

export const hardwareWarningTitle = {
  videos: i18n.t('forms.domain.hardware.videos'),
  vcpus: i18n.t('forms.domain.hardware.vcpus'),
  memory: i18n.t('forms.domain.hardware.memory'),
  isos: i18n.t('forms.domain.media.isos'),
  floppies: i18n.t('forms.domain.media.floppies'),
  boot_order: i18n.t('forms.domain.hardware.boot'),
  vgpus: i18n.t('forms.domain.bookables.vgpus')
}
