import axios from 'axios'
import { apiV3Segment, authenticationSegment } from '../../shared/constants'
import { ConfigUtils } from '../../utils/configUtils'

export default {
  state: {
    providers: [],
    config: {},
    timeouts: []
  },
  getters: {
    getProviders: state => {
      return state.providers
    },
    getConfig: state => {
      return state.config
    },
    getStatusBarNotification: state => {
      return state.statusBarNotification
    }
  },
  mutations: {
    setProviders: (state, providers) => {
      state.providers = providers
    },
    setConfig: (state, config) => {
      state.config = config
    },
    setStatusBarNotification: (state, notification) => {
      state.statusBarNotification = notification
    },
    addTimeout: (state, timeout) => {
      state.timeouts.push(timeout)
    },
    clearTimeouts: (state) => {
      state.timeouts.forEach(timeout => {
        clearTimeout(timeout)
      })
      state.timeouts = []
    }
  },
  actions: {
    async fetchProviders ({ commit }) {
      const rsp = await axios.get(`${authenticationSegment}/providers`)
      commit('setProviders', rsp.data.providers)
    },
    async fetchConfig (context) {
      const rsp = await axios.get(`${apiV3Segment}/user/config`)
      context.commit('setConfig', ConfigUtils.parseConfig(rsp.data))
      // Impersonate has an id of "isard-service" and we don't want to show the session modal
      if (context.getters.getConfig.session.id !== 'isardvdi-service') {
        // Clear all timeouts
        context.commit('clearTimeouts')
        // Create a new timeout that shows a modal when the session is about to expire (5 minutes before)
        if (context.getters.getConfig.session.maxRenewTime < context.getters.getConfig.session.maxTime) {
          context.commit('addTimeout', setTimeout(() => {
            context.dispatch('showExpiredSessionModal', 'renew')
          }, (context.getters.getConfig.session.maxRenewTime * 1000 - 300000) - Date.now()))
          // Create a new timeout that shows a modal when the session is expired
          context.commit('addTimeout', setTimeout(() => {
            context.dispatch('showExpiredSessionModal', 'expired')
          }, context.getters.getConfig.session.maxRenewTime * 1000 - Date.now()))
        } else {
          context.commit('addTimeout', setTimeout(() => {
            context.dispatch('showExpiredSessionModal', 'renew')
          }, (context.getters.getConfig.session.maxTime * 1000 - 300000) - Date.now()))
        }
      }
    },
    async fetchMaintenanceText ({ _ }) {
      const rsp = await axios.get(`${apiV3Segment}/maintenance/text/frontend`)
      return rsp.data
    },
    async fetchMaintenanceStatus ({ _ }) {
      const rsp = await axios.get(`${apiV3Segment}/maintenance`)
      return rsp.data
    },
    async fetchStatusBarNotification ({ commit }) {
      const rsp = await axios.get(`${apiV3Segment}/notifications/status_bar`)
      commit('setStatusBarNotification', rsp.data)
    }
  }
}
