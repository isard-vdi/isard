import { computed, onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import type { BrowserVncValues } from '@/gen/oas/apiv4'
import { getDesktopViewerByTypeOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'

import { canViewInBrowser, type VideowallDesktop } from '@/lib/videowall'

const MAX_RETRIES = 3
const RETRY_DELAY_MS = 1000
// A handshake that neither connects nor fails would spin forever.
const CONNECT_TIMEOUT_MS = 15000

/** A noVNC feed of a videowall desktop, live only while `active` holds. */
export function useVideowallStream(
  desktop: MaybeRefOrGetter<VideowallDesktop | null>,
  active: MaybeRefOrGetter<boolean>
) {
  const desktopId = computed(() => toValue(desktop)?.id ?? '')
  const streaming = computed(() => {
    const current = toValue(desktop)
    return current !== null && toValue(active) && canViewInBrowser(current)
  })

  const {
    data: viewer,
    isError,
    refetch
  } = useQuery(
    computed(() => ({
      ...getDesktopViewerByTypeOptions({
        path: { desktop_id: desktopId.value, viewer_type: 'browser-vnc' }
      }),
      enabled: streaming.value,
      // The engine rotates the password on every start: never reuse one.
      staleTime: 0,
      gcTime: 0
    }))
  )

  const vncValues = computed(() =>
    streaming.value && viewer.value?.kind === 'browser' && viewer.value.protocol === 'vnc'
      ? (viewer.value.values as BrowserVncValues)
      : null
  )

  // Each attempt is its own key, so a retry remounts noVNC even with the same password.
  const attempt = ref(0)
  // Failures in a row: a stream that paints again earns its retries back.
  let failures = 0
  const connectionKey = computed(() =>
    vncValues.value ? `${desktopId.value}:${vncValues.value.token}:${attempt.value}` : null
  )
  const connection = ref<{ key: string; state: 'connected' | 'failed' } | null>(null)
  const connectionState = computed(() =>
    connection.value && connection.value.key === connectionKey.value ? connection.value.state : null
  )
  const failed = computed(
    () => streaming.value && (isError.value || connectionState.value === 'failed')
  )
  const connecting = computed(
    () => streaming.value && !failed.value && connectionState.value !== 'connected'
  )

  let retryTimer: ReturnType<typeof setTimeout> | undefined
  let timeoutTimer: ReturnType<typeof setTimeout> | undefined

  const fail = () => {
    const key = connectionKey.value
    if (!key) return
    if (failures >= MAX_RETRIES) {
      connection.value = { key, state: 'failed' }
      return
    }
    clearTimeout(retryTimer)
    retryTimer = setTimeout(
      async () => {
        if (connectionKey.value !== key) return
        await refetch()
        failures++
        attempt.value++
      },
      RETRY_DELAY_MS * (failures + 1)
    )
  }

  const onConnect = () => {
    if (!connectionKey.value) return
    failures = 0
    connection.value = { key: connectionKey.value, state: 'connected' }
  }

  watch(connectionKey, (key) => {
    clearTimeout(timeoutTimer)
    if (!key) return
    timeoutTimer = setTimeout(() => {
      if (connectionKey.value === key && connectionState.value === null) fail()
    }, CONNECT_TIMEOUT_MS)
  })

  watch([desktopId, streaming], () => {
    clearTimeout(retryTimer)
    failures = 0
    attempt.value = 0
  })

  onScopeDispose(() => {
    clearTimeout(retryTimer)
    clearTimeout(timeoutTimer)
  })

  return {
    streaming,
    vncValues,
    connectionKey,
    connecting,
    failed,
    onConnect,
    onDisconnect: fail
  }
}
