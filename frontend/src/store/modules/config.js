import { apiAxios } from '@/router/auth'

export default {
  state: {
    config: {},
    configLoaded: false
  },
  getters: {
    getConfig: state => {
      return state.config
    },
    getConfigLoaded: state => {
      return state.configLoaded
    }
  },
  mutations: {
    setConfig: (state, config) => {
      state.config = config
      state.configLoaded = true
    }
  },
  actions: {
    async fetchConfig ({ commit }) {
      const rsp = await apiAxios.get('/config')
      commit('setConfig', rsp.data)
    }
  }
}
