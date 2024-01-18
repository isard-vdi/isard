import router from '@/router'
import axios from 'axios'
import { apiAdminSegment } from '@/shared/constants'
import store from '@/store/index.js'
import * as cookies from 'tiny-cookie'

export default {
  state: {
    user: {},
    token: '',
    registerToken: '',
    expirationDate: '',
    urlTokens: [],
    verified: null
  },
  getters: {
    getUser: state => {
      return state.user
    },
    getToken: state => {
      return state.token
    },
    getRegisterToken: state => {
      return state.registerToken
    },
    getExpirationDate: state => {
      return state.expirationDate
    },
    getUrlTokens: state => {
      return state.urlTokens
    },
    getVerified: state => {
      return state.Verified
    }
  },
  actions: {
    setSession (context, token) {
      const jwt = JSON.parse(atob(token.split('.')[1]))
      context.commit('setToken', token)
      context.commit('setExpirationDate', jwt.exp * 1000)
      if (jwt.type) {
        context.commit('setUser', jwt)
      } else {
        context.commit('setUser', JSON.parse(decodeURIComponent(escape(atob(token.split('.')[1])))).data)
      }
    },
    deleteSessionAndGoToLogin (context) {
      localStorage.token = ''
      context.commit('resetStore')
      router.push({ name: 'Login' })
    },
    loginSuccess (context, token) {
      context.dispatch('setSession', token)
      localStorage.token = token
      context.dispatch('openSocket', {})
      context.dispatch('fetchConfig')
      context.dispatch('saveNewLanguage')
      store.dispatch('removeAuthorizationCookie')
      router.push({ name: 'desktops' })
    },
    loginAdmin (context) {
      axios.get(`${apiAdminSegment}/login`, {}, { timeout: 25000 }).catch(e => {
        if (e.response.status === 503) {
          router.push({ name: 'Maintenance' })
        } else {
          console.log(e)
        }
      }).then(() => {
        window.location = `${apiAdminSegment}/admin/landing`
      })
    },
    saveNavigation (context, payload) {
      const tokens = payload.url.name
      context.commit('setUrlTokens', tokens)
    },
    removeAuthorizationCookie (context) {
      cookies.removeCookie('authorization')
    }
  },
  mutations: {
    setUser (state, user) {
      state.user = user
    },
    setToken (state, token) {
      state.token = token
    },
    setRegisterToken (state, registerToken) {
      state.registerToken = registerToken
    },
    setExpirationDate (state, expirationDate) {
      state.expirationDate = expirationDate
    },
    setUrlTokens (state, tokens) {
      state.urlTokens = tokens
    },
    setVerified (state, verified) {
      state.verified = verified
    }
  }
}
