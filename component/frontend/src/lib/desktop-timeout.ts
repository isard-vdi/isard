import { ref } from 'vue'
import type { WsMessagePayload } from '@/types/ws-events'

const MSG_CODE = 'desktop-time-limit'
const LEVELS = ['info', 'warning', 'danger'] as const

export type DesktopTimeoutLevel = (typeof LEVELS)[number]

export interface DesktopTimeoutWarning {
  /** One warning is kept per key: a newer one for the same desktop replaces the older. */
  key: string
  /** Null when the backend does not say which desktop the warning is about. */
  desktopId: string | null
  name: string
  /** Raw ISO stop time; the modal formats it for display. */
  stopsAt: string
  level: DesktopTimeoutLevel
  /** Minutes the user may add, or null when extending is not offered. */
  extendMinutes: number | null
}

export const desktopTimeouts = ref<DesktopTimeoutWarning[]>([])

export const addDesktopTimeout = (warning: DesktopTimeoutWarning) => {
  const index = desktopTimeouts.value.findIndex((w) => w.key === warning.key)
  if (index === -1) {
    desktopTimeouts.value = [...desktopTimeouts.value, warning]
  } else {
    desktopTimeouts.value = desktopTimeouts.value.map((w, i) => (i === index ? warning : w))
  }
}

export const removeDesktopTimeout = (key: string) => {
  desktopTimeouts.value = desktopTimeouts.value.filter((w) => w.key !== key)
}

export const removeDesktopTimeoutsOf = (desktopId: string) => {
  desktopTimeouts.value = desktopTimeouts.value.filter((w) => w.desktopId !== desktopId)
}

export const clearDesktopTimeouts = () => {
  desktopTimeouts.value = []
}

export const highestDesktopTimeoutLevel = (
  warnings: DesktopTimeoutWarning[]
): DesktopTimeoutLevel =>
  warnings.reduce<DesktopTimeoutLevel>(
    (highest, w) => (LEVELS.indexOf(w.level) > LEVELS.indexOf(highest) ? w.level : highest),
    'info'
  )

/** Drops a desktop's warnings once its scheduled stop time has moved past the one they announce. */
export const removeDesktopTimeoutsSupersededBy = (desktopId: string, shutdown: unknown) => {
  if (typeof shutdown !== 'string') return
  const scheduledAt = new Date(shutdown).getTime()

  desktopTimeouts.value = desktopTimeouts.value.filter(
    (w) => w.desktopId !== desktopId || !(scheduledAt > new Date(w.stopsAt).getTime())
  )
}

/** Maps a `msg` socket payload to a warning, or null when it is not one. */
export function parseDesktopTimeout(payload: WsMessagePayload): DesktopTimeoutWarning | null {
  if (payload?.msg_code !== MSG_CODE) return null

  const params = payload.params ?? {}
  if (typeof params.date !== 'string') return null

  const level = payload.type as DesktopTimeoutLevel
  const desktopId = typeof params.desktop_id === 'string' ? params.desktop_id : null
  const name = typeof params.name === 'string' ? params.name : ''

  return {
    key: desktopId ?? `${name}|${params.date}`,
    desktopId,
    name,
    stopsAt: params.date,
    level: LEVELS.includes(level) ? level : 'warning',
    extendMinutes: desktopId && params.extend_enabled === true ? (params.extend_time ?? 0) : null
  }
}
