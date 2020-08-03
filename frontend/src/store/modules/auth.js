import * as cookies from 'tiny-cookie'

export default {
  state: {
    user: {}
  },
  getters: {
    getUser: state => {
      return state.user
    }
  },
  actions: {
    setUser (context) {
      return new Promise((resolve, reject) => {
        context.commit('setUser')
      })
    }
  },
  mutations: {
    setUser (state) {
      const isard = JSON.parse(atob(cookies.get('isard')))

      state.user = {
        name: isard.name,
        templates: isard.templates
      }
    }
  }
}
