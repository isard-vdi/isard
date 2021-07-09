export const apiV3Segment = '/api/v3'
export const apiWebSockets = '/api/v3/socket.io'
export const apiAdminSegment = '/isard-admin'
export const authenticationSegment = '/authentication'

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
  'shutting-down': 'shutting-down'
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
    action: '',
    icon: ''
  },
  working: {
    action: '',
    icon: ''
  }
}
