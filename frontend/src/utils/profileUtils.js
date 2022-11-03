export class ProfileUtils {
  static parseProfile (item) {
    const { category, email, group, name, provider, quota, used, restriction_applied: restrictionApplied, role, username, photo, secondary_groups: secondaryGroups, total_disk_size: totalDiskSize } = item
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
      totalDiskSize
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
