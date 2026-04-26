import type { BrowserVncValues } from '@/gen/oas/apiv4/'

export interface VideowallDesktop {
  id: string
  userName: string
  userPhoto?: string
  state: string
  viewer?: { values: BrowserVncValues }
}

export interface VideowallDeployment {
  id: string
  name: string
  desktopName?: string
  desktops: VideowallDesktop[]
}

// Statuses where the engine guarantees a live VNC server. The videowall
// "only started" filter — and the natural unmount of <NoVNC> when desktop
// transitions out — both key off this set.
export const VIDEOWALL_ALIVE_STATES = new Set(['started', 'waitingip', 'shutting-down'])
