// import i18n from '@/i18n'
import { apiV3Segment } from '@/shared/constants'
// import store from '@/store/index.js'
import axios from 'axios'
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
import messageTemplate from './modules/messageTemplate'
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
    resetStore (state) {
      state.auth.user = null
      state.auth.session = false
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
    showMessageModal (context, show) {
      context.commit('setShowMessageModal', show)
    },
    checkCreateQuota (context, data) {
      return axios.get(`${apiV3Segment}/${data.itemType}/new/check_quota`).then(response => {
        context.dispatch('navigate', data.routeName)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    checkHypervisorAvailability () {
      return axios.get(`${apiV3Segment}/admin/storage_pool/availability`).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    checkHyperAvailableAndQuota (context, data) {
      return context.dispatch('checkHypervisorAvailability').then(response => {
        if (response.status === 200) {
          context.dispatch('checkCreateQuota', data)
        }
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
    recycleBin,
    messageTemplate
  }
})
