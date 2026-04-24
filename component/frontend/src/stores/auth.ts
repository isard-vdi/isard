import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import {
  useCookies,
  removeToken,
  getToken,
  getBearer,
  setToken,
  parseToken,
  type TypeClaims
} from '@/lib/auth'
import { renew } from '@/gen/oas/authentication'

export const useAuthStore = defineStore('auth', () => {
  const claims = ref<TypeClaims | null>(null)
  const token = ref<string | null>(null)
  const cookies = useCookies()

  // Track cookie changes
  let previousCookieValue = getBearer(cookies)

  const isAuthenticated = computed(() => !!token.value)
  const tokenType = computed(() => claims.value?.type)
  const sessionId = computed(() => claims.value?.session_id || null)
  const user = computed(() => claims.value?.data || null)

  // Cookie watcher - only handles auth state, not session management
  const cookieWatcher = watch(
    () => getBearer(cookies),
    async (newValue, oldValue) => {
      console.debug('🍪 Cookie watcher triggered:', {
        newValue,
        oldValue,
        previousCookieValue
      })

      // --- CASE 1: Cookie removed → external logout ---
      if (!newValue && previousCookieValue) {
        console.debug('🔒 Session cookie deleted → external logout detected')
        const tokenForLogout = previousCookieValue
        previousCookieValue = undefined

        // Before resetting auth state, call authentication logout endpoint
        logoutAuthentication(tokenForLogout)

        // Clear auth state without clearing cookie (already gone)
        $reset()

        // The session store watcher will detect this change and handle the external logout
        return
      }

      // --- CASE 2: Cookie added/updated → reinitialize ---
      if (newValue && newValue !== previousCookieValue) {
        console.debug('🔄 Session cookie changed → reinitialize auth')
        previousCookieValue = newValue
        initialize()
      }
    },
    { immediate: false, flush: 'post' }
  )

  const initialize = () => {
    try {
      const bearer = getBearer(cookies)
      const parsedToken = getToken(cookies)

      if (!bearer || !parsedToken) {
        console.debug('🔓 No valid token, clearing auth state')
        $reset()
        return
      }

      token.value = bearer
      claims.value = parsedToken
      previousCookieValue = bearer

      console.debug('🔐 Auth initialized successfully')
    } catch (error) {
      console.error('❌ Auth initialization failed:', error)
      logout()
    }
  }

  const renewSession = async () => {
    if (!token.value) {
      throw new Error('No token available for renewal')
    }

    const response = await renew({
      body: { token: token.value }
    })

    if (!response || response.error) {
      throw new Error(response?.error?.msg || 'Token renewal failed')
    }

    console.debug('✅ Token renewed, updating cookie')
    setToken(cookies, response.data.token)
    // Cookie watcher will handle reinitializing the auth state
  }

  const logout = (clearCookie = true) => {
    if (!isAuthenticated.value) {
      console.debug('⚠️ Logout called but user is not authenticated')
      return
    }

    const currentToken = token.value
    const currentUser = user.value

    // Clear auth state and cookie immediately
    if (clearCookie) {
      removeToken(cookies)
    }
    token.value = null
    claims.value = null
    previousCookieValue = undefined

    // Fire logout requests in background (fire and forget)
    if (currentToken) {
      if (['manager', 'admin'].includes(currentUser?.role_id || '')) {
        logoutWebapp(currentToken)
      }
      // Check if the currentToken is still valid before calling logoutAuthentication
      const parsedToken = parseToken(currentToken)
      if (parsedToken?.exp && parsedToken.exp * 1000 > Date.now()) {
        logoutAuthentication(currentToken)
      }
    }
  }

  // TODO: This should be done by authentication
  const logoutWebapp = (authToken: string) => {
    console.debug('🚪 Webapp logout initiated')
    fetch('/isard-admin/logout/remote', {
      method: 'GET',
      headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' }
    })
      .then(() => console.debug('✅ Webapp logout successful'))
      .catch((error) => console.error('❌ Webapp logout failed:', error))
  }

  const logoutAuthentication = (authToken?: string) => {
    console.debug('🚪 Auth service logout initiated')
    fetch('/authentication/logout', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken || token.value}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({})
    })
      .then(() => console.debug('✅ Auth service logout successful'))
      .catch((error) => console.error('❌ Auth service logout failed:', error))
  }

  const $reset = () => {
    token.value = null
    claims.value = null
    previousCookieValue = undefined
  }

  const cleanup = () => {
    cookieWatcher()
  }

  return {
    token,
    claims,
    tokenType,
    sessionId,
    user,
    isAuthenticated,
    initialize,
    renewSession,
    logout,
    cleanup,
    $reset
  }
})
