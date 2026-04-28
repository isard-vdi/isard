import axios from 'axios'
import router from '@/router'
import { sessionCookieName } from '../shared/constants'
import { getCookie } from 'tiny-cookie'
import store from '@/store'
import { jwtDecode } from 'jwt-decode'
import { setFaroApiEvent, setFaroError } from '@/lib/faro'

// Strip token-bearing path segments and querystrings so Faro's
// route_template stays a low-cardinality, OpenAPI-shaped value.
function routeTemplateFor (urlString) {
  try {
    const parsed = new URL(urlString, window.location.origin)
    return parsed.pathname
  } catch {
    return urlString.split('?')[0]
  }
}

function clientFor (urlString) {
  if (urlString.includes('/authentication')) return 'auth'
  if (urlString.includes('/api/v3') || urlString.includes('/api/v4')) return 'api'
  return 'api'
}

export default function axiosSetUp () {
  // point to your API endpoint
  axios.defaults.baseURL = `${window.location.protocol}//${window.location.host}`
  // Track request start time so Faro can report duration on failures.
  axios.interceptors.request.use(
    function (config) {
      config.metadata = { ...(config.metadata || {}), faroStart: performance.now() }
      return config
    }
  )

  // Add a request interceptor
  axios.interceptors.request.use(
    // Spinning show
    async function (config) {
      document.body.classList.add('loading-cursor')
      if (document.querySelector('[type="submit"]')) {
        document.querySelector('[type="submit"]').setAttribute('disabled', 'disabled')
      }

      // Check if token needs renewal before making API requests
      if (getCookie(sessionCookieName)) {
        const session = store.getters.getSession

        // Skip renewal for service sessions or logout requests
        if (config.url.includes('logout', 'renew') || !session) {
          config.headers.Authorization = `Bearer ${getCookie(sessionCookieName)}`
          return config
        }

        const sessionData = jwtDecode(session)

        // Skip renewal for isard-service sessions
        if (sessionData.session_id === 'isard-service') {
          config.headers.Authorization = `Bearer ${getCookie(sessionCookieName)}`
          return config
        }

        // Get current time and token expiration
        const now = Date.now()
        const timeDrift = store.getters.getTimeDrift
        const adjustedNow = now + (Math.abs(timeDrift) < 86400000 ? timeDrift : 0)
        const tokenExp = sessionData.exp * 1000
        const timeToExpiry = tokenExp - adjustedNow

        // Renew the session 1 minute before it expires
        if (timeToExpiry < 60000) {
          console.debug('🔄 Token expiring soon, renewing before request')
          try {
            await store.dispatch('renew')
            if (!store.getters.getSession) {
              console.error('❌ Token renewal failed')
              return Promise.reject(new Error('Session cannot be renewed'))
            }
            console.debug('✅ Token renewed successfully before request')
          } catch (error) {
            console.error('❌ Failed to renew token before request:', error)
            return Promise.reject(error)
          }
        }

        config.headers.Authorization = `Bearer ${getCookie(sessionCookieName)}`
      }
      return config
    },
    function (error) {
      // Do something with request error
      return Promise.reject(error)
    }
  )

  // Add a response interceptor
  axios.interceptors.response.use(
    // Spinning hide
    function (response) {
      document.body.classList.remove('loading-cursor')
      if (document.querySelector('[type="submit"]')) {
        document.querySelector('[type="submit"]').removeAttribute('disabled')
      }
      // Any status code that lie within the range of 2xx cause this function to trigger
      // Do something with response data
      return response
    },
    async function (error) {
      document.body.classList.remove('loading-cursor')
      if (document.querySelector('[type="submit"]')) {
        document.querySelector('[type="submit"]').removeAttribute('disabled')
      }

      const cfg = error.config || {}
      const url = cfg.url || ''
      const started = cfg.metadata?.faroStart ?? performance.now()
      const responseSize = Number(error.response?.headers?.['content-length']) || undefined
      const requestId = error.response?.headers?.['x-request-id'] || undefined

      setFaroApiEvent({
        client: clientFor(url),
        method: (cfg.method || 'GET').toUpperCase(),
        route_template: routeTemplateFor(url),
        duration_ms: Math.round(performance.now() - started),
        error_type: error.response ? 'http' : 'network',
        status: error.response?.status,
        request_id: requestId,
        response_size: responseSize
      })

      // Check if error.response exists (network errors don't have response)
      if (!error.response) {
        console.error('Network error or request cancelled:', error.message)
        setFaroError(error, { source: 'axios', info: 'api_network_error' })
        return Promise.reject(error)
      }

      if (!error.config.url.includes('scheduler') && error.response.status === 503) {
        // router.replace({ name: 'Maintenance' })
        window.location.pathname = '/maintenance'
      } else if (error.response.status === 500) {
        router.replace({
          name: 'Error',
          params: { code: error.response.status.toString() }
        })
      } else if (error.response.status === 401) {
        store.dispatch('logout')
      } else if (error.response.status === 429) {
        console.log('Too many requests')
        return Promise.resolve(null)
      }
      return Promise.reject(error)
    }
  )
}
