import axios from 'axios'
import i18n from '@/i18n'
import { orderBy } from 'lodash'
import { apiV3Segment, availableViewers } from '../../shared/constants'
import { DomainsUtils } from '../../utils/domainsUtils'
import { ErrorUtils } from '../../utils/errorUtils'
import { ImageUtils } from '../../utils/imageUtils'

const getDefaultState = () => {
  return {
    images: [],
    domainLoaded: false,
    editDomainId: '',
    newFromMedia: {
      id: '',
      kind: ''
    },
    domain: {
      id: '',
      name: '',
      description: '',
      guestProperties: {
        credentials: {
          username: 'isard',
          password: 'pirineus'
        },
        fullscreen: false,
        viewers: [{
          browser_vnc: {
            options: null
          }
        }, {
          file_spice: {
            options: null
          }
        }],
        limits: false
      },
      hardware: {
        bootOrder: ['disk'],
        diskBus: 'default',
        disks: [],
        diskSize: 1,
        floppies: [],
        graphics: ['default'],
        interfaces: ['default'],
        interfacesMac: [],
        isos: [],
        memory: 1,
        vcpus: 1,
        videos: ['default']
      },
      reservables: {
        vgpus: ['None']
      },
      image: {
      },
      OSTemplateId: ''
    },
    hardware: [], // Available hardware
    bookables: [], // Available bookables
    isos: [], // Available isos
    floppies: [], // Available floppires
    mediaInstalls: [],
    mediaInstallsLoaded: false
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getImages: state => {
      return state.images
    },
    getEditDomainId: state => {
      return state.editDomainId
    },
    getNewFromMedia: state => {
      return state.newFromMedia
    },
    getDomain: state => {
      return state.domain
    },
    getHardware: state => {
      return state.hardware
    },
    getBookables: state => {
      return state.bookables
    },
    getIsos: state => {
      return state.isos
    },
    getFloppies: state => {
      return state.floppies
    },
    getSelectedOSTemplateId: state => {
      return state.domain.OSTemplateId
    },
    getMediaInstalls: state => {
      return state.mediaInstalls
    },
    getMediaInstallsLoaded: state => {
      return state.mediaInstalls
    }
  },
  mutations: {
    resetDomainState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setImages: (state, images) => {
      state.images = images
    },
    setEditDomainId: (state, domainId) => {
      state.editDomainId = domainId
    },
    setNewFromMedia: (state, newFromMedia) => {
      state.newFromMedia.id = newFromMedia.id
      state.newFromMedia.kind = newFromMedia.kind
    },
    setSelectedIsos: (state, selectedIsos) => {
      state.domain.hardware.isos = selectedIsos
    },
    setSelectedFloppies: (state, selectedFloppies) => {
      state.domain.hardware.floppies = selectedFloppies
    },
    setDomain: (state, domain) => {
      state.domain = domain
      state.domainLoaded = true
    },
    setHardware: (state, hardware) => {
      state.hardware = hardware
    },
    setBookables: (state, bookables) => {
      state.bookables = bookables
    },
    setIsos: (state, isos) => {
      state.isos = isos
    },
    setFloppies: (state, floppies) => {
      state.floppies = floppies
    },
    removeWireguardViewers: (state) => {
      // Get viewers that require the wireguard network
      const wireguardViewers = availableViewers.filter(viewer => viewer.needsWireguard)
      for (const value of wireguardViewers) {
        // Remove each one of them from the domain selected viewers
        const viewerIndex = state.domain.guestProperties.viewers.findIndex(v => Object.keys(v)[0] === value.key)
        if (viewerIndex !== -1) {
          state.domain.guestProperties.viewers.splice(viewerIndex, 1)
        }
      }
    },
    removeGuestProperties: (state) => {
      state.domain.guestProperties.credentials.username = 'isard'
      state.domain.guestProperties.credentials.password = 'pirineus'
    },
    setSelectedOSTemplateId: (state, selectedOSTemplateId) => {
      state.domain.OSTemplateId = selectedOSTemplateId
    },
    setMediaInstalls: (state, installs) => {
      state.mediaInstalls = installs
      state.mediaInstallsLoaded = true
    }
  },
  actions: {
    resetDomainState (context) {
      context.commit('resetDomainState')
    },
    fetchDesktopImages (context) {
      const itemId = context.getters.getEditDomainId
      const data = { params: { desktop_id: itemId } }
      axios.get(`${apiV3Segment}/images/desktops`, data).then(response => {
        context.commit('setImages', ImageUtils.parseImages(orderBy(orderBy(response.data, ['id'], ['desc']), ['type'], ['desc'])))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    changeImage (context, imageData) {
      const domain = context.getters.getDomain
      domain.image = imageData
      context.commit('setDomain', domain)
    },
    async uploadImageFile (context, payload) {
      const itemId = context.getters.getEditDomainId

      const reader = new FileReader()
      reader.onloadend = () => {
        const base64String = reader.result
          .replace('data:', '')
          .replace(/^.+,/, '')

        const data = `{"image": {"type": "user","file": {"data": "${decodeURIComponent(base64String)}", "filename": "${payload.filename}"}}}`

        axios.put(`${apiV3Segment}/domain/${itemId}`, JSON.stringify(JSON.parse(data)), { headers: { 'Content-Type': 'application/json' } }).then(response => {
          ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.image-uploaded'), '', true, 1000)
          context.dispatch('fetchDesktopImages')
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
      }

      await reader.readAsDataURL(payload.file)
    },
    goToEditDomain (context, domainId) {
      context.commit('setEditDomainId', domainId)
      context.dispatch('navigate', 'domainedit')
    },
    goToNewFromMedia (context, media) {
      context.commit('setNewFromMedia', media)
      context.dispatch('navigate', 'newfrommedia')
    },
    fetchDomain (context, domainId) {
      axios.get(`${apiV3Segment}/domain/info/${domainId}`).then(response => {
        if (!context.getters.getEditDomainId) { // Only keep the domain name when editing
          response.data.name = context.getters.getDomain.name
        }
        context.commit('setDomain', DomainsUtils.parseDomain(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchHardware (context) {
      axios.get(`${apiV3Segment}/user/hardware/allowed`).then(response => {
        context.commit('setHardware', DomainsUtils.parseAvailableHardware(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchBookables (context) {
      axios.get(`${apiV3Segment}/domains/allowed/reservables`).then(response => {
        context.commit('setBookables', response.data)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    editDomain (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.editing'))
      return axios.put(`${apiV3Segment}/domain/${data.id}`, data).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    removeWireguardViewers (context, wireguard) {
      context.commit('removeWireguardViewers')
      context.commit('removeGuestProperties')
    },
    fetchMediaInstalls ({ commit }) {
      axios.get(`${apiV3Segment}/media/installs`).then(response => {
        commit(
          'setMediaInstalls', response.data, ['desc']
        )
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    setSelectedOSTemplateId (context, selectedOSTemplateId) {
      context.commit('setSelectedOSTemplateId', selectedOSTemplateId)
    }
  }
}
