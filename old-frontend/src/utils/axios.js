import axios from 'axios'
import router from '@/router'
import { sessionCookieName } from '../shared/constants'
import { getCookie } from 'tiny-cookie'
import store from '@/store'
import { jwtDecode } from 'jwt-decode'

export default function axiosSetUp () {
  // point to your API endpoint
  axios.defaults.baseURL = `${window.location.protocol}//${window.location.host}`
  // Add a request interceptor
  axios.interceptors.request.use(
    // Spinning show
    async function (config) {
      document.body.classList.add('loading-cursor')
      if (document.querySelector('[type="submit"]')) {
        document.querySelector('[type="submit"]').setAttribute('disabled', 'disabled')
      }
      // If the session is expired and it's not calling the logout endpoint try to renew the token
      if (getCookie(sessionCookieName)) {
        const session = store.getters.getSession
        const sessionData = jwtDecode(session)
        // Check session expiration with fallback logic
        const now = Date.now()
        const timeDrift = store.getters.getTimeDrift
        // adjustedNow = now + timeDrift (if time drift is reasonable)
        const adjustedNow = now + (Math.abs(timeDrift) < (24 * 60 * 60 * 1000) ? timeDrift : 0) // 24h in ms
        const tokenExpiration = sessionData.exp * 1000 // in ms
        const maxRenewTime = store.getters.getConfig.session?.maxRenewTime * 1000 // in ms

        // Auto-renew 30s before expiration or within renewal window (after expiration but before max time)
        const isExpired = adjustedNow > tokenExpiration
        const shouldRenew = adjustedNow > tokenExpiration - 30000 && (!isExpired || (maxRenewTime && adjustedNow < maxRenewTime))

        if (!config.url.includes('logout') && shouldRenew) {
          await store.dispatch('renew')
          if (!store.getters.getSession) {
            return Promise.reject(new Error('Session cannot be renewed'))
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
      if (!error.config.url.includes('scheduler') && error.response.status === 503) {
        // router.replace({ name: 'Maintenance' })
        window.location.pathname = '/maintenance'
      } else if (error.response.status === 500) {
        router.replace({
          name: 'Error',
          params: { code: error.response && error.response.status.toString() }
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
