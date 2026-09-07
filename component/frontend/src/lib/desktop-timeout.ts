import { ref } from 'vue'
import type { WsMessagePayload } from '@/types/ws-events'

const MSG_CODE = 'desktop-time-limit'
const LEVELS = ['info', 'warning', 'danger'] as const

export type DesktopTimeoutLevel = (typeof LEVELS)[number]

export interface DesktopTimeoutWarning {
  /** Null on vGPU/booking desktops, whose stop time is fixed by the booking. */
  desktopId: string | null
  name: string
  /** Raw ISO stop time; the modal formats it for display. */
  stopsAt: string
  level: DesktopTimeoutLevel
  /** Minutes the user may add, or null when extending is not offered. */
  extendMinutes: number | null
}

export const desktopTimeout = ref<DesktopTimeoutWarning | null>(null)

export const clearDesktopTimeout = () => {
  desktopTimeout.value = null
}

/** Maps a `msg` socket payload to a warning, or null when it is not one. */
export function parseDesktopTimeout(payload: WsMessagePayload): DesktopTimeoutWarning | null {
  if (payload?.msg_code !== MSG_CODE) return null

  const params = payload.params ?? {}
  if (typeof params.date !== 'string') return null

  const level = payload.type as DesktopTimeoutLevel
  const desktopId = typeof params.desktop_id === 'string' ? params.desktop_id : null

  return {
    desktopId,
    name: typeof params.name === 'string' ? params.name : '',
    stopsAt: params.date,
    level: LEVELS.includes(level) ? level : 'warning',
    extendMinutes: desktopId && params.extend_enabled === true ? (params.extend_time ?? 0) : null
  }
}
