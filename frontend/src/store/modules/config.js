import { apiAxios } from '@/router/auth'

export default {
  state: {
    config: {}
  },
  getters: {
    getConfig: state => {
      return state.config
    }
  },
  mutations: {
    setConfig: (state, config) => {
      state.config = config
    }
  },
  actions: {
    async fetchConfig ({ commit }) {
      const rsp = await apiAxios.get('/config')
      commit('setConfig', rsp.data)
    }
  }
}
