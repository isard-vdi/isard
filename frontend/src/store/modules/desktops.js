import * as cookies from 'tiny-cookie'

import { apiAxios } from '@/router/auth'
import i18n from '@/i18n'
import router from '@/router'
import { toast } from '@/store/index.js'

export default {
  state: {
    viewer: cookies.getCookie('viewer') || '',
    desktops: [],
    desktops_loaded: false
  },
  getters: {
    getDesktops: state => {
      return state.desktops
    },
    getDesktopsLoaded: state => {
      return state.desktops_loaded
    },
    getViewer: state => {
      return state.viewer
    }
  },
  mutations: {
    setDesktops: (state, desktops) => {
      state.desktops = desktops
      state.desktops_loaded = true
    },
    setViewer: (state, viewer) => {
      state.viewer = viewer
    }
  },
  actions: {
    fetchDesktops ({ commit }) {
      return new Promise((resolve, reject) => {
        apiAxios.get('/desktops').then(response => {
          commit('setDesktops', response.data)
          resolve()
        }).catch(e => {
          console.log(e)
          if (e.response.status === 503) {
            reject(e)
            router.push({ name: 'Maintenance' })
          } else if (e.response.status === 401 || e.response.status === 403) {
            this._vm.$snotify.clear()
            reject(e)
            router.push({ name: 'ExpiredSession' })
          } else {
            reject(e.response)
          }
        })
      })
    },
    createDesktop (context, data) {
      return this._vm.$snotify.async(
        i18n.t('views.select-template.notification.loading.description'),
        i18n.t('views.select-template.notification.loading.title'),
        () => new Promise((resolve, reject) => {
          apiAxios.post('/create', data, { timeout: 25000 }).then(response => {
            context.dispatch('fetchDesktops')
            this._vm.$snotify.clear()
            resolve()
          }).catch(e => {
            if (e.response.status === 503) {
              reject(e)
              router.push({ name: 'Maintenance' })
            } else if (e.response.status === 401 || e.response.status === 403) {
              this._vm.$snotify.clear()
              reject(e)
              router.push({ name: 'ExpiredSession' })
            } else if (e.response.status === 507) {
              reject(
                toast(
                  i18n.t('views.select-template.error.create-quota.title'),
                  i18n.t('views.select-template.error.create-quota.description')
                )
              )
            } else {
              reject(
                toast(
                  i18n.t('views.select-template.error.create-error.title'),
                  i18n.t('views.select-template.error.create-error.description')
                )
              )
            }
          })
        })
      )
    },
    changeDesktopStatus (context, data) {
      return this._vm.$snotify.async(
        i18n.t('views.select-template.notification.loading.description'),
        i18n.t('views.select-template.notification.loading.title'),
        () => new Promise((resolve, reject) => {
          apiAxios.post(`/desktop/${data.desktopId}/${data.action}`).then(response => {
            context.dispatch('fetchDesktops')
            this._vm.$snotify.clear()
            resolve()
          }).catch(e => {
            if (e.response.status === 503) {
              reject(e)
              router.push({ name: 'Maintenance' })
            } else if (e.response.status === 408) {
              resolve(
                toast(
                  i18n.t(`views.select-template.error.${data.action}-timeout.title`),
                  i18n.t(`views.select-template.error.${data.action}-timeout.description`)
                )
              )
            } else if (e.response.status === 507) {
              reject(
                toast(
                  i18n.t(`views.select-template.error.${data.action}-quota.title`),
                  i18n.t(`views.select-template.error.${data.action}-quota.description`)
                )
              )
            } else if (e.response.status === 401 || e.response.status === 403) {
              this._vm.$snotify.clear()
              reject(e)
              router.push({ name: 'ExpiredSession' })
            } else {
              reject(
                toast(
                  i18n.t(`views.select-template.error.${data.action}-error.title`),
                  i18n.t(`views.select-template.error.${data.action}-error.description`)
                )
              )
            }
          })
        })
      )
    },
    openDesktop (context, data) {
      return this._vm.$snotify.async(
        i18n.t('views.select-template.notification.loading.description'),
        i18n.t('views.select-template.notification.loading.title'),
        () => new Promise((resolve, reject) => {
          cookies.setCookie('viewer', data.viewer)
          context.commit('setViewer', data.viewer)
          apiAxios.get(`/desktop/${data.desktopId}/viewer/${data.viewer}`).then(response => {
            const el = document.createElement('a')
            if (data.viewer === 'browser') {
              const spiceUrl = `${window.location.protocol}//${window.location.host}/viewer/noVNC/`
              el.setAttribute('href', spiceUrl)
              console.log(spiceUrl)
              el.setAttribute('target', '_blank')
              document.body.appendChild(el)
              el.click()
              this._vm.$snotify.clear()
              resolve()
            } else {
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
                  i18n.t('views.select-template.notification.downloaded.title'),
                  i18n.t('views.select-template.notification.downloaded.description')
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
                  i18n.t('views.select-template.error.open-error.title'),
                  i18n.t('views.select-template.error.open-error.description')
                )
              )
            }
          })
        })
      )
    },
    deleteDesktop (context, desktopId) {
      return this._vm.$snotify.async(
        i18n.t('views.select-template.notification.loading.description'),
        i18n.t('views.select-template.notification.loading.title'),
        () => new Promise((resolve, reject) => {
          apiAxios.delete(`/desktop/${desktopId}`).then(response => {
            context.dispatch('fetchDesktops')
            this._vm.$snotify.clear()
            resolve()
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
                  i18n.t('views.select-template.error.delete-error.title'),
                  i18n.t('views.select-template.error.delete-error.description')
                )
              )
            }
          })
        })
      )
    }
  }
}
