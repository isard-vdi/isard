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
      }).catch(err => {
        console.log(err)
        if (err.response.status === 503) {
          router.push({ name: 'Maintenance' })
        } else {
          router.push({
            name: 'Error',
            params: { code: err.response && err.response.status.toString() }
          })
        }
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
    login (context, data) {
      return new Promise((resolve, reject) => {
        axios.post(`${authenticationSegment}/login`, data, { timeout: 25000 }).then(response => {
          const token = response.data
          const tokenType = JSON.parse(atob(response.data.split('.')[1])).type || ''

          if (tokenType === 'register') {
            store.dispatch('formSuccess', token)
          } else {
            store.dispatch('loginSuccess', token)
          }

          resolve()
        }).catch(e => {
          console.log(e)
          if (e.response.status === 503) {
            reject(e)
            router.push({ name: 'Maintenance' })
          } else {
            console.log(e)
            reject(e)
          }
        })
      })
    },
    async register (context, code) {
      const data = new FormData()
      data.append('code', code)
      await axios.post(`${apiV3Segment}/user/register`, data).then(response => {
        store.dispatch('login')
      }).catch(e => {
        store.dispatch('handleError', e)
      })
    },
    logout (context) {
      axios.get(`${apiAdminSegment}/logout/remote`).catch(e => {
        if (e.response.status === 503) {
          console.log(e)
        } else {
          console.log(e)
        }
      }).then(() => {
        localStorage.token = ''
        context.commit('resetStore')
        router.push({ name: 'Login' })
      })
    },
    watchToken (context) {
      window.addEventListener('storage', (e) => {
        if (e.key === 'token' && e.newValue === null) {
          store.dispatch('logout')
        }
      })
    },
    handleError ({ commit }, error) {
      if (error.response.status === 503) {
        router.push({ name: 'Maintenance' })
        return
      } else if (error.response.status === 404) {
        if (error.response.data.code === 1) { // Register code not found
          commit('setPageErrorMessage', i18n.t('views.register.errors.404'))
          return
        }
      } else if (error.response.status === 401) {
        if (error.response.data.code === 'authorization_header_missing') { // jwt header not sent
          commit('setPageErrorMessage', i18n.t('views.register.errors.401'))
          return
        } else if (error.response.data.code === 'not_allowed') { // jwt token not present
          commit('setPageErrorMessage', i18n.t('views.register.errors.401'))
          return
        }
      }
      commit('setPageErrorMessage', i18n.t('views.error.codes.500'))
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
