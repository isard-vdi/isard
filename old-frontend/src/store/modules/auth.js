import { jwtDecode } from 'jwt-decode'
import axios from 'axios'
import router from '@/router'
import {
  sessionCookieName,
  apiV3Segment,
  apiAdminSegment,
  authenticationSegment
} from '@/shared/constants'
import { getCookie, setCookie, removeCookie } from 'tiny-cookie'
import { DateUtils } from '../../utils/dateUtils'

const webapp = axios.create({
  baseURL: apiAdminSegment
})

webapp.interceptors.request.use(function (config) {
  config.headers.Authorization = 'Bearer ' + getCookie(sessionCookieName)
  return config
})

export default {
  state: {
    session: getCookie(sessionCookieName) || false,
    timeDrift: Number(localStorage.getItem('auth_time_drift')) || 0,
    user: null,
    currentRoute: '',
    pageErrorMessage: {
      message: '',
      args: {}
    },
    userCategories: [],
    expiredSessionModal: {
      show: false,
      kind: 'renew'
    },
    isRenewing: false
  },
  getters: {
    getSession: (state) => {
      return state.session
    },
    getTimeDrift: (state) => {
      return state.timeDrift
    },
    getUser: (state) => {
      return state.user
    },
    getCurrentRoute: (state) => {
      return state.currentRoute
    },
    getPageErrorMessage: (state) => {
      return state.pageErrorMessage
    },
    getUserCategories: (state) => {
      return state.userCategories
    },
    getExpiredSessionModal: (state) => {
      return state.expiredSessionModal
    },
    getIsRenewing: (state) => {
      return state.isRenewing
    }
  },
  mutations: {
    setSession (state, session) {
      if (session) {
        setCookie(sessionCookieName, session)
      } else {
        removeCookie(sessionCookieName)
        removeCookie('authorization')
        removeCookie('session')
      }
      state.session = session
    },
    setTimeDrift (state, drift) {
      state.timeDrift = drift
      localStorage.setItem('auth_time_drift', drift)
    },
    setUser (state, user) {
      state.user = user
    },
    setPageErrorMessage (state, errorMessage) {
      if (errorMessage.args) {
        state.pageErrorMessage = {
          message: errorMessage.message,
          args: errorMessage.args
        }
      } else {
        state.pageErrorMessage = { message: errorMessage }
      }
    },
    setCurrentRoute (state, routeName) {
      state.currentRoute = routeName
    },
    setUserCategories (state, categories) {
      state.userCategories = categories
    },
    setExpiredSessionModal (state, payload) {
      state.expiredSessionModal = payload
    },
    setRenewingFlag (state, isRenewing) {
      state.isRenewing = isRenewing
    }
  },
  actions: {
    async login (context, data) {
      const authentication = axios.create({
        baseURL: authenticationSegment
      })

      authentication.interceptors.request.use(function (config) {
        if (getCookie('authorization')) {
          config.headers.Authorization = 'Bearer ' + getCookie('authorization')
        }
        return config
      })
      const response = await authentication
        .post(
          `/login?provider=${data ? data.get('provider') : 'form'}&category_id=${data ? data.get('category_id') : 'default'}`,
          data,
          { timeout: 25000 }
        )

      const token = jwtDecode(response.data)
      if (token.type === 'register') {
        window.location.pathname = '/register'
      } else if (token.type === 'category-select') {
        window.location.pathname = '/'
      } else {
        const location = response.headers.get('location')
        if (location) {
          window.location.pathname = location
        }
        context.dispatch('loginSuccess', response.data)
      }
    },
    fetchUserCategories (context) {
      const token = jwtDecode(getCookie('authorization'))
      context.commit('setUser', jwtDecode(getCookie('authorization')).user)
      context.commit('setUserCategories', token.categories)
    },
    loginSuccess (context, token) {
      context.commit('setSession', token)
      const session = jwtDecode(context.getters.getSession)
      context.dispatch('updateTimeDrift', session)
      if (!session.type) {
        context.dispatch('fetchUser')
        if (['admin', 'manager'].includes(context.getters.getUser.role_id)) {
          context.dispatch('loginWebapp')
        }
        context.dispatch('saveNewLanguage')
      }
      router.push({ name: 'desktops' })
    },
    loginWebapp (context) {
      webapp.get('/login', {}, { timeout: 25000 }).catch((e) => {
        if (e.response.status === 503) {
          window.location.pathname = '/maintenance'
        } else {
          console.log(e)
        }
      })
    },
    renew (context, closeModal = false) {
      // Set a flag to prevent renewal loops across tabs
      context.commit('setRenewingFlag', true)

      const authentication = axios.create({
        baseURL: authenticationSegment
      })
      authentication.interceptors.request.use((config) => {
        config.headers.Authorization = `Bearer ${getCookie(sessionCookieName)}`
        return config
      })
      return authentication
        .post('/renew', {})
        .then((response) => {
          if (closeModal) {
            context.commit('setExpiredSessionModal', { show: false, kind: 'renew' })
          }
          context.commit('setSession', response.data.token)
          context.dispatch('updateTimeDrift', jwtDecode(response.data.token))
          context.dispatch('openSocket', {})
          context.dispatch('fetchUser')
          context.dispatch('fetchConfig')
        })
        .catch((e) => {
          console.error('Session renewal failed:', e)
          context.dispatch('showExpiredSessionModal', 'expired')
        })
        .finally(() => {
          // Clear the renewal flag
          context.commit('setRenewingFlag', false)
        })
    },
    logout (context, redirect = true) {
      const bearer = `Bearer ${getCookie(sessionCookieName)}`
      const logoutAxios = axios.create()
      logoutAxios.interceptors.request.use((config) => {
        config.headers.Authorization = bearer
        return config
      })
      if (getCookie(sessionCookieName)) {
        const session = jwtDecode(context.getters.getSession)
        if (!session.type) {
          if (
            context.getters.getUser &&
            ['admin', 'manager'].includes(context.getters.getUser.role_id)
          ) {
            webapp.get('/logout/remote')
          }
        }
        logoutAxios.post(
          `${authenticationSegment}/logout`,
          {}
        ).then((response) => {
          context.commit('setSession', false)
          context.commit('resetStore')
          context.dispatch('closeSocket')
          if (response.data.redirect) {
            window.location = response.data.redirect
          } else if (redirect) {
            window.location.pathname = '/login'
          }
        }).catch((error) => {
          console.warn('Logout request failed:', error)
          context.commit('setSession', false)
          context.commit('resetStore')
          context.dispatch('closeSocket')

          window.location.pathname = '/login'
        })
      } else {
        context.commit('setSession', false)
        context.commit('resetStore')
        context.dispatch('closeSocket')
        window.location.pathname = '/login'
      }
    },
    saveNavigation (context, payload) {
      const currentRoute = payload.url.name
      context.commit('setCurrentRoute', currentRoute)
    },
    handleLoginError ({ commit }, e) {
      if (e.response.status === 403 && e.response.data === 'disabled user') {
        commit('setPageErrorMessage', 'errors.user_disabled')
      } else if ([401, 500].includes(e.response.status)) {
        commit(
          'setPageErrorMessage',
          `views.login.errors.${e.response.status}`
        )
      } else if ([429].includes(e.response.status)) {
        if (DateUtils.dateIsToday(e.response.headers['retry-after'])) {
          commit('setPageErrorMessage', {
            message: `views.login.errors.${e.response.status}`,
            args: {
              time: DateUtils.formatAsTimeWithSeconds(
                e.response.headers['retry-after']
              )
            }
          })
        } else {
          commit('setPageErrorMessage', {
            message: `views.login.errors.${e.response.status}`,
            args: {
              time: DateUtils.formatAsFullDateTime(
                e.response.headers['retry-after']
              )
            }
          })
        }
      } else {
        commit('setPageErrorMessage', 'views.login.errors.generic')
      }
    },
    async selectCategory (context, categoryId) {
      const loginData = new FormData()
      loginData.append('provider', 'saml')
      loginData.append('category_id', categoryId)
      context.dispatch('login', loginData)
    },
    fetchUser (context) {
      // Get basic user info from token
      const tokenPayload = jwtDecode(context.getters.getSession)
      if (tokenPayload.data) {
        context.commit('setUser', tokenPayload.data)

        // Update user info with additional data from API
        axios.get(`${apiV3Segment}/user`).then((response) => {
          const data = { ...tokenPayload.data }

          data.role_name = response.data.role_name
          data.category_name = response.data.category_name
          data.group_name = response.data.group_name

          context.commit('setUser', data)
        })
        // Email verification page
      }
    },
    async updateSession (context, session) {
      context.commit('setSession', session)
      context.dispatch('updateTimeDrift', jwtDecode(session))
    },
    updateTimeDrift (context, jwt) {
      // Unixtime in milis
      const local = Date.now()
      // Unixtime in seconds
      const server = jwt.iat * 1000

      let drift = server - local

      // Maximum allowed drift: 24 hours in either direction
      const MAX_DRIFT = 24 * 60 * 60 * 1000

      if (Math.abs(drift) > MAX_DRIFT) {
        console.warn(`Extreme time drift detected: ${drift}ms. Changing to a safe range.`)
        drift = drift > 0 ? MAX_DRIFT : -MAX_DRIFT
      }

      context.commit('setTimeDrift', drift)
    },
    // Email verification
    sendVerifyEmail (context, data) {
      const verifyEmailAxios = axios.create()
      verifyEmailAxios.interceptors.request.use((config) => {
        config.headers.Authorization = `Bearer ${getCookie(sessionCookieName)}`
        return config
      })
      return verifyEmailAxios.post(
        `${authenticationSegment}/request-email-verification`,
        data
      )
    },
    verifyEmail (context, token) {
      const verifyEmailAxios = axios.create()
      verifyEmailAxios.interceptors.request.use((config) => {
        config.headers.Authorization = `Bearer ${token}`
        return config
      })
      return verifyEmailAxios.post(`${authenticationSegment}/verify-email`, {})
    },
    // Password reset
    sendResetPasswordEmail (context, data) {
      const forgotPasswordAxios = axios.create()
      return forgotPasswordAxios.post(
        `${authenticationSegment}/forgot-password`,
        data
      )
    },
    fetchExpiredPasswordPolicy (context, token) {
      const expiredPasswordAxios = axios.create()
      expiredPasswordAxios.interceptors.request.use((config) => {
        config.headers.Authorization = `Bearer ${token}`
        return config
      })
      return expiredPasswordAxios
        .get(`${apiV3Segment}/user/expired/password-policy`)
        .then((response) => {
          context.commit('setPasswordPolicy', response.data)
        })
    },
    resetPassword (context, data) {
      const resetPasswordAxios = axios.create()
      const token = data.token
      delete data.token
      resetPasswordAxios.interceptors.request.use((config) => {
        config.headers.Authorization = `Bearer ${token}`
        return config
      })

      return resetPasswordAxios.post(
        `${authenticationSegment}/reset-password`,
        data
      )
    },
    showExpiredSessionModal (context, kind) {
      context.commit('setExpiredSessionModal', { show: true, kind: kind })
    },
    syncSessionFromCookie (context, newSessionToken) {
      // This action is called when the session cookie changes in another tab
      // It synchronizes the current tab's session state and dismisses modals if appropriate

      // Don't sync if this tab is currently renewing (to prevent loops)
      if (context.getters.getIsRenewing) {
        return
      }

      const oldSession = context.getters.getSession
      if (oldSession !== newSessionToken) {
        // Update the session in the store
        context.commit('setSession', newSessionToken)

        // Update time drift based on the new token
        context.dispatch('updateTimeDrift', jwtDecode(newSessionToken))

        // Check if we should dismiss the renewal modal
        const config = context.rootGetters.getConfig
        if (config.session) {
          const now = Date.now()
          const timeDrift = context.getters.getTimeDrift
          const adjustedNow = now + timeDrift

          const sessionData = jwtDecode(newSessionToken)
          const tokenExpiration = sessionData.exp * 1000
          const maxRenewTime = config.session.maxRenewTime * 1000

          // If the new token is not expired yet, dismiss the renewal modal
          if (adjustedNow < tokenExpiration) {
            context.commit('setExpiredSessionModal', { show: false, kind: 'renew' })

            // Re-fetch config to update timers with the new session
            context.dispatch('fetchConfig')
          } else if (adjustedNow < maxRenewTime) {
            // Token is still expired but within renewal window - keep showing renewal modal
            context.dispatch('showExpiredSessionModal', 'renew')
          } else {
            // Max renew time exceeded - show expired modal for logout
            context.dispatch('showExpiredSessionModal', 'expired')
          }
        }
      }
    }
  }
}
