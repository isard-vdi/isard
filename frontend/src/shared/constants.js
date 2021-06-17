
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
    icon: ['fas', 'stop'],
    variant: 'danger'
  },
  waitingip: {
    action: 'stop',
    icon: ['fas', 'stop'],
    variant: 'danger'
  },
  stopped: {
    action: 'start',
    icon: ['fas', 'play'],
    variant: 'success'
  },
  failed: {
    action: 'start'
  },
  working: {
  }
}
