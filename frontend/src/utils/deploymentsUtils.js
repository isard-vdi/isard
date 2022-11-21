import { DesktopUtils } from './desktopsUtils'

export class DeploymentsUtils {
  static parseDeployments (items) {
    return items.map((item) => {
      return DeploymentsUtils.parseDeploymentsItem(item)
    }) || []
  }

  static parseDeploymentsItem (deployment) {
    const { id, name, description, startedDesktops, totalDesktops, visible, needs_booking: needsBooking, desktop_name: desktopName, template } = deployment
    return {
      id,
      name,
      description,
      startedDesktops,
      totalDesktops,
      visible,
      needsBooking,
      desktopName,
      template
    }
  }

  static parseDeployment (deployment) {
    const { id, name, desktop_name: desktopName, description, visible } = deployment
    const desktops = deployment.desktops
      ? deployment.desktops.map((desktop) => {
        return DeploymentsUtils.parseDeploymentDesktop(desktop)
      })
      : []
    return { id, name, desktops, description, desktopName, visible }
  }

  static parseDeploymentDesktop (desktop) {
    const { id, ip, user, userName, userPhoto, categoryName, groupName, state, viewer, viewers, image, accessed } = desktop
    return {
      id,
      ip,
      user,
      userName,
      userPhoto,
      categoryName,
      groupName,
      image,
      state,
      viewer,
      viewers,
      buttonIconName: desktop.state ? DesktopUtils.buttonIconName(desktop) : '',
      last: accessed
    }
  }
}
