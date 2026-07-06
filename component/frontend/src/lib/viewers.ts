export const WIREGUARD_REQUIRING_VIEWERS = ['browser_rdp', 'file_rdpgw', 'file_rdpvpn'] as const

export type WireguardRequiringViewer = (typeof WIREGUARD_REQUIRING_VIEWERS)[number]

export function hasWireguardRequiringViewer(viewers: readonly string[]): boolean {
  return viewers.some((v) => (WIREGUARD_REQUIRING_VIEWERS as readonly string[]).includes(v))
}

export function stripWireguardRequiringViewers(viewers: readonly string[]): string[] {
  return viewers.filter((v) => !(WIREGUARD_REQUIRING_VIEWERS as readonly string[]).includes(v))
}

export function getWireguardRequiringViewers(viewers: readonly string[]): string[] {
  return viewers.filter((v) => (WIREGUARD_REQUIRING_VIEWERS as readonly string[]).includes(v))
}

export function selectedViewerKeys(viewers: Record<string, unknown> | null | undefined): string[] {
  return Object.entries(viewers ?? {})
    .filter(([, value]) => value != null)
    .map(([key]) => key)
}
