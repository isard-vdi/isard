// lib/http-interceptor.ts
import { useAuthStore } from '@/stores/auth'

/**
 * Check if token needs renewal before making API requests
 * @returns true if token is valid, false if renewal failed
 */
export async function checkTokenBeforeRequest(): Promise<boolean> {
  const authStore = useAuthStore()

  // If not authenticated or session ID is isard-service, no need to renew
  if (authStore.sessionId === 'isard-service' || !authStore.isAuthenticated || !authStore.claims) {
    console.debug('🧹 No valid token for request, no need to renew token')
    return false
  }

  // Get current time and token expiration
  const now = Date.now()
  const timeDrift = Number(localStorage.getItem('timeDrift')) || 0
  const adjustedNow = now + (Math.abs(timeDrift) < 86400000 ? timeDrift : 0)
  const tokenExp = (authStore.claims.exp ?? 0) * 1000
  const timeToExpiry = tokenExp - adjustedNow

  // Renew the session 1 minute before it expires
  if (timeToExpiry < 60000) {
    try {
      // Attempt renewal
      await authStore.renewSession()
      console.debug('✅ Token renewed successfully before request')
      return true
    } catch (error) {
      console.error('❌ Failed to renew token before request:', error)
      await authStore.logout()
      return false
    }
  }

  // Token is still valid
  return true
}
