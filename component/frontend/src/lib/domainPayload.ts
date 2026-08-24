import type {
  BastionRequest,
  DomainGuestPropertiesInput,
  DomainHardware,
  DomainHardwareResource,
  DomainImageFile,
  DomainImageInput,
  DomainImageOutput,
  GuestPropertiesViewersInput,
  MediaHardware,
  ReservablesInput
} from '@/gen/oas/apiv4/types.gen'

export type BootDevice = 'iso' | 'floppy' | 'disk' | 'pxe'

/** Exactly what `BastionConfigForm.getFormData()` returns. */
export interface BastionFormData {
  http?: { enabled?: boolean; httpPort: number; httpsPort: number; proxyProtocol?: boolean } | null
  ssh?: { enabled?: boolean; sshPort: number; authorizedKeys: string } | null
  customDomains?: string[]
}

/** Exactly what `DomainAccessForm.getFormData()` returns. */
export interface AccessFormData {
  credentials?: { username?: string | null; password?: string | null }
  fullscreen?: boolean
  viewers?: Record<string, { options: Record<string, unknown> | null }>
  bastion?: BastionFormData
}

/** Exactly what `DomainHardwareForm.getFormData()` returns — note the camelCase. */
export interface HardwareFormData {
  vcpus: number
  memory: number
  diskBus: string
  diskSize?: number
  /** Single value today, sent as `[videos]`. */
  videos: string
  /** Single value today, sent as `[bootOrder]`. */
  bootOrder: string
  isos?: DomainHardwareResource[]
  floppies?: DomainHardwareResource[]
  interfaces: string[]
  reservables: { vgpus?: string[] | null }
}

export function toGuestProperties(
  access: AccessFormData | undefined
): DomainGuestPropertiesInput | undefined {
  if (!access) return undefined

  return {
    credentials: access.credentials,
    fullscreen: access.fullscreen,
    viewers: access.viewers as GuestPropertiesViewersInput | undefined
  }
}

export function toDomainHardware(
  hardware: HardwareFormData | undefined
): DomainHardware | undefined {
  if (!hardware) return undefined

  return {
    vcpus: hardware.vcpus,
    memory: hardware.memory,
    disk_bus: hardware.diskBus,
    videos: [hardware.videos],
    boot_order: [hardware.bootOrder as BootDevice],
    interfaces: hardware.interfaces,
    isos: hardware.isos,
    floppies: hardware.floppies
  }
}

/** `MediaHardware` carries the disk size, nests its reservables and has no peripherals. */
export function toMediaHardware(hardware: HardwareFormData | undefined): MediaHardware | undefined {
  if (!hardware) return undefined

  return {
    vcpus: hardware.vcpus,
    memory: hardware.memory,
    disk_bus: hardware.diskBus,
    disk_size: hardware.diskSize ?? 1,
    videos: [hardware.videos],
    boot_order: [hardware.bootOrder as BootDevice],
    interfaces: hardware.interfaces,
    reservables: { vgpus: hardware.reservables?.vgpus ?? [] }
  }
}

export function toReservables(
  hardware: HardwareFormData | undefined
): ReservablesInput | undefined {
  if (!hardware) return undefined

  return { vgpus: hardware.reservables?.vgpus ?? null }
}

// BastionConfigForm reports disabled protocols as `null`, but the API only
// disables a protocol when it receives an explicit `enabled: false` payload
// (a missing/null value means "leave as is"), so both branches must always
// send a full object.
export function toBastionTarget(bastion: BastionFormData | undefined): BastionRequest | undefined {
  if (!bastion) return undefined

  return {
    http: {
      enabled: !!bastion.http?.enabled,
      http_port: bastion.http?.httpPort ?? 80,
      https_port: bastion.http?.httpsPort ?? 443,
      proxy_protocol: !!bastion.http?.proxyProtocol
    },
    ssh: {
      enabled: !!bastion.ssh?.enabled,
      port: bastion.ssh?.sshPort ?? 22,
      authorized_keys: (bastion.ssh?.authorizedKeys ?? '')
        .split('\n')
        .map((key) => key.trim())
        .filter((key) => key.length > 0)
    }
  }
}

export function toImageInput(
  image: DomainImageOutput | undefined,
  file?: DomainImageFile
): DomainImageInput | undefined {
  if (!image) return undefined

  return {
    id: image.id,
    type: image.type,
    ...(file ? { file } : {})
  }
}
