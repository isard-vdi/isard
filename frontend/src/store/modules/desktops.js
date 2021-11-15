import * as cookies from 'tiny-cookie'
import axios from 'axios'
import i18n from '@/i18n'
import router from '@/router'
import { apiV3Segment } from '../../shared/constants'
import { DesktopUtils } from '../../utils/desktopsUtils'
import { ErrorUtils } from '../../utils/errorUtils'

export default {
  state: {
    viewers: localStorage.viewers ? JSON.parse(localStorage.viewers) : {},
    desktops: [],
    desktops_loaded: false,
    viewType: 'grid',
    showStarted: false,
    filters: {
      desktops: ''
    }
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
    },
    getDesktopsFilter: state => {
      return state.filters.desktops
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
    },
    saveDesktopFilter: (state, payload) => {
      state.filters.desktops = payload.filter
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
      axios.get(`${apiV3Segment}/user/desktops`).then(response => {
        context.commit('setDesktops', DesktopUtils.parseDesktops(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    createDesktop (_, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-desktop'))

      axios.post(`${apiV3Segment}/desktop`, data, { timeout: 25000 }).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    changeDesktopStatus (_, data) {
      axios.get(`${apiV3Segment}/desktop/${data.action}/${data.desktopId}`).then(response => {
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    openDesktop (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.opening-desktop'))

      // Save last viewer selected
      const viewers = {}
      if (data.template) {
        viewers[data.template] = data.viewer
      } else {
        viewers[data.desktopId] = data.viewer
      }
      context.commit('updateViewers', viewers)

      axios.get(`${apiV3Segment}/desktop/${data.desktopId}/viewer/${data.viewer}`).then(response => {
        this._vm.$snotify.clear()

        const el = document.createElement('a')
        if (response.data.kind === 'file') {
          el.setAttribute(
            'href',
              `data:${response.data.mime};charset=utf-8,${encodeURIComponent(response.data.content)}`
          )
          el.setAttribute('download', `${response.data.name}.${response.data.ext}`)
          ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.file-downloaded'), '', false, 1000)
        } else if (response.data.kind === 'browser') {
          cookies.setCookie('browser_viewer', response.data.cookie)
          el.setAttribute('href', response.data.viewer)
          el.setAttribute('target', '_blank')
        }
        el.style.display = 'none'
        document.body.appendChild(el)
        el.click()
        document.body.removeChild(el)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    createNewDesktop (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-desktop'), '', true, 1000)

      const formData = new FormData()
      formData.append('desktop_name', payload.name)
      formData.append('desktop_description', payload.description)
      formData.append('template_id', payload.id)

      axios.post(`${apiV3Segment}/persistent_desktop`, formData).then(response => {
        // this._vm.$snotify.clear()
        router.push({ name: 'desktops' })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    deleteDesktop (_, desktopId) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-desktop'))

      axios.delete(`${apiV3Segment}/desktop/${desktopId}`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    updateDesktopsFilter (context, payload) {
      context.commit('saveDesktopFilter', payload)
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
