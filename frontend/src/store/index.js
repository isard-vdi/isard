import i18n from '@/i18n'
import Vue from 'vue'
import Vuex from 'vuex'
import router from '@/router'
import axios from 'axios'
import auth from './modules/auth'
import config from './modules/config'
import desktops from './modules/desktops'
import templates from './modules/templates'
import sockets from './modules/sockets'
import deployments from './modules/deployments'
import vpn from './modules/vpn'
import store from '@/store/index.js'
import { authenticationSegment, apiV3Segment, apiAdminSegment } from '@/shared/constants'
import { getCookie } from 'tiny-cookie'

Vue.use(Vuex)

export function toast (titol, missatge) {
  return {
    title: titol,
    body: missatge,
    config: {
      timeout: 5000,
      showProgressBar: true,
      closeOnClick: true,
      pauseOnHover: true
    }
  }
}

export default new Vuex.Store({
  state: {
    categories: [],
    pageErrorMessage: ''
  },
  getters: {
    getCategories: state => {
      return state.categories
    },
    getPageErrorMessage: state => {
      return state.pageErrorMessage
    }
  },
  mutations: {
    setCategories (state, categories) {
      state.categories = categories
    },
    setPageErrorMessage (state, errorMessage) {
      state.pageErrorMessage = errorMessage
    },
    resetStore (state) {
      state.auth.user = {
        UID: '',
        Username: '',
        Provider: '',
        Category: '',
        role: '',
        group: '',
        name: '',
        email: '',
        photo: ''
      }
      state.auth.token = ''
      state.auth.expirationDate = ''
      state.desktops.viewers = localStorage.viewers ? JSON.parse(localStorage.viewers) : {}
      state.desktops.desktops = []
      state.desktops.desktops_loaded = false
      state.desktops.viewType = 'grid'
      state.desktops.showStarted = false
      state.templates.templates = []
      state.templates.templates_loaded = false
    },
    cleanStoreOnNavigation (state) {
      state.pageErrorMessage = ''
    }
  },
  actions: {
    fetchCategories ({ commit }) {
      return axios.get(`${apiV3Segment}/categories`).then(response => {
        commit('setCategories', response.data)
      })
    },
    maintenance (context) {
      return new Promise((resolve, reject) => {
        axios.get(`${apiV3Segment}/check`).then(response => {
          resolve()
        }).catch(e => {
          console.log(e)
          reject(e)
        })
      })
    },
    handleLoginError ({ commit }, e) {
      if (e.response.status === 401) {
        commit('setPageErrorMessage', i18n.t('views.login.errors.401'))
      } else if (e.response.status === 403 && e.response.data === 'disabled user') {
        commit('setPageErrorMessage', i18n.t('errors.user_disabled'))
      } else if (e.response.status === 500) {
        commit('setPageErrorMessage', i18n.t('views.login.errors.500'))
      } else {
        commit('setPageErrorMessage', i18n.t('views.login.errors.generic'))
      }
    },
    login ({ commit }, data) {
      return new Promise((resolve, reject) => {
        axios.create().post(`${authenticationSegment}/login`, data, { timeout: 25000 }).then(response => {
          const jwt = JSON.parse(atob(response.data.split('.')[1]))
          if (jwt.type === 'register') {
            router.push({ name: 'Register' })
          } else {
            store.dispatch('loginSuccess', response.data)
          }

          resolve()
        }).catch(e => {
          store.dispatch('handleLoginError', e)
          reject(e)
        })
      })
    },
    async register (context, code) {
      const data = new FormData()
      data.append('code', code)
      const registerAxios = axios.create()
      registerAxios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${getCookie('authorization')}`
        return config
      })
      await registerAxios.post(`${apiV3Segment}/user/register`, data).then(response => {
        return new Promise((resolve, reject) => {
          registerAxios.post(`${authenticationSegment}/login`, data, { timeout: 25000 }).then(response => {
            store.dispatch('loginSuccess', response.data)
            resolve()
          }).catch(e => {
            store.dispatch('handleLoginError', e)
            reject(e)
          })
        })
      }).catch(e => {
        store.dispatch('handleRegisterError', e)
      })
    },
    logout (context) {
      axios.get(`${apiAdminSegment}/logout/remote`).then(() => {
        localStorage.token = ''
        context.commit('resetStore')
        if (!store.getters.getUrlTokens.includes('login')) {
          router.push({ name: 'Login' })
        }
      })
    },
    watchToken (context) {
      window.addEventListener('storage', (e) => {
        if (localStorage.token === undefined) {
          store.dispatch('logout')
        } else if (e.key === 'token' && e.newValue === null) {
          store.dispatch('logout')
        }
      })
    },
    handleRegisterError ({ commit }, error) {
      if (error.response.status === 404) {
        commit('setPageErrorMessage', i18n.t('views.register.errors.404'))
        return
      } else if (error.response.status === 401) {
        if (error.response.data.error === 'authorization_header_missing') { // jwt header not sent
          commit('setPageErrorMessage', i18n.t('views.register.errors.401'))
          return
        } else if (error.response.data.error === 'not_allowed') { // jwt token not present
          commit('setPageErrorMessage', i18n.t('views.register.errors.401'))
          return
        }
      }
      commit('setPageErrorMessage', i18n.t('views.error.codes.500'))
    },
    parseErrorFromQuery ({ commit }, error) {
      const errID = 'errors.' + error
      if (i18n.t(errID) !== errID) {
        commit('setPageErrorMessage', i18n.t(errID))
      } else {
        commit('setPageErrorMessage', i18n.t('views.error.codes.500'))
      }
    }
  },
  modules: {
    auth,
    templates,
    desktops,
    deployments,
    config,
    vpn,
    sockets
  }
})
