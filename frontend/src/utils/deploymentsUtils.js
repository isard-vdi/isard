export class DeploymentsUtils {
  static parseDeployments (items) {
    return items.map((item) => {
      return DeploymentsUtils.parseDeploymentsItem(item)
    }) || []
  }

  static parseDeploymentsItem (deployment) {
    const { id, name, startedDesktops, totalDesktops } = deployment
    return {
      id,
      name,
      startedDesktops,
      totalDesktops
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
    const { id, user, userName, userPhoto, categoryName, groupName, state, viewer, viewers } = desktop
    return {
      id,
      user,
      userName,
      userPhoto,
      categoryName,
      groupName,
      state,
      viewer,
      viewers
    }
  }
}
