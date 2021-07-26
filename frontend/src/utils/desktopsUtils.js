import { cardIcons, desktopStates, status } from '../shared/constants'

export class DesktopUtils {
  static parseDesktops (items) {
    return items.map((item) => {
      const { description, icon, id, name, state, type, viewers, ip, template } = item
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
        buttonIconName: this.buttonIconName(item)
      }
    }) || []
  }

  static parseTemplates (items) {
    return items.map((item) => {
      const { description, icon, id, name } = item
      return {
        description,
        icon: !icon || !(icon in cardIcons) ? ['fas', 'desktop'] : this.getIcon(icon),
        id,
        name,
        type: 'nonpersistent',
        buttonIconName: 'play'
      }
    }) || []
  }

  static getIcon (name) {
    return ['fab', name]
  }

  static hash (term) {
    if (term === null) return 1
    if (term === undefined) return 1

    const H = 48
    let total = 0

    for (var i = 0; i < term.length; i++) {
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
    return [desktopStates.started, desktopStates.stopped, desktopStates.failed, desktopStates.waitingip, desktopStates['shutting-down']].includes(state.toLowerCase()) ? state : desktopStates.working
  }

  static viewerNeedsIp (viewer) {
    return ['rdp', 'rdp-html5'].includes(viewer)
  }
}
