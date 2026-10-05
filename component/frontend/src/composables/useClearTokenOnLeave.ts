import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { useEventListener } from '@vueuse/core'
import { useAuthStore } from '@/stores/auth'
import {
  discardStashedToken,
  getToken,
  removeToken,
  stashToken,
  useCookies,
  type TokenType
} from '@/lib/auth'

export function useClearTokenOnLeave(tokenTypes: readonly TokenType[]) {
  const authStore = useAuthStore()
  const router = useRouter()
  const cookies = useCookies()

  onBeforeRouteLeave(() => {
    if (authStore.tokenType && tokenTypes.includes(authStore.tokenType)) {
      authStore.logout()
    }
  })

  // Read the cookie, not the store: a view that removes the cookie and then sets
  // window.location leaves the store stale, and stashing would undo that logout.
  useEventListener(window, 'pagehide', () => {
    const token = getToken(cookies)
    if (!token || !tokenTypes.includes(token.type)) {
      return
    }

    stashToken(cookies)
    removeToken(cookies)
    authStore.$reset()
  })

  useEventListener(window, 'pageshow', (event: PageTransitionEvent) => {
    if (event.persisted) {
      discardStashedToken()
      router.go(0)
    }
  })
}
