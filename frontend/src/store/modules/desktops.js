import * as cookies from 'tiny-cookie'
import axios from 'axios'
import i18n from '@/i18n'
import router from '@/router'
import { toast } from '@/store/index.js'
import { apiV3Segment } from '../../shared/constants'
import { DesktopUtils } from '../../utils/desktopsUtils'
import { ErrorUtils } from '../../utils/errorUtils'
import { get } from 'lodash'

export default {
  state: {
    viewers: localStorage.viewers ? JSON.parse(localStorage.viewers) : {},
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
      localStorage.viewers = JSON.stringify(state.viewers)
    },
    setViewType: (state, type) => {
      state.viewType = type
    },
    toggleShowStarted: (state, type) => {
      state.showStarted = !state.showStarted
    },
    add_desktop: (state, desktop) => {
      state.desktops = [...state.desktops, desktop]
    },
    update_desktop: (state, desktop) => {
      const item = state.desktops.find(d => d.id === desktop.id)
      Object.assign(item, desktop)
    },
    remove_desktop: (state, desktop) => {
      const desktopIndex = state.desktops.findIndex(d => d.id === desktop.id)
      if (desktopIndex !== -1) {
        state.desktops.splice(desktopIndex, 1)
      }
    }
  },
  actions: {
    socket_desktopAdd (context, data) {
      const desktop = DesktopUtils.parseDesktop(JSON.parse(data))
      context.commit('add_desktop', desktop)
    },
    socket_desktopUpdate (context, data) {
      const desktop = DesktopUtils.parseDesktop(JSON.parse(data))
      context.commit('update_desktop', desktop)
    },
    socket_desktopDelete (context, data) {
      const desktop = JSON.parse(data)
      context.commit('remove_desktop', desktop)
    },
    loadViewers (context, viewers) {
      context.commit('updateViewers', viewers)
    },
    fetchDesktops (context) {
      return new Promise((resolve, reject) => {
        axios.get(`${apiV3Segment}/user/desktops`).then(response => {
          context.commit('setDesktops', DesktopUtils.parseDesktops(response.data))
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
          axios.post(`${apiV3Segment}/desktop`, data, { timeout: 25000 }).then(response => {
            this._vm.$snotify.clear()
            resolve()
          }).catch(e => {
            if (e.response.status === 503) {
              reject(e)
              router.push({ name: 'Maintenance' })
            } else if (e.response.status === 408) {
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
          axios.get(`${apiV3Segment}/desktop/${data.action}/${data.desktopId}`).then(response => {
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
          const viewers = {}
          if (data.template) {
            viewers[data.template] = data.viewer
          } else {
            viewers[data.desktopId] = data.viewer
          }
          context.commit('updateViewers', viewers)
          axios.get(`${apiV3Segment}/desktop/${data.desktopId}/viewer/${data.viewer}`).then(response => {
            const el = document.createElement('a')
            if (response.data.kind === 'file') {
              el.setAttribute(
                'href',
                  `data:${response.data.mime};charset=utf-8,${encodeURIComponent(response.data.content)}`
              )
              el.setAttribute('download', `${response.data.name}.${response.data.ext}`)
            } else if (response.data.kind === 'browser') {
              cookies.setCookie('browser_viewer', response.data.cookie)
              el.setAttribute('href', response.data.viewer)
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
    createNewDesktop (context, payload) {
      const formData = new FormData()
      formData.append('desktop_name', payload.name)
      formData.append('desktop_description', payload.description)
      formData.append('template_id', payload.id)

      axios.post(`${apiV3Segment}/persistent_desktop`, formData).then(response => {
        router.push({ name: 'desktops' })
      }).catch(e => {
        const errorMessageCode = ErrorUtils.errorMessageDefinition[get(e, 'response.status')] ? ErrorUtils.errorMessageDefinition[get(e, 'response.status')][get(e, 'response.data.code')] : undefined

        this._vm.$snotify.error(ErrorUtils.getErrorMessageText(errorMessageCode), {
          timeout: 2000,
          showProgressBar: false,
          closeOnClick: true,
          pauseOnHover: true,
          position: 'centerTop'
        })
      })
    },
    deleteDesktop (context, desktopId) {
      return this._vm.$snotify.async(
        i18n.t('views.select-template.notification.loading.description'),
        i18n.t('views.select-template.notification.loading.title'),
        () => new Promise((resolve, reject) => {
          axios.delete(`${apiV3Segment}/desktop/${desktopId}`).then(response => {
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
    },
    navigate (context, path) {
      router.push({ name: path })
    }
  }
}
