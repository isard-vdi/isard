import axios from 'axios'
import { apiV3Segment, authenticationSegment } from '../../shared/constants'
import { ConfigUtils } from '../../utils/configUtils'
import { jwtDecode } from 'jwt-decode'
import store from '@/store'

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
        const now = Date.now()
        const timeDrift = store.getters.getTimeDrift
        const adjustedNow = now + timeDrift

        const session = store.getters.getSession
        if (session) {
          const sessionData = jwtDecode(session)

          // Token expiration time (when renewal window starts)
          const tokenExpiration = sessionData.exp * 1000

          // Max renew time from config (when renewal window ends)
          const maxRenewTime = store.getters.getConfig.session.maxRenewTime * 1000

          // Show renewal modal 30 seconds before token expiration
          const renewalWindowDelay = tokenExpiration - adjustedNow - 30000
          if (renewalWindowDelay > 0) {
            context.commit('addTimeout', setTimeout(() => {
              context.dispatch('showExpiredSessionModal', 'renew')
            }, renewalWindowDelay))
          // Unlikely case: If the session is expired, the axios interceptor or router should have already attempted renewal before fetchConfig runs
          // but in case fetchConfig is called before that happens, check if we're already in the renewal window
          // and show the modal immediately
          } else if (adjustedNow < maxRenewTime) {
            context.dispatch('showExpiredSessionModal', 'renew')
          }

          // Force logout when max renew time is reached
          const forceLogoutDelay = maxRenewTime - adjustedNow
          if (forceLogoutDelay > 0) {
            context.commit('addTimeout', setTimeout(() => {
              context.dispatch('showExpiredSessionModal', 'expired')
            }, forceLogoutDelay))
          // Unlikely case: If max renew time has already passed, force logout immediately
          } else {
            context.dispatch('showExpiredSessionModal', 'expired')
          }
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
