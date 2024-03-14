import axios from 'axios'
import { apiV3Segment, authenticationSegment } from '../../shared/constants'
import { ConfigUtils } from '../../utils/configUtils'

export default {
  state: {
    providers: [],
    config: {}
  },
  getters: {
    getProviders: state => {
      return state.providers
    },
    getConfig: state => {
      return state.config
    }
  },
  mutations: {
    setProviders: (state, providers) => {
      state.providers = providers
    },
    setConfig: (state, config) => {
      state.config = config
    }
  },
  actions: {
    async fetchProviders ({ commit }) {
      const rsp = await axios.get(`${authenticationSegment}/providers`)
      commit('setProviders', rsp.data.providers)
    },
    async fetchConfig ({ commit }) {
      const rsp = await axios.get(`${apiV3Segment}/user/config`)
      commit('setConfig', ConfigUtils.parseConfig(rsp.data))
    },
    async fetchMaintenanceText ({ _ }) {
      const rsp = await axios.get(`${apiV3Segment}/maintenance/text/frontend`)
      return rsp.data
    },
    async fetchMaintenanceStatus ({ _ }) {
      const rsp = await axios.get(`${apiV3Segment}/maintenance`)
      return rsp.data
    }
  }
}
