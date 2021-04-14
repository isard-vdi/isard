import { apiAxios } from '@/router/auth'
import router from '@/router'

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
        apiAxios.get('/user').then(response => {
          context.commit('setUser', response.data)
          resolve()
        }).catch(e => {
          console.log(e)
          if (e.response.status === 503) {
            reject(e)
            router.push({ name: 'Maintenance' })
          } else if (e.response.status === 401 || e.response.status === 403) {
            this._vm.$snotify.clear()
            reject(e)
            router.push({ name: 'Login' })
          } else {
            reject(e.response)
          }
        })
      })
    }
  },
  mutations: {
    setUser (state, user) {
      state.user = user
    }
  }
}
