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
        if (!config.url.includes('logout') && Date.now() + store.getters.getTimeDrift > ((sessionData.exp - 30) * 1000)) {
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
