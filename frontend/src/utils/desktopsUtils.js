import { cardIcons, desktopStates } from '../shared/constants'

export class DesktopUtils {
  static parseDesktops (items) {
    return items.map((item) => {
      const { description, icon, id, name, state, type, viewers, ip, template } = item
      return {
        description,
        icon: !icon || !(icon in cardIcons) ? ['fas', 'desktop'] : this.getIcon(icon),
        id,
        name,
        state: [desktopStates.started, desktopStates.stopped, desktopStates.failed, desktopStates.waitingip, desktopStates['shutting-down']].includes(state.toLowerCase()) ? state : desktopStates.working,
        type,
        ip,
        viewers,
        template
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
        type: 'nonpersistent'
      }
    }) || []
  }

  static parseDeployments (items) {
    return items.map((item) => {
      const { id, name, startedDesktops, totalDesktops } = item
      return {
        id,
        name,
        startedDesktops,
        totalDesktops
      }
    }) || []
  }

  static parseDeployment (items) {
    return items.map((item) => {
      const { id, user, name, description, state, viewers } = item
      return {
        id,
        user,
        name,
        description,
        state,
        viewers
      }
    })
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
}
