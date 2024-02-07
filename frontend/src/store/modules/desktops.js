import i18n from '@/i18n'
import router from '@/router'
import axios from 'axios'
import * as cookies from 'tiny-cookie'
import { apiV3Segment } from '../../shared/constants'
import { DesktopUtils } from '../../utils/desktopsUtils'
import { DirectViewerUtils } from '../../utils/directViewerUtils'
import { ErrorUtils } from '../../utils/errorUtils'
import { DateUtils } from '../../utils/dateUtils'
import { jwtDecode } from 'jwt-decode'

const getDefaultState = () => {
  return {
    viewers: localStorage.viewers ? JSON.parse(localStorage.viewers) : {},
    desktops: [],
    currentTab: 'desktops',
    directViewer: {
      name: '',
      description: '',
      viewers: [],
      state: '',
      shutdown: ''
    },
    desktops_loaded: false,
    viewType: 'grid',
    showStarted: false,
    filters: {
      desktops: ''
    },
    directLink: {
      modalShow: false,
      link: '',
      domainId: '',
      enabled: null
    },
    resetModal: {
      show: false,
      item: {
        id: '',
        action: ''
      }
    },
    desktopModal: {
      show: false,
      type: '',
      item: {
        id: ''
      }
    }
  }
}

const state = getDefaultState()

export default {
  state,
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
    },
    getDirectViewer: state => {
      return state.directViewer
    },
    getCurrentTab: state => {
      return state.currentTab
    },
    getDirectLinkModalShow: state => {
      return state.directLink.modalShow
    },
    getDirectLink: state => {
      return state.directLink.link
    },
    getDirectLinkDomainId: state => {
      return state.directLink.domainId
    },
    getDirectLinkEnabled: state => {
      return state.directLink.enabled
    },
    getResetModal: state => {
      return state.resetModal
    },
    getDesktopModal: state => {
      return state.desktopModal
    }
  },
  mutations: {
    resetDesktopsState: (state) => {
      Object.assign(state, getDefaultState())
    },
    resetDirectLinkState: (state) => {
      state.directLink.modalShow = false
      state.directLink.link = ''
      state.directLink.domainId = false
      state.directLink.enabled = null
    },
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
      if (item) {
        Object.assign(item, desktop)
      }
    },
    remove_desktop: (state, desktop) => {
      const desktopIndex = state.desktops.findIndex(d => d.id === desktop.id)
      if (desktopIndex !== -1) {
        state.desktops.splice(desktopIndex, 1)
      }
    },
    saveDesktopFilter: (state, payload) => {
      state.filters.desktops = payload.filter
    },
    saveDirectViewer: (state, payload) => {
      state.directViewer.name = payload.name
      state.directViewer.description = payload.description
      state.directViewer.viewers = Object.keys(payload.viewers).map((viewer) => {
        return payload.viewers[viewer]
      })
      state.directViewer.state = payload.state
      state.directViewer.jwt = payload.jwt
      state.directViewer.desktopId = payload.desktopId
      state.directViewer.shutdown = payload.shutdown
    },
    setDirectViewerErrorState: (state) => {
      state.directViewer.state = 'error'
    },
    setCurrentTab: (state, currentTab) => {
      state.currentTab = currentTab
    },
    setDirectLinkModalShow: (state, directLinkModalShow) => {
      state.directLink.modalShow = directLinkModalShow
    },
    setDirectLink: (state, directLink) => {
      state.directLink.link = directLink
    },
    setDirectLinkDomainId: (state, domainId) => {
      state.directLink.domainId = domainId
    },
    setDirectLinkEnabled: (state, enabled) => {
      state.directLink.enabled = enabled
    },
    setResetModal: (state, resetModal) => {
      state.resetModal = resetModal
    },
    setDesktopModal: (state, desktopModal) => {
      state.desktopModal = desktopModal
    }
  },
  actions: {
    resetDesktopsState (context) {
      context.commit('resetDesktopsState')
    },
    resetDirectLinkState (context) {
      context.commit('resetDirectLinkState')
    },
    socket_directviewerUpdate (context, data) {
      context.commit('saveDirectViewer', DirectViewerUtils.parseDirectViewer(JSON.parse(data)))
    },
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

      axios.post(`${apiV3Segment}/nonpersistent`, data, { timeout: 25000 }).then(response => {
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
    resetDesktop (_, data) {
      axios.put(`${apiV3Segment}/direct/${data.token}/${data.action}`).then(response => {
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
          if (response.data.protocol === 'rdp') {
            localStorage.viewerToken = localStorage.token
          }
          cookies.setCookie('browser_viewer', response.data.cookie)
          cookies.setCookie('token', localStorage.token)
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
    createNewDesktop (_, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-desktop'), '', true, 1000)

      axios.post(`${apiV3Segment}/persistent_desktop`, data).then(response => {
        router.push({ name: 'desktops' })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    createNewDesktopFromMedia (_, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-desktop'), '', true, 1000)

      axios.post(`${apiV3Segment}/desktop/from/media`, data).then(response => {
        router.push({ name: 'desktops' })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    deleteDesktop (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-desktop'))
      const url = data.permanent
        ? `${apiV3Segment}/desktop/${data.id}/permanent`
        : `${apiV3Segment}/desktop/${data.id}`

      axios.delete(url).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    deleteNonpersistentDesktop (_, desktopId) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-desktop'))

      axios.delete(`${apiV3Segment}/nonpersistent/${desktopId}`).then(response => {
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
    },
    getDirectViewers (context, payload) {
      return axios.get(`/api/v3/direct/${payload.token}`).then(response => {
        context.commit('saveDirectViewer', DirectViewerUtils.parseDirectViewer(response.data))
      }).catch(e => {
        context.commit('setDirectViewerErrorState')
        // If the error is that the desktop needs booking format he given time to the users local
        if (e.response.data.description_code === 'desktop_not_booked_until') {
          e.response.data.params.start = DateUtils.utcToLocalTime(e.response.data.params.start)
        }
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    openDirectViewerDesktop (_, payload) {
      const el = document.createElement('a')

      if (payload.kind === 'file') {
        el.setAttribute(
          'href',
            `data:${payload.mime};charset=utf-8,${encodeURIComponent(payload.content)}`
        )
        el.setAttribute('download', `${payload.name}.${payload.ext}`)
      } else if (payload.kind === 'browser') {
        const exp = payload.protocol === 'rdp' ? jwtDecode(payload.cookie).web_viewer.exp * 1000 : JSON.parse(atob(decodeURIComponent(payload.cookie))).web_viewer.exp * 1000
        cookies.setCookie('token', localStorage.viewerToken)
        cookies.setCookie('browser_viewer', payload.cookie, { expires: exp })

        const url = new URL(payload.viewer)
        url.searchParams.append('direct', '1')

        el.setAttribute('href', url.toString())
      }

      el.style.display = 'none'
      document.body.appendChild(el)
      el.click()
      document.body.removeChild(el)
    },
    updateCurrentTab (context, currentTab) {
      context.commit('setCurrentTab', currentTab)
    },
    fetchDirectLink (context, domainId) {
      axios.get(`${apiV3Segment}/desktop/jumperurl/${domainId}`).then(response => {
        context.commit('setDirectLinkDomainId', domainId)
        context.commit('setDirectLinkEnabled', !!response.data.jumperurl)
        context.commit('setDirectLink', response.data.jumperurl ? `${location.protocol}//${location.host}/vw/${response.data.jumperurl}` : '')
        context.dispatch('directLinkModalShow', true)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    directLinkModalShow (context, show) {
      context.commit('setDirectLinkModalShow', show)
    },
    toggleDirectLink (context, data) {
      axios.put(`${apiV3Segment}/desktop/jumperurl_reset/${data.domainId}`, { disabled: data.disabled }).then(response => {
        context.commit('setDirectLink', response.data ? `${location.protocol}//${location.host}/vw/${response.data}` : '')
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    editDesktopReservables (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.editing'))
      return axios.put(`${apiV3Segment}/domain/reservables/${data.id}`, data).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    updateResetModal (context, data) {
      context.commit('setResetModal', data)
    },
    resetResetModal (context) {
      context.commit('setResetModal', {
        show: false,
        item: {
          id: '',
          action: ''
        }
      })
    },
    updateDesktopModal (context, data) {
      context.commit('setDesktopModal', data)
    },
    resetDesktopModal (context) {
      context.commit('setDesktopModal', {
        show: false,
        type: '',
        item: {
          id: ''
        }
      })
    }
  }
}
