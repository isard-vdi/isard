// stores/session.ts
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { useRouter, type RouteLocationRaw } from 'vue-router'
import { useAuthStore } from './auth'
import { useUserStore } from './user'
import { isProvider } from '@/lib/auth'
import { apiV4CategoryCustomUrl } from '@/gen/oas/apiv4'

export type SessionModalKind = 'renew' | 'max-renew-time' | 'max-time' | 'error-renew'

const PROVIDER_ROUTE_ALIASES: Record<string, string> = { local: 'form', ldap: 'form' }

export const useSessionStore = defineStore('session', () => {
  // Session state
  const modalOpen = ref(false)
  const modalKind = ref<SessionModalKind>('renew')
  const timeDrift = ref(Number(localStorage.getItem('timeDrift')) || 0)

  // Timeout tracking
  const timeouts = ref<{
    renewal: NodeJS.Timeout | null
    maxRenew: NodeJS.Timeout | null
    maxTime: NodeJS.Timeout | null
  }>({
    renewal: null,
    maxRenew: null,
    maxTime: null
  })

  // Store references
  const authStore = useAuthStore()
  const userStore = useUserStore()
  const router = useRouter()

  // Track authentication state
  const wasAuthenticated = ref(false)
  const internalLogoutInProgress = ref(false) // Flag to track internal logouts

  // Computed values
  const isSessionActive = computed(() => authStore.isAuthenticated)
  const tokenExpiration = computed(() => (authStore.claims?.exp ?? 0) * 1000)
  const sessionConfig = computed(() => userStore.config?.session)

  /**
   * Initialize session management
   */
  const initialize = async () => {
    console.debug('🎯 Initializing session management')

    // If session is isard-service skip session initialization
    if (authStore.sessionId === 'isard-service') {
      console.debug('❌ User not authenticated, skipping session initialization')
      return
    }

    wasAuthenticated.value = true
    internalLogoutInProgress.value = false // Reset flag on new authentication

    // Ensure user config is loaded
    if (!userStore.config) {
      await userStore.getUserConfig()
    }

    // Set up session timeouts
    if (sessionConfig.value.id !== 'isardvdi-service') {
      setupTimeouts()
    }
  }

  /**
   * Setup session timeouts based on current token and config
   */
  const setupTimeouts = () => {
    clearAllTimeouts()

    if (!authStore.claims || !sessionConfig.value) {
      console.debug('⏰ No claims or config, skipping timeout setup')
      return
    }

    const now = Date.now()
    const exp = tokenExpiration.value
    const maxRenewTime = sessionConfig.value.max_renew_time * 1000
    const maxTime = sessionConfig.value.max_time * 1000

    // Adjust for time drift (if reasonable)
    const adjustedNow = now + (Math.abs(timeDrift.value) < 86400000 ? timeDrift.value : 0)

    const timeToExpiry = exp - adjustedNow
    const timeToMaxRenew = maxRenewTime - adjustedNow

    console.debug('⏰ Setting up session timeouts:', {
      tokenExpiry: new Date(exp).toLocaleString(),
      maxRenewTime: new Date(maxRenewTime).toLocaleString(),
      maxTime: new Date(maxTime).toLocaleString(),
      timeToExpiry: Math.round(timeToExpiry / 1000),
      timeToMaxRenew: Math.round(timeToMaxRenew / 1000)
    })

    // Case 1: Max renew time equals max time - no renewal possible
    if (sessionConfig.value.max_renew_time === sessionConfig.value.max_time) {
      timeouts.value.maxTime = setTimeout(() => {
        console.debug('🔒 Max session time reached (no renewal)')
        handleSessionEnd('max-time')
      }, timeToExpiry)
      return
    }

    // Case 2: Normal session with renewal window
    // Show renewal modal when the token expires
    if (timeToExpiry > 0) {
      timeouts.value.renewal = setTimeout(() => {
        console.debug('🔄 Showing renewal modal')
        showModal('renew')
      }, timeToExpiry)
    }

    // Set max renew time timeout
    if (timeToMaxRenew > 0) {
      timeouts.value.maxRenew = setTimeout(() => {
        console.debug('🔒 Max renewal time reached')
        handleSessionEnd('max-renew-time')
      }, timeToMaxRenew)
    }
  }

  /**
   * Handle session renewal
   */
  const renewSession = async (): Promise<boolean> => {
    try {
      console.debug('🔄 Attempting session renewal')

      await authStore.renewSession()

      hideModal()
      console.debug('✅ Session renewed successfully')
      return true
    } catch (error) {
      console.error('❌ Session renewal failed:', error)
      handleSessionEnd('error-renew')
      return false
    }
  }

  /**
   * Handle session end scenarios (internal timeouts/errors)
   */
  const handleSessionEnd = async (reason: SessionModalKind) => {
    console.debug('🚪 Handling internal session end:', reason)

    clearAllTimeouts()
    internalLogoutInProgress.value = true // Mark as internal logout

    if (reason === 'error-renew') {
      // Show error modal but don't logout yet
      showModal(reason)
    } else {
      // Force logout for other scenarios
      await authStore.logout()
      showModal(reason)
    }
  }

  const categoryCustomUrl = async (categoryId: string): Promise<string | undefined> => {
    const fromConfig = userStore.config?.category_custom_url
    if (typeof fromConfig === 'string' && fromConfig) {
      return fromConfig
    }

    // Fall back to apiV4CategoryCustomUrl if the user doesn't have a valid token
    try {
      const { data } = await apiV4CategoryCustomUrl({ path: { category_id: categoryId } })
      // The endpoint answers with a '/login' sentinel when the category has no slug.
      return data && data !== '/login' ? data : undefined
    } catch (error) {
      console.warn('Could not resolve the category login URL:', error)
      return undefined
    }
  }

  const loginRoute = async (): Promise<RouteLocationRaw> => {
    const identity = authStore.lastLoginIdentity
    if (!identity) {
      return { name: 'login' }
    }

    const aliased = PROVIDER_ROUTE_ALIASES[identity.provider] ?? identity.provider
    const provider = isProvider(aliased) ? aliased : 'all'

    const category = await categoryCustomUrl(identity.categoryId)
    return category
      ? { name: 'login', params: { provider, category } }
      : { name: 'login', params: { provider } }
  }

  const pushLoginRoute = async () => {
    const route = await loginRoute()
    userStore.$reset()
    router.push(route)
  }

  const handleExternalLogout = async () => {
    console.debug('🚪 External logout detected (session terminated in Flask app)')
    clearAllTimeouts()
    hideModal()
    wasAuthenticated.value = false
    internalLogoutInProgress.value = false

    // Redirect to login immediately without showing modal
    await pushLoginRoute()
  }

  /**
   * Show session modal
   */
  const showModal = (kind: SessionModalKind) => {
    modalKind.value = kind
    modalOpen.value = true
  }

  /**
   * Hide session modal
   */
  const hideModal = () => {
    modalOpen.value = false
  }

  /**
   * Handle logout from modal (internal logout)
   */
  const handleLogout = async () => {
    console.debug('🚪 Internal logout requested')
    internalLogoutInProgress.value = true

    await authStore.logout()
    hideModal()
    wasAuthenticated.value = false
    await pushLoginRoute()
  }

  /**
   * Handle redirect to login
   */
  const redirectToLogin = async () => {
    hideModal()
    wasAuthenticated.value = false
    internalLogoutInProgress.value = false
    await pushLoginRoute()
  }

  /**
   * Clear all active timeouts
   */
  const clearAllTimeouts = () => {
    Object.values(timeouts.value).forEach((timeout) => {
      if (timeout) clearTimeout(timeout)
    })
    timeouts.value = { renewal: null, maxRenew: null, maxTime: null }
  }

  /**
   * Reset session store
   */
  const $reset = () => {
    clearAllTimeouts()
    modalOpen.value = false
    modalKind.value = 'renew'
    wasAuthenticated.value = false
    internalLogoutInProgress.value = false
  }

  // Watch for authentication changes
  watch(
    () => authStore.isAuthenticated,
    async (isAuth, wasAuth) => {
      console.debug('🔐 Auth state changed:', {
        isAuth,
        wasAuth,
        wasAuthenticated: wasAuthenticated.value,
        internalLogoutInProgress: internalLogoutInProgress.value
      })

      if (isAuth) {
        console.debug('🔐 User authenticated, initializing session')
        await initialize()
      } else if (wasAuthenticated.value && !internalLogoutInProgress.value) {
        // User was authenticated but now isn't AND it's not an internal logout
        // This means the cookie was removed externally (Flask app logout)
        console.debug('🔓 External logout detected (Flask app)')
        await handleExternalLogout()
      } else if (internalLogoutInProgress.value) {
        // This is an internal logout we initiated
        console.debug('🔓 Internal logout completed')
        clearAllTimeouts()
        hideModal()
        wasAuthenticated.value = false
        internalLogoutInProgress.value = false
      } else {
        // User was never authenticated in this session
        console.debug('🔓 User not authenticated, clearing session')
        clearAllTimeouts()
        hideModal()
      }
    },
    { immediate: false }
  )

  // Watch for token changes (renewals)
  watch(
    () => authStore.token,
    async (newToken, oldToken) => {
      if (newToken && oldToken && newToken !== oldToken) {
        console.debug('🔄 Token renewed, resetting timeouts')
        // Refetch the user condig to retrieve the new max renew time
        await userStore.getUserConfig()
        initialize()
      }
    }
  )

  return {
    // State
    modalOpen,
    modalKind,
    isSessionActive,

    // Actions
    initialize,
    renewSession,
    loginRoute,
    handleLogout,
    redirectToLogin,
    showModal,
    hideModal,
    $reset
  }
})
