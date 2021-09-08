import axios from 'axios'
import { authenticationSegment } from '../../shared/constants'

export default {
  state: {
    config: {
      providers: [],
      show_admin_button: false
    }
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
      const rsp = await axios.get(`${authenticationSegment}/config`)
      commit('setConfig', rsp.data)
    }
  }
}
