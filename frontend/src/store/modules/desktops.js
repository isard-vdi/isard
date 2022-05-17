import * as cookies from 'tiny-cookie'
import axios from 'axios'
import i18n from '@/i18n'
import router from '@/router'
import { apiV3Segment } from '../../shared/constants'
import { DesktopUtils } from '../../utils/desktopsUtils'
import { ErrorUtils } from '../../utils/errorUtils'
import { get, orderBy } from 'lodash'
import { ImageUtils } from '../../utils/imageUtils'

export default {
  state: {
    viewers: localStorage.viewers ? JSON.parse(localStorage.viewers) : {},
    desktops: [],
    currentTab: 'desktops',
    images: [],
    imagesListItemId: '',
    directViewer: {
      name: '',
      description: '',
      viewers: [],
      state: ''
    },
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
    },
    getDirectViewer: state => {
      return state.directViewer
    },
    getImages: state => {
      return state.images
    },
    getImagesListItemId: state => {
      return state.imagesListItemId
    },
    getCurrentTab: state => {
      return state.currentTab
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
    },
    saveDirectViewer: (state, payload) => {
      state.directViewer.name = payload.name
      state.directViewer.description = payload.description
      state.directViewer.viewers = payload.viewers
      state.directViewer.state = payload.state
      state.directViewer.jwt = payload.jwt
      state.directViewer.desktopId = payload.desktopId
    },
    update_direct_viewer: (state, desktop) => {
      const item = state.desktops.find(d => d.id === desktop.id)
      Object.assign(item, desktop)
    },
    setDirectViewerErrorState: (state) => {
      state.directViewer.state = 'error'
    },
    setImages: (state, images) => {
      state.images = images
    },
    setImagesListItemId: (state, payload) => {
      state.imagesListItemId = payload.itemId
      state.imagesListReturnPage = payload.returnPage
    },
    setCurrentTab: (state, currentTab) => {
      state.currentTab = currentTab
    }
  },
  actions: {
    socket_directviewerUpdate (context, data) {
      data = JSON.parse(data)
      const name = data.vmName
      const description = data.vmDescription
      const state = data.vmState
      const viewers = data.viewers

      context.commit('saveDirectViewer', { name, description, viewers, state })
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
    },
    getDirectViewers (context, payload) {
      return axios.get(`/api/v3/direct/${payload.token}`).then(response => {
        const name = get(response, 'data.vmName')
        const description = get(response, 'data.vmDescription')
        const state = get(response, 'data.vmState')
        const jwt = get(response, 'data.jwt')
        const desktopId = get(response, 'data.desktopId')
        const viewers = get(response, 'data.viewers')

        context.commit('saveDirectViewer', { name, description, viewers, state, jwt, desktopId })
      }).catch(e => {
        context.commit('setDirectViewerErrorState')
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
        cookies.setCookie('browser_viewer', payload.cookie)
        el.setAttribute('href', payload.viewer)
        el.setAttribute('target', '_blank')
      }

      el.style.display = 'none'
      document.body.appendChild(el)
      el.click()
      document.body.removeChild(el)
    },
    fetchDesktopImages (context) {
      const itemId = context.getters.getImagesListItemId
      const data = { params: { desktop_id: itemId } }
      axios.get(`${apiV3Segment}/images/desktops`, data).then(response => {
        context.commit('setImages', ImageUtils.parseImages(orderBy(orderBy(response.data, ['id'], ['desc']), ['type'], ['desc'])))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    goToImagesList (context, payload) {
      context.commit('setImagesListItemId', payload)
      context.dispatch('navigate', 'images')
    },
    async changeImage (context, payload) {
      const itemId = context.getters.getImagesListItemId
      const data = { image: { type: payload.type, id: payload.id } }
      axios.put(`${apiV3Segment}/desktop/${itemId}`, data).then(response => {
        context.dispatch('navigate', 'desktops')
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    async uploadImageFile (context, payload) {
      const itemId = context.getters.getImagesListItemId

      const reader = new FileReader()
      reader.onloadend = () => {
        const base64String = reader.result
          .replace('data:', '')
          .replace(/^.+,/, '')

        const data = `{"image": {"type": "user","file": {"data": "${decodeURIComponent(base64String)}", "filename": "${payload.filename}"}}}`

        axios.put(`${apiV3Segment}/desktop/${itemId}`, JSON.stringify(JSON.parse(data)), { headers: { 'Content-Type': 'application/json' } }).then(response => {
          context.dispatch('navigate', 'desktops')
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
      }

      await reader.readAsDataURL(payload.file)
    },
    updateCurrentTab (context, currentTab) {
      context.commit('setCurrentTab', currentTab)
    }
  }
}
