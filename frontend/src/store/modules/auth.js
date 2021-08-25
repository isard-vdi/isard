import router from '@/router'
import axios from 'axios'
import { apiAdminSegment } from '@/shared/constants'
import store from '@/store/index.js'
import * as cookies from 'tiny-cookie'

export default {
  state: {
    user: {
      UID: '',
      Username: '',
      Provider: '',
      Category: '',
      role: '',
      group: '',
      name: '',
      email: '',
      photo: ''
    },
    token: '',
    registerToken: '',
    expirationDate: ''
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
    }
  },
  actions: {
    setSession (context, token) {
      context.commit('setToken', token)
      context.commit('setExpirationDate', JSON.parse(atob(token.split('.')[1])).exp * 1000)
      context.commit('setUser', JSON.parse(atob(token.split('.')[1])).data)
    },
    loginSuccess (context, token) {
      context.dispatch('setSession', token)
      localStorage.token = token
      store.dispatch('loginAdmin')
      store.dispatch('removeAuthorizationCookie')
      router.push({ name: 'Home' })
    },
    loginAdmin (context) {
      axios.get(`${apiAdminSegment}/login/external`, {}, { timeout: 25000 }).catch(e => {
        if (e.response.status === 503) {
          router.push({ name: 'Maintenance' })
        } else {
          console.log(e)
        }
      })
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
    }
  }
}
