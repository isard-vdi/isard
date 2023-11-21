import { DateUtils } from './dateUtils'
import i18n from '@/i18n'
export class RecycleBinUtils {
  static parseRecycleBinList (items) {
    return items.map((item) => {
      return RecycleBinUtils.parseRecycleBinListItem(item)
    }) || []
  }

  static parseRecycleBinListItem (item) {
    const {
      id,
      accessed,
      item_type: itemType,
      item_name: itemName,
      agent_name: agentName,
      agent_id: agentId,
      status,
      desktops,
      templates,
      deployments,
      storages,
      logs
    } = item
    return {
      id,
      accessed,
      itemType,
      itemName: itemType === 'bulk' ? i18n.t('views.recycle-bins.item-type.bulk') : itemName,
      agentName,
      agentId,
      status,
      desktops,
      templates,
      deployments,
      storages,
      size: Math.round(item.size / 1024 / 1024 / 1024) + ' GB',
      logs
    }
  }

  static parseRecycleBin (item) {
    const {
      id,
      accessed,
      item_name: itemName,
      item_type: itemType,
      agent_name: agentName,
      agent_id: agentId,
      desktops,
      deployments,
      templates,
      storages
    } = item
    return {
      id,
      accessed,
      itemName: itemType === 'bulk' ? i18n.t('views.recycle-bins.item-type.bulk') : itemName,
      itemType,
      agentName,
      agentId,
      size: Math.round(item.size / 1024 / 1024 / 1024) + ' GB',
      desktops: RecycleBinUtils.parseRecycleBinDesktops(desktops),
      deployments: RecycleBinUtils.parseRecycleBinDeployments(deployments),
      templates: RecycleBinUtils.parseRecycleBinTemplates(templates),
      storages: RecycleBinUtils.parseRecycleBinStorages(storages)
    }
  }

  static parseRecycleBinDesktops (items) {
    return items.map((item) => {
      return RecycleBinUtils.parseRecycleBinDesktop(item)
    }) || []
  }

  static parseRecycleBinDesktop (item) {
    const {
      id,
      name,
      accessed,
      category,
      group,
      username
    } = item
    return {
      id,
      name,
      accessed,
      category,
      group,
      username
    }
  }

  static parseRecycleBinTemplates (items) {
    return items.map((item) => {
      return RecycleBinUtils.parseRecycleBinTemplate(item)
    }) || []
  }

  static parseRecycleBinTemplate (item) {
    const {
      id,
      name,
      accessed,
      category,
      group,
      username
    } = item
    return {
      id,
      name,
      accessed,
      category,
      group,
      username
    }
  }

  static parseRecycleBinDeployments (items) {
    return items.map((item) => {
      return RecycleBinUtils.parseRecycleBinDeployment(item)
    }) || []
  }

  static parseRecycleBinDeployment (item) {
    const desktopName = item.create_dict.name
    const {
      id,
      name,
      category,
      group,
      user
    } = item
    return {
      id,
      name,
      desktopName,
      category,
      group,
      user
    }
  }

  static parseRecycleBinStorages (items) {
    return items.map((item) => {
      return RecycleBinUtils.parseRecycleBinStorage(item)
    }) || []
  }

  static parseRecycleBinStorage (item) {
    const size = item['qemu-img-info'] !== undefined ? Math.round(item['qemu-img-info']['virtual-size'] / 1024 / 1024 / 1024) + ' GB' : '-'
    const used = item['qemu-img-info'] !== undefined ? Math.round(item['qemu-img-info']['actual-size'] / 1024 / 1024 / 1024) + ' GB' : '-'
    const {
      id,
      directory_path: path,
      status,
      type: format,
      parent,
      user,
      category,
      domains
    } = item
    return {
      id,
      path,
      status,
      format,
      size,
      used,
      parent,
      user,
      category,
      domains
    }
  }

  static parseMaxTime (maxTime) {
    if (maxTime !== 'null') {
      maxTime = parseInt(maxTime)
      if (maxTime) {
        return DateUtils.humanize(maxTime, 'hours')
      }
    }
    return maxTime
  }
}
