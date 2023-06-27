export class ProfileUtils {
  static parseProfile (item) {
    const { category_name: category, email, group_name: group, name, provider, quota, used, restriction_applied: restrictionApplied, role_name: role, username, photo, secondary_groups: secondaryGroups, total_disk_size: totalDiskSize, user_storage: userStorage } = item
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
      }
    }
  }

  static parseSecondaryGroups (secondaryGroups) {
    return secondaryGroups.join(', ')
  }

  static parseQuota (quota) {
    const {
      desktops, templates, isos, memory, running, vcpus, total_size: totalSize, total_soft_size: totalSoftSize, storage_size: storageSize, media_size: mediaSize
    } = quota
    return {
      desktops,
      templates,
      isos,
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
