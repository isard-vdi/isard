import Vue from 'vue'
import Vuex from 'vuex'
import router from '@/router'
import { apiAxios } from '@/router/auth'
import auth from './modules/auth'
import config from './modules/config'
import desktops from './modules/desktops'
import templates from './modules/templates'
import vpn from './modules/vpn'

Vue.use(Vuex)

export function toast (titol, missatge) {
  return {
    title: titol,
    body: missatge,
    config: {
      timeout: 5000,
      showProgressBar: true,
      closeOnClick: true,
      pauseOnHover: true
    }
  }
}

export default new Vuex.Store({
  state: {
    categories: []
  },
  getters: {
    getCategories: state => {
      return state.categories
    }
  },
  mutations: {
    setCategories (state, categories) {
      state.categories = categories
    }
  },
  actions: {
    fetchCategories ({ commit }) {
      return apiAxios.get('/categories').then(response => {
        commit('setCategories', response.data)
      }).catch(err => {
        console.log(err)
        if (err.response.status === 503) {
          router.push({ name: 'Maintenance' })
        } else {
          router.push({
            name: 'Error',
            params: { code: err.response && err.response.status.toString() }
          })
        }
      })
    },
    maintenance (context) {
      return new Promise((resolve, reject) => {
        apiAxios.get('/check').then(response => {
          resolve()
        }).catch(e => {
          console.log(e)
          reject(e)
        })
      })
    },
    login (context, data) {
      return new Promise((resolve, reject) => {
        apiAxios.post(`/login/${data.get('category')}?provider=${data.get('provider')}&redirect=/`, data, { timeout: 25000 }).then(response => {
          resolve()
        }).catch(e => {
          if (e.response.status === 503) {
            reject(e)
            router.push({ name: 'Maintenance' })
          } else {
            console.log(e)
            reject(e)
          }
        })
      })
    },
    logout (context) {
      window.location = `${window.location.protocol}//${window.location.host}/api/v2/logout`
    }
  },
  modules: {
    auth,
    templates,
    desktops,
    config,
    vpn
  }
})
