import { onBeforeRouteLeave } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { TokenType } from '@/lib/auth'

export function useClearTokenOnLeave(tokenTypes: readonly TokenType[]) {
  const authStore = useAuthStore()

  onBeforeRouteLeave(() => {
    if (authStore.tokenType && tokenTypes.includes(authStore.tokenType)) {
      authStore.logout()
    }
  })
}
