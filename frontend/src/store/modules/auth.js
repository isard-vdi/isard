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
    urlTokens: []
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
    }
  },
  actions: {
    setSession (context, token) {
      context.commit('setToken', token)
      context.commit('setExpirationDate', JSON.parse(atob(token.split('.')[1])).exp * 1000)
      context.commit('setUser', JSON.parse(decodeURIComponent(escape(atob(token.split('.')[1])))).data)
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
        window.location = `${apiAdminSegment}/admin/domains/render/Desktops`
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
    }
  }
}
