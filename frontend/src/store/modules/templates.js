import { apiAxios } from '@/router/auth'

export default {
  state: {
    templates: [],
    templates_loaded: false
  },
  getters: {
    getTemplates: state => {
      return state.templates
    },
    getTemplatesLoaded: state => {
      return state.templates_loaded
    }
  },
  mutations: {
    setTemplates: (state, templates) => {
      state.templates = templates
      state.templates_loaded = true
    }
  },
  actions: {
    async fetchTemplates ({ commit }) {
      const response = await apiAxios.get('/templates')
      commit('setTemplates', response.data)
    }
  }
}
