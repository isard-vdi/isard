import { diskBus } from '../shared/constants'
import { AllowedUtils } from './allowedUtils'
import { ImageUtils } from './imageUtils'

// Dropdown ceilings (1 TB RAM, 128 vCPU, 2 TB disk) with coarsening steps so
// the option list stays bounded even when the quota is the "unlimited" sentinel.
const MEMORY_TIERS = [
  { from: 0.5, to: 4, step: 0.5 },
  { from: 5, to: 16, step: 1 },
  { from: 18, to: 32, step: 2 },
  { from: 36, to: 64, step: 4 },
  { from: 72, to: 128, step: 8 },
  { from: 144, to: 256, step: 16 },
  { from: 288, to: 512, step: 32 },
  { from: 576, to: 1024, step: 64 }
]
const VCPU_TIERS = [
  { from: 1, to: 16, step: 1 },
  { from: 18, to: 32, step: 2 },
  { from: 36, to: 64, step: 4 },
  { from: 72, to: 128, step: 8 }
]
const DISK_TIERS = [
  { from: 1, to: 16, step: 1 },
  { from: 18, to: 32, step: 2 },
  { from: 36, to: 64, step: 4 },
  { from: 72, to: 128, step: 8 },
  { from: 144, to: 256, step: 16 },
  { from: 288, to: 512, step: 32 },
  { from: 576, to: 1024, step: 64 },
  { from: 1152, to: 2048, step: 128 }
]

function buildTieredOptions (quotaMax, tiers) {
  if (quotaMax == null || !(quotaMax > 0)) return []
  const result = []
  for (const { from, to, step } of tiers) {
    const limit = Math.min(to, quotaMax)
    if (from > limit) break
    for (let v = from; v <= limit + 1e-9; v += step) {
      result.push(+v.toFixed(2))
    }
  }
  return result
}

// Snap a non-tier-aligned legacy value to the nearest dropdown option so the
// form submits a valid value. Ties break low.
function roundToNearestTier (value, tiers, quotaMax) {
  if (value == null || !Number.isFinite(value)) return value
  const options = buildTieredOptions(quotaMax, tiers)
  if (options.length === 0) return value
  let best = options[0]
  let bestDiff = Math.abs(options[0] - value)
  for (let i = 1; i < options.length; i++) {
    const diff = Math.abs(options[i] - value)
    if (diff < bestDiff) {
      best = options[i]
      bestDiff = diff
    }
  }
  return best
}

export class DomainsUtils {
  static parseDomain (item) {
    const { id, kind, name, description, guest_properties: guestProperties, hardware, reservables, image, limited_hardware: limitedHardware } = item
    const rawQuota = hardware.quota
    const quotaMemory = rawQuota ? rawQuota.memory : 128
    const quotaVcpus = rawQuota ? rawQuota.vcpus : 128
    const quotaDiskSize = rawQuota ? rawQuota.desktops_disk_size : 500
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
        diskSize: roundToNearestTier(parseFloat(hardware.disk_size), DISK_TIERS, quotaDiskSize),
        floppies: AllowedUtils.parseItems(hardware.floppies),
        graphics: hardware.graphics ? hardware.graphics : 'default',
        interfaces: hardware.interfaces.map(i => i.id),
        interfacesMac: hardware.interfaces.map(i => i.mac),
        isos: AllowedUtils.parseItems(hardware.isos),
        memory: roundToNearestTier(parseFloat(hardware.memory), MEMORY_TIERS, quotaMemory),
        vcpus: roundToNearestTier(parseInt(hardware.vcpus), VCPU_TIERS, quotaVcpus),
        videos: hardware.videos,
        quota: !hardware.quota ? { memory: 128, vcpus: 128, desktopDiskSizes: 500 } : hardware.quota
      },
      limitedHardware,
      reservables: {
        vgpus: reservables && reservables.vgpus && reservables.vgpus.length > 0 ? [...reservables.vgpus] : ['None']
      },
      image: image ? ImageUtils.parseImage(image) : {}
    }
  }

  static parseAvailableHardware (hardware) {
    const { boot_order: bootOrder, disks, floppies, graphics, interfaces, isos, videos } = hardware
    // Unlimited default quota
    let quota = { memory: 128, vcpus: 128, desktopDiskSizes: 500 }
    if (hardware.quota !== false) {
      quota = { memory: hardware.quota.memory, vcpus: hardware.quota.vcpus, desktopDiskSizes: hardware.quota.desktops_disk_size }
    }
    const memory = buildTieredOptions(quota.memory, MEMORY_TIERS)
    const vcpus = buildTieredOptions(quota.vcpus, VCPU_TIERS)
    const desktopDiskSizes = buildTieredOptions(quota.desktopDiskSizes, DISK_TIERS)

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
