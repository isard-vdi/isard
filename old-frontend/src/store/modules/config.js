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
      // Clear all existing timeouts before setting new ones
      context.commit('clearTimeouts')

      const rsp = await axios.get(`${apiV3Segment}/user/config`)
      context.commit('setConfig', ConfigUtils.parseConfig(rsp.data))

      // Skip session management for isardvdi-service sessions
      if (context.getters.getConfig.session?.id === 'isardvdi-service') {
        console.debug('❌ Service session detected, skipping session timeouts')
        return
      }

      const session = store.getters.getSession
      if (!session) {
        console.debug('❌ No session found, skipping timeout setup')
        return
      }

      const now = Date.now()
      const timeDrift = store.getters.getTimeDrift
      const adjustedNow = now + (Math.abs(timeDrift) < 86400000 ? timeDrift : 0)

      const sessionData = jwtDecode(session)
      const tokenExpiration = sessionData.exp * 1000
      const maxRenewTime = context.getters.getConfig.session.maxRenewTime * 1000
      const maxTime = context.getters.getConfig.session.maxTime * 1000

      const timeToExpiry = tokenExpiration - adjustedNow
      const timeToMaxRenew = maxRenewTime - adjustedNow

      console.debug('⏰ Setting up session timeouts:', {
        tokenExpiry: new Date(tokenExpiration).toLocaleString(),
        maxRenewTime: new Date(maxRenewTime).toLocaleString(),
        maxTime: new Date(maxTime).toLocaleString(),
        timeToExpiry: Math.round(timeToExpiry / 1000) + 's',
        timeToMaxRenew: Math.round(timeToMaxRenew / 1000) + 's'
      })

      // Case 1: Max renew time equals max time - no renewal possible
      if (context.getters.getConfig.session.maxRenewTime === context.getters.getConfig.session.maxTime) {
        console.debug('🔒 No renewal window (maxRenewTime === maxTime)')
        if (timeToExpiry > 0) {
          context.commit('addTimeout', setTimeout(() => {
            console.debug('🔒 Max session time reached (no renewal)')
            context.dispatch('showExpiredSessionModal', 'max-time')
          }, timeToMaxRenew))
        } else {
          context.dispatch('showExpiredSessionModal', 'max-time')
        }
        return
      }

      // Case 2: Normal session with renewal window
      // Show renewal modal 1 minute before maxRenewTime is reached
      const oneMinute = 60 * 1000 // 60 seconds in milliseconds
      const timeToRenewalWarning = timeToMaxRenew - oneMinute

      if (timeToRenewalWarning > 0) {
        context.commit('addTimeout', setTimeout(() => {
          console.debug('🔄 Showing renewal modal (1 minute before max renew time)')
          context.dispatch('showExpiredSessionModal', 'renew')
        }, timeToRenewalWarning))
      } else if (timeToMaxRenew > 0) {
        // Less than 1 minute until max renew time - show modal immediately
        console.debug('⏰ Less than 1 minute until max renew time, showing modal now')
        context.dispatch('showExpiredSessionModal', 'renew')
      }

      // Set max renew time timeout (when renewal window ends)
      if (timeToMaxRenew > 0) {
        context.commit('addTimeout', setTimeout(() => {
          console.debug('🔒 Max renewal time reached')
          context.dispatch('showExpiredSessionModal', 'max-renew-time')
        }, timeToMaxRenew))
      } else {
        // Already past max renew time
        console.debug('🔒 Already past max renewal time')
        context.dispatch('showExpiredSessionModal', 'max-renew-time')
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
