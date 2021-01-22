import Vue from 'vue'
import Vuex from 'vuex'
import { apiAxios } from '@/router/auth'
import auth from './modules/auth'
import config from './modules/config'
import desktops from './modules/desktops'
import templates from './modules/templates'

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
  mutations: {
    setCategories (state, categories) {
      state.categories = categories
    }
  },
  actions: {
    fetchCategories ({ commit }) {
      return new Promise((resolve, reject) => {
        apiAxios.get('/categories').then(response => {
          commit('setCategories', response.data)
          resolve()
        }).catch(e => {
          console.log(e)
          reject(e.response)
        })
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
        apiAxios.post(`/login/${data.get('category')}?provider=${data.get('provider')}&redirect=/select_template`, data, { timeout: 25000 }).then(response => {
          resolve()
        }).catch(e => {
          console.log(e)
          reject(e)
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
    config
  }
})
