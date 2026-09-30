import { onBeforeRouteLeave } from 'vue-router'
import { useEventListener } from '@vueuse/core'
import { useAuthStore } from '@/stores/auth'
import {
  getBearer,
  getToken,
  removeToken,
  stashToken,
  useCookies,
  type TokenType
} from '@/lib/auth'

export function useClearTokenOnLeave(tokenTypes: readonly TokenType[]) {
  const authStore = useAuthStore()
  const cookies = useCookies()

  onBeforeRouteLeave(() => {
    if (authStore.tokenType && tokenTypes.includes(authStore.tokenType)) {
      authStore.logout()
    }
  })

  // Read the cookie, not the store: a view that removes the cookie and then sets
  // window.location leaves the store stale, and stashing would undo that logout.
  useEventListener(window, 'pagehide', () => {
    const bearer = getBearer(cookies)
    const token = getToken(cookies)
    if (!bearer || !token || !tokenTypes.includes(token.type)) {
      return
    }

    stashToken(bearer)
    removeToken(cookies)
    authStore.$reset()
  })

  useEventListener(window, 'pageshow', (event: PageTransitionEvent) => {
    if (event.persisted) {
      authStore.restoreStashedToken()
    }
  })
}
