import { ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useDocumentVisibility, useTimeoutFn } from '@vueuse/core'
import { jwtDecode } from 'jwt-decode'

// Renew before `exp` so no in-flight request ever races the expiry.
const RENEW_MARGIN_MS = 2 * 60 * 1000
// A blip must not strand the caller on a dead token until a reload.
const RENEW_RETRY_MS = 30 * 1000

/**
 * Keeps a short-lived JWT alive: calls `renew` shortly before the token's `exp`
 * and re-arms on the token it hands back.
 *
 * Also re-arms whenever the tab returns to the front, because browsers throttle
 * timers in background tabs — the delay is clamped at 0, so a token that
 * expired while the tab slept is renewed on the spot.
 */
export function useJwtRenewal(
  jwt: MaybeRefOrGetter<string | undefined>,
  renew: () => Promise<unknown>
) {
  const visibility = useDocumentVisibility()
  const delayMs = ref(0)

  const { start, stop, isPending } = useTimeoutFn(
    async () => {
      try {
        await renew()
        // On success the new token flows back through `jwt`, which re-arms.
      } catch {
        schedule(RENEW_RETRY_MS)
      }
    },
    delayMs,
    { immediate: false }
  )

  // `start` reads the delay at call time and clears any pending timer first.
  const schedule = (ms: number) => {
    delayMs.value = ms
    start()
  }

  const rearm = () => {
    const token = toValue(jwt)
    if (!token) {
      stop()
      return
    }
    let expMs: number
    try {
      expMs = (jwtDecode<{ exp?: number }>(token).exp ?? 0) * 1000
    } catch {
      stop()
      return
    }
    if (!expMs) {
      stop()
      return
    }
    schedule(Math.max(expMs - Date.now() - RENEW_MARGIN_MS, 0))
  }

  watch(() => toValue(jwt), rearm, { immediate: true })
  watch(visibility, (state) => {
    if (state === 'visible') rearm()
  })

  return { isPending, stop }
}
