import Vue from 'vue'
import Vuex from 'vuex'
import auth from './modules/auth'
import templates from './modules/templates'
import { apiAxios } from '@/router/auth'
import router from '@/router'
import i18n from '@/i18n'

import * as cookies from 'tiny-cookie'

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
  },
  mutations: {
  },
  actions: {
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
    createDesktop (context, data) {
      return new Promise((resolve, reject) => {
        apiAxios.post('/create', data, { timeout: 25000 }).then(response => {
          resolve()
        }).catch(e => {
          console.log(e)
          reject(e)
        })
      })
    },
    openDesktop (context, desktopType) {
      return this._vm.$snotify.async(
        i18n.t('views.landing.notification.loading.description'),
        i18n.t('views.landing.notification.loading.title'),
        () => new Promise((resolve, reject) => {
          apiAxios.get(`/viewer?type=${desktopType}`).then(response => {
            const el = document.createElement('a')
            if (desktopType === 'remote') {
              const content = JSON.parse(atob(cookies.get('isard'))).remote_viewer
              el.setAttribute(
                'href',
                `data:application/x-virt-viewer;charset=utf-8,${encodeURIComponent(content)}`
              )
              el.setAttribute('download', 'escriptori.vv')
              el.style.display = 'none'
              document.body.appendChild(el)
              el.click()
              document.body.removeChild(el)
              resolve(
                toast(
                  i18n.t('views.landing.notification.downloaded.title'),
                  i18n.t('views.landing.notification.downloaded.description')
                )
              )
            } else {
              const spiceUrl = `${window.location.protocol}//${window.location.host}/viewer/noVNC/`
              el.setAttribute('href', spiceUrl)
              console.log(spiceUrl)
              el.setAttribute('target', '_blank')
              document.body.appendChild(el)
              el.click()
              resolve(
                toast(
                  i18n.t('views.landing.notification.opened.title'),
                  i18n.t('views.landing.notification.opened.description')
                )
              )
            }
          }).catch(e => {
            if (e.response.status === 503) {
              reject(e)
              router.push({ name: 'Maintenance' })
            } else if (e.response.status === 401 || e.response.status === 403) {
              this._vm.$snotify.clear()
              reject(e)
              router.push({ name: 'ExpiredSession' })
            } else {
              reject(
                toast(
                  i18n.t('views.landing.notification.error.title'),
                  i18n.t('views.landing.notification.error.description')
                )
              )
            }
          })
        })
      )
    },
    destroyDesktop (context) {
      window.location = `${window.location.protocol}//${window.location.host}/api/v2/logout`
    }
  },
  modules: {
    auth,
    templates
  }
})
