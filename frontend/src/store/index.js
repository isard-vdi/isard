import i18n from '@/i18n'
import router from '@/router'
import { apiAdminSegment, apiV3Segment, authenticationSegment } from '@/shared/constants'
import store from '@/store/index.js'
import axios from 'axios'
import { getCookie } from 'tiny-cookie'
import Vue from 'vue'
import Vuex from 'vuex'
import { ErrorUtils } from '../utils/errorUtils'
import allowed from './modules/allowed'
import auth from './modules/auth'
import booking from './modules/booking'
import config from './modules/config'
import deployment from './modules/deployment'
import deployments from './modules/deployments'
import domain from './modules/domain'
import desktops from './modules/desktops'
import media from './modules/media'
import planning from './modules/planning'
import profile from './modules/profile'
import recycleBin from './modules/recycleBin'
import snotify from './modules/snotify'
import sockets from './modules/sockets'
import storage from './modules/storage'
import template from './modules/template'
import templates from './modules/templates'
import vpn from './modules/vpn'
import { MessageUtils } from '../utils/messageUtils'

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
    category: {},
    pageErrorMessage: '',
    currentInternalTime: '',
    messageModal: {
      show: false,
      title: '',
      message: ''
    }
  },
  getters: {
    getCategories: state => {
      return state.categories
    },
    getCategory: state => {
      return state.category
    },
    getPageErrorMessage: state => {
      return state.pageErrorMessage
    },
    getMessageModal: state => {
      return state.messageModal
    }
  },
  mutations: {
    setCategories (state, categories) {
      state.categories = categories
    },
    setCategory (state, category) {
      state.category = category
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
    },
    setMessageModal: (state, message) => {
      state.messageModal = message
    },
    setShowMessageModal: (state, show) => {
      state.messageModal.show = show
    }
  },
  actions: {
    socket_msg (context, data) {
      context.commit('setMessageModal', MessageUtils.parseMessage(JSON.parse(data)))
    },
    fetchCategories ({ commit }) {
      return axios.get(`${apiV3Segment}/categories`).then(response => {
        commit('setCategories', response.data)
      })
    },
    fetchCategory (context, customUrl) {
      return axios.get(`${apiV3Segment}/category/` + customUrl).then(response => {
        context.commit('setCategory', response.data)
      }).catch(e => {
        if (e.response.status === 404) {
          context.dispatch('navigate', 'NotFound')
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
    handleLoginError ({ commit }, e) {
      if (e.response.status === 401) {
        commit('setPageErrorMessage', i18n.t('views.login.errors.401'))
      } else if (e.response.status === 403 && e.response.data === 'disabled user') {
        commit('setPageErrorMessage', i18n.t('errors.user_disabled'))
      } else if (e.response.status === 429) {
        commit('setPageErrorMessage', i18n.t('views.login.errors.429'))
      } else if (e.response.status === 500) {
        commit('setPageErrorMessage', i18n.t('views.login.errors.500'))
      } else {
        commit('setPageErrorMessage', i18n.t('views.login.errors.generic'))
      }
    },
    login (context, data) {
      return new Promise((resolve, reject) => {
        axios.create().post(`${authenticationSegment}/login?provider=${data.get('provider')}&category_id=${data.get('category_id')}&username=${data.get('username')}`, data, { timeout: 25000 }).then(response => {
          const jwt = JSON.parse(atob(response.data.split('.')[1]))
          if (jwt.type === 'register') {
            router.push({ name: 'Register' })
          } else if (jwt.type === 'email-verification-required') {
            localStorage.token = response.data
            context.dispatch('setSession', response.data)
            router.push({ name: 'VerifyEmail' })
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
      const provider = JSON.parse(atob(getCookie('authorization').split('.')[1])).provider
      await registerAxios.post(`${apiV3Segment}/user/register`, data).then(response => {
        return new Promise((resolve, reject) => {
          registerAxios.post(`${authenticationSegment}/login?provider=${provider}`, data, { timeout: 25000 }).then(response => {
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
        context.dispatch('closeSocket')
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
      } else if (error.response.status === 429) {
        commit('setPageErrorMessage', i18n.t('views.login.errors.429'))
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
    },
    showErrorPopUp (context, errorMessageCode) {
      console.log(errorMessageCode)
      const errorMessageText = ErrorUtils.getErrorMessageText(errorMessageCode)
      console.log(errorMessageText)
      ErrorUtils.showErrorNotification(this._vm.$snotify, errorMessageText)
    },
    showMessageModal (context, show) {
      context.commit('setShowMessageModal', show)
    },
    checkCreateQuota (context, data) {
      axios.get(`${apiV3Segment}/${data.itemType}/new/check_quota`).then(response => {
        context.dispatch('navigate', data.routeName)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    sendResetPasswordEmail (context, data) {
      const forgotPasswordAxios = axios.create()
      return forgotPasswordAxios.post(`${authenticationSegment}/forgot-password`, data).then(response => {
        router.push({ name: 'Login' })
      }).catch(e => {
        ErrorUtils.showErrorMessage(e, this._vm.$snotify)
      })
    },
    updateForgottenPassword (context, data) {
      const forgotPasswordAxios = axios.create()
      forgotPasswordAxios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${data.token}`
        return config
      })

      return forgotPasswordAxios.post(`${authenticationSegment}/reset-password`, data).then(response => {
        router.push({ name: 'Login' })
      }).catch(e => {
        ErrorUtils.showErrorMessage(e, this._vm.$snotify)
      })
    },
    sendVerifyEmail (context, data) {
      const verifyEmailAxios = axios.create()
      verifyEmailAxios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${localStorage.token}`
        return config
      })
      return verifyEmailAxios.post(`${authenticationSegment}/request-email-verification`, data).catch(e => {
        ErrorUtils.showErrorMessage(e, this._vm.$snotify)
      })
    },
    verifyEmail (context, token) {
      const verifyEmailAxios = axios.create()
      verifyEmailAxios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${token}`
        return config
      })
      return verifyEmailAxios.post(`${authenticationSegment}/verify-email`, {}).catch(e => {
        ErrorUtils.showErrorMessage(e, this._vm.$snotify)
      })
    }
  },
  modules: {
    auth,
    templates,
    template,
    desktops,
    domain,
    deployments,
    deployment,
    config,
    vpn,
    sockets,
    allowed,
    booking,
    snotify,
    planning,
    profile,
    media,
    storage,
    recycleBin
  }
})
