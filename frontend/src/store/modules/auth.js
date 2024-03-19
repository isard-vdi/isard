import { jwtDecode } from 'jwt-decode'
import axios from 'axios'
import router from '@/router'
import { sessionCookieName, apiV3Segment, apiAdminSegment, authenticationSegment } from '@/shared/constants'
import { getCookie, setCookie, removeCookie } from 'tiny-cookie'

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
    user: null,
    currentRoute: '',
    pageErrorMessage: ''
  },
  getters: {
    getSession: state => {
      return state.session
    },
    getUser: state => {
      return state.user
    },
    getCurrentRoute: state => {
      return state.currentRoute
    },
    getPageErrorMessage: state => {
      return state.pageErrorMessage
    }
  },
  mutations: {
    setSession (state, session) {
      if (session) {
        setCookie(sessionCookieName, session)
      } else {
        removeCookie(sessionCookieName)
        removeCookie('authorization')
      }
      state.session = session
    },
    setUser (state, user) {
      state.user = user
    },
    setPageErrorMessage (state, errorMessage) {
      state.pageErrorMessage = errorMessage
    },
    setCurrentRoute (state, routeName) {
      state.currentRoute = routeName
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
      await authentication.post(`/login?provider=${data.get('provider')}&category_id=${data.get('category_id')}`, data, { timeout: 25000 }).then(response => {
        if (jwtDecode(response.data).type === 'register') {
          router.push({ name: 'Register' })
        } else {
          context.dispatch('loginSuccess', response.data)
        }
      })
    },
    loginSuccess (context, token) {
      context.commit('setSession', token)
      const session = jwtDecode(context.getters.getSession)
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
      webapp.get('/login', {}, { timeout: 25000 }).catch(e => {
        if (e.response.status === 503) {
          router.push({ name: 'Maintenance' })
        } else {
          console.log(e)
        }
      })
    },
    logout (context, redirect = true) {
      if (getCookie(sessionCookieName)) {
        const session = jwtDecode(context.getters.getSession)
        if (!session.type) {
          if (context.getters.getUser && ['admin', 'manager'].includes(context.getters.getUser.role_id)) {
            webapp.get('/logout/remote')
          }
        }
      }
      context.commit('setSession', false)
      context.commit('resetStore')
      context.dispatch('closeSocket')
      if (redirect) {
        router.push({ name: 'Login' })
      }
    },
    saveNavigation (context, payload) {
      const currentRoute = payload.url.name
      context.commit('setCurrentRoute', currentRoute)
    },
    handleLoginError ({ commit }, e) {
      if (e.response.status === 403 && e.response.data === 'disabled user') {
        commit('setPageErrorMessage', 'errors.user_disabled')
      } else if ([401, 429, 500].includes(e.response.status)) {
        commit('setPageErrorMessage', `views.login.errors.${e.response.status}`)
      } else {
        commit('setPageErrorMessage', 'views.login.errors.generic')
      }
    },
    async register (context, code) {
      const register = axios.create({
        baseURL: apiV3Segment
      })
      register.interceptors.request.use(function (config) {
        config.headers.Authorization = 'Bearer ' + getCookie('authorization')
        return config
      })
      // TODO: Change to application/json
      const data = new FormData()
      data.append('code', code)
      return register.post('/user/register', data).then(() => {
        setCookie(sessionCookieName, getCookie('authorization'))
        const registeredUser = jwtDecode(getCookie(sessionCookieName))
        let provider = registeredUser.provider
        if (provider === 'local' || provider === 'ldap') {
          provider = 'form'
        }
        // TODO: Change to application/json
        const loginData = new FormData()
        loginData.append('provider', provider)
        loginData.append('category_id', registeredUser.category_id)
        loginData.append('username', registeredUser.username)
        context.dispatch('login', loginData)
      })
    },
    handleRegisterError ({ commit }, error) {
      if ([401, 404, 409].includes(error.response.status)) {
        commit('setPageErrorMessage', `views.register.errors.${error.response.status}`)
      } else if (error.response.status === 429) {
        commit('setPageErrorMessage', 'views.login.errors.429')
      } else {
        commit('setPageErrorMessage', 'views.error.codes.500')
      }
    },
    fetchUser (context) {
      // TODO: Instead of retrieving from JWT get from API
      const tokenPayload = jwtDecode(getCookie(sessionCookieName))
      if (tokenPayload.data) {
        context.commit('setUser', tokenPayload.data)
      // Email verification page
      } else {
        context.commit('setUser', { current_email: tokenPayload.current_email })
      }
    },
    async updateSession (context, session) {
      context.commit('setSession', session)
    },
    // Email verification
    sendVerifyEmail (context, data) {
      const verifyEmailAxios = axios.create()
      verifyEmailAxios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${getCookie(sessionCookieName)}`
        return config
      })
      return verifyEmailAxios.post(`${authenticationSegment}/request-email-verification`, data)
    },
    verifyEmail (context, token) {
      const verifyEmailAxios = axios.create()
      verifyEmailAxios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${token}`
        return config
      })
      return verifyEmailAxios.post(`${authenticationSegment}/verify-email`, {})
    },
    // Password reset
    sendResetPasswordEmail (context, data) {
      const forgotPasswordAxios = axios.create()
      return forgotPasswordAxios.post(`${authenticationSegment}/forgot-password`, data)
    },
    fetchExpiredPasswordPolicy (context, token) {
      const expiredPasswordAxios = axios.create()
      expiredPasswordAxios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${token}`
        return config
      })
      return expiredPasswordAxios.get(`${apiV3Segment}/user/expired/password-policy`)
        .then(response => {
          context.commit('setPasswordPolicy', response.data)
        })
    },
    resetPassword (context, data) {
      const resetPasswordAxios = axios.create()
      const token = data.token
      delete data.token
      resetPasswordAxios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${token}`
        return config
      })

      return resetPasswordAxios.post(`${authenticationSegment}/reset-password`, data)
    }
  }
}
