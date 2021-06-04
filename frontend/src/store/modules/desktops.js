import * as cookies from 'tiny-cookie'
import { apiAxios } from '@/router/auth'
import i18n from '@/i18n'
import router from '@/router'
import { toast } from '@/store/index.js'
import { desktopStates } from '../../shared/constants'
import { DesktopUtils } from '../../utils/desktopsUtils'

var polling

function pollDesktops (context) {
  if (!polling) {
    polling = setInterval(() => {
      context.dispatch('fetchDesktops')
    }, 5000)
  }
}

export function clearPolling () {
  if (polling) {
    clearInterval(polling)
    polling = null
  }
}

export default {
  state: {
    viewers: cookies.getCookie('viewers') ? JSON.parse(cookies.getCookie('viewers')) : {},
    desktops: [],
    desktops_loaded: false,
    viewType: 'grid',
    showStarted: false
  },
  getters: {
    getDesktops: state => {
      return state.desktops
    },
    getDesktopsLoaded: state => {
      return state.desktops_loaded
    },
    getViewers: state => {
      return state.viewers
    },
    getViewType: state => {
      return state.viewType
    },
    getShowStarted: state => {
      return state.showStarted
    }
  },
  mutations: {
    setDesktops: (state, desktops) => {
      state.desktops = desktops
      state.desktops_loaded = true
    },
    updateViewers: (state, viewers) => {
      state.viewers = { ...state.viewers, ...viewers }
      cookies.setCookie('viewers', JSON.stringify(state.viewers))
    },
    setViewType: (state, type) => {
      state.viewType = type
    },
    toggleShowStarted: (state, type) => {
      state.showStarted = !state.showStarted
    }
  },
  actions: {
    loadViewers (context, viewers) {
      context.commit('updateViewers', viewers)
    },
    fetchDesktops (context) {
      return new Promise((resolve, reject) => {
        apiAxios.get('/desktops').then(response => {
          context.commit('setDesktops', DesktopUtils.parseDesktops(response.data))
          if (response.data.find(desktop => desktop.state.toLowerCase() === desktopStates.waitingip)) {
            pollDesktops(context)
          } else {
            clearPolling()
          }
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
            } else if (e.response.status === 408) {
              pollDesktops(context)
              resolve(
                toast(
                  i18n.t('views.select-template.error.create-timeout.title'),
                  i18n.t('views.select-template.error.create-timeout.description')
                )
              )
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
              pollDesktops(context)
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
          const viewers = {}
          if (data.template) {
            viewers[data.template] = data.viewer
          } else {
            viewers[data.desktopId] = data.viewer
          }
          context.commit('updateViewers', viewers)
          apiAxios.get(`/desktop/${data.desktopId}/viewer/${data.viewer}`).then(response => {
            const el = document.createElement('a')
            if (response.data.kind === 'file') {
              el.setAttribute(
                'href',
                  `data:${response.data.mime};charset=utf-8,${encodeURIComponent(response.data.content)}`
              )
              el.setAttribute('download', `${response.data.name}.${response.data.ext}`)
            } else if (response.data.kind === 'url') {
              cookies.setCookie('browser_viewer', response.data.cookie)
              el.setAttribute('href', response.data.viewer[0])
              el.setAttribute('target', '_blank')
            }
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
    },
    setViewType (context, viewType) {
      context.commit('setViewType', viewType)
    },
    toggleShowStarted (context) {
      context.commit('toggleShowStarted')
    }
  }
}
