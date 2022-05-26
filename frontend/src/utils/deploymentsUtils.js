export class DeploymentsUtils {
  static parseDeployments (items) {
    return items.map((item) => {
      return DeploymentsUtils.parseDeploymentsItem(item)
    }) || []
  }

  static parseDeploymentsItem (deployment) {
    const { id, name, startedDesktops, totalDesktops, visible } = deployment
    return {
      id,
      name,
      startedDesktops,
      totalDesktops,
      visible
    }
  }

  static parseDeployment (deployment) {
    const { id, name, description } = deployment
    const desktops = deployment.desktops.map((desktop) => {
      return DeploymentsUtils.parseDeploymentDesktop(desktop)
    })
    const desktopName = deployment.desktop_name
    return { id, name, desktops, description, desktopName }
  }

  static parseDeploymentDesktop (desktop) {
    const { id, ip, user, userName, userPhoto, categoryName, groupName, state, viewer, viewers, image } = desktop
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
      viewers
    }
  }
}
