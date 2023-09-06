import { diskBus } from '../shared/constants'
import { AllowedUtils } from './allowedUtils'

export class DomainsUtils {
  static parseDomain (item) {
    const { id, kind, name, description, guest_properties: guestProperties, hardware, reservables, image, limited_hardware: limitedHardware } = item
    return {
      id,
      kind,
      name,
      description,
      guestProperties: {
        fullscreen: guestProperties.fullscreen,
        credentials: {
          username: guestProperties.credentials.username,
          password: guestProperties.credentials.password
        },
        viewers: Object.entries(guestProperties.viewers).map(([key, value]) => ({ [key]: value }))
      },
      hardware: {
        bootOrder: hardware.boot_order,
        diskBus: hardware.disk_bus ? hardware.disk_bus : 'default',
        disks: hardware.disks,
        diskSize: hardware.disk_size,
        floppies: AllowedUtils.parseItems(hardware.floppies),
        graphics: hardware.graphics ? hardware.graphics : 'default',
        interfaces: hardware.interfaces.map(i => i.id),
        interfacesMac: hardware.interfaces.map(i => i.mac),
        isos: AllowedUtils.parseItems(hardware.isos),
        memory: parseFloat(hardware.memory),
        vcpus: parseInt(hardware.vcpus),
        videos: hardware.videos,
        quota: !hardware.quota ? { memory: 128, vcpus: 128, desktopDiskSizes: 500 } : hardware.quota
      },
      limitedHardware,
      reservables: {
        vgpus: reservables && reservables.vgpus && reservables.vgpus.length > 0 ? [reservables.vgpus[0]] : ['None']
      },
      image
    }
  }

  static parseAvailableHardware (hardware) {
    const { boot_order: bootOrder, disks, floppies, graphics, interfaces, isos, videos } = hardware
    // Unlimited default quota
    let quota = { memory: 128, vcpus: 128, desktopDiskSizes: 500 }
    if (hardware.quota !== false) {
      quota = { memory: hardware.quota.memory, vcpus: hardware.quota.vcpus, desktopDiskSizes: hardware.quota.desktops_disk_size }
    }
    const memory = []
    for (let i = 0.5; i <= quota.memory; i += 0.5) {
      memory.push(i)
    }
    const vcpus = []
    for (let i = 1; i <= quota.vcpus; i += 1) {
      vcpus.push(i)
    }

    const desktopDiskSizes = []
    for (let i = 1; i <= quota.desktopDiskSizes; i += 1) {
      desktopDiskSizes.push(i)
    }

    return {
      bootOrder,
      diskBus: diskBus,
      disks,
      diskSize: desktopDiskSizes,
      floppies,
      graphics,
      interfaces,
      isos,
      memory,
      vcpus,
      videos,
      quota
    }
  }
}
