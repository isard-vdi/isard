import i18n from '@/i18n'

export const apiV3Segment = '/api/v3'
export const schedulerSegment = '/scheduler'
export const apiWebSockets = '/api/v3/socket.io'
export const apiAdminSegment = '/isard-admin'
export const authenticationSegment = '/authentication'
export const appTitle = 'IsardVDI'
export const sessionCookieName = 'isardvdi_session'

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
  paused: 'paused',
  updating: 'updating',
  maintenance: 'maintenance'
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
    action: 'updating',
    icon: 'arrow-repeat'
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
  },
  restart: {
    action: 'reset',
    icon: 'power',
    variant: 'danger'
  },
  updating: {
    action: '',
    icon: 'arrow-repeat'
  },
  maintenance: {
    action: '',
    variant: 'warning'
  }
}

export const eventsTitles = {
  available: i18n.t('components.bookings.item.event-titles.available'),
  unavailable: i18n.t('components.bookings.item.event-titles.unavailable'),
  overridable: i18n.t('components.bookings.item.event-titles.overridable')
}

export const availableViewers = [
  {
    id: 'rdp',
    key: 'browser_rdp',
    type: 'browser',
    order: 3,
    needsWireguard: true
  },
  {
    id: 'vnc',
    key: 'browser_vnc',
    type: 'browser',
    order: 1,
    needsWireguard: false
  },
  {
    id: 'rdpgw',
    key: 'file_rdpgw',
    type: 'file',
    order: 4,
    needsWireguard: true
  },
  {
    id: 'rdpvpn',
    key: 'file_rdpvpn',
    type: 'file',
    order: 5,
    needsWireguard: true
  },
  {
    id: 'spice',
    key: 'file_spice',
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
  interfaces: i18n.t('forms.domain.hardware.interfaces'),
  floppies: i18n.t('forms.domain.media.floppies'),
  boot_order: i18n.t('forms.domain.hardware.boot'),
  vgpus: i18n.t('forms.domain.bookables.vgpus')
}
