export class ProfileUtils {
  static parseProfile (item) {
    const { category_name: category, email, group_name: group, name, provider, quota, used, restriction_applied: restrictionApplied, role_name: role, username, photo, secondary_groups: secondaryGroups, total_disk_size: totalDiskSize, user_storage: userStorage, email_verified: emailVerified } = item
    return {
      category,
      email,
      group,
      name,
      provider,
      used: used ? this.parseQuota(used) : false,
      quota: quota ? this.parseQuota(quota) : false,
      restrictionApplied,
      role,
      username,
      photo,
      secondaryGroups: secondaryGroups.length > 0 ? this.parseSecondaryGroups(secondaryGroups) : '-',
      totalDiskSize,
      userStorage: {
        tokenWeb: userStorage ? userStorage.token_web : false,
        providerQuota: userStorage ? userStorage.provider_quota : false
      },
      emailVerified
    }
  }

  static parseSecondaryGroups (secondaryGroups) {
    return secondaryGroups.join(', ')
  }

  static parseQuota (quota) {
    const {
      desktops, volatile, templates, isos, deployments_total: deploymentsTotal, deployment_desktops: deploymentDesktops, started_deployment_desktops: startedDeploymentDesktops, memory, running, vcpus, total_size: totalSize, total_soft_size: totalSoftSize, storage_size: storageSize, media_size: mediaSize
    } = quota
    return {
      desktops,
      volatile,
      templates,
      isos,
      deploymentsTotal,
      deploymentDesktops,
      startedDeploymentDesktops,
      memory,
      running,
      vcpus,
      totalSize,
      totalSoftSize,
      storageSize,
      mediaSize
    }
  }
}
