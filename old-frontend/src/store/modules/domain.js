import axios from 'axios'
import router from '@/router'
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
      kind: '',
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
      OSTemplateId: '',
      macs: {}
    },
    hardware: [], // Available hardware
    bookables: [], // Available bookables
    isos: [], // Available isos
    floppies: [], // Available floppires
    mediaInstalls: [],
    mediaInstallsLoaded: false,
    bastion: {
      enabled: false,
      id: '',
      http: {
        enabled: false,
        http_port: 80,
        https_port: 443,
        proxy_protocol: false
      },
      ssh: {
        enabled: false,
        port: 22,
        authorized_keys: []
      }
    }
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
    },
    getBastion: state => {
      return state.bastion
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
    },
    changeVideos: (state, videos) => {
      state.domain.hardware.videos = videos
    },
    setBastion: (state, bastion) => {
      state.bastion = bastion
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
      const itemKind = context.getters.getDomain.kind === 'template' ? 'template' : 'desktop'

      const reader = new FileReader()
      reader.onloadend = () => {
        const base64String = reader.result
          .replace('data:', '')
          .replace(/^.+,/, '')

        // ``id`` is required by the apiv4 ``DomainImage`` schema even on
        // upload — the backend assigns the persistent id server-side.
        // Vue 3's ChangeImageModal sends the same empty-string sentinel.
        const data = `{"image": {"id": "","type": "user","file": {"data": "${decodeURIComponent(base64String)}", "filename": "${payload.filename}"}}}`

        axios.put(`${apiV3Segment}/item/${itemKind}/${itemId}/edit`, JSON.stringify(JSON.parse(data)), { headers: { 'Content-Type': 'application/json' } }).then(response => {
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
      axios.get(`${apiV3Segment}/item/desktop/${domainId}/get-info`).then(response => {
        if (!context.getters.getEditDomainId) { // Only keep the domain name when editing
          response.data.name = context.getters.getDomain.name
        } else if (response.data.kind !== 'template') { // bastion is desktop-only
          context.dispatch('fetchBastion', domainId)
        }
        context.commit('setDomain', DomainsUtils.parseDomain(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchHardware (context) {
      axios.get(`${apiV3Segment}/item/user/get-allowed-hardware`).then(response => {
        context.commit('setHardware', DomainsUtils.parseAvailableHardware(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchBookables (context) {
      axios.get(`${apiV3Segment}/items/domains/get-allowed-reservables`).then(response => {
        context.commit('setBookables', response.data)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    editDomain (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.editing'))

      const kindSegment = data.kind === 'template' ? 'template' : 'desktop'
      const redirectName = data.kind === 'template' ? 'templates' : 'desktops'
      axios.put(`${apiV3Segment}/item/${kindSegment}/${data.id}/edit`, data).then(response => {
        if (data.kind !== 'template') {
          context.dispatch('updateBastion', data.id)
        }
        router.push({ name: redirectName })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    removeWireguardViewers (context, wireguard) {
      context.commit('removeWireguardViewers')
      context.commit('removeGuestProperties')
    },
    fetchMediaInstalls ({ commit }) {
      axios.get(`${apiV3Segment}/items/media/installs`).then(response => {
        commit(
          'setMediaInstalls', response.data, ['desc']
        )
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    setSelectedOSTemplateId (context, selectedOSTemplateId) {
      context.commit('setSelectedOSTemplateId', selectedOSTemplateId)
    },
    changeVideos (context, videos) {
      context.commit('changeVideos', videos)
    },
    fetchBastion (context, domainId) {
      const config = context.getters.getConfig
      if (config.canUseBastion === true) {
        axios.get(`${apiV3Segment}/item/desktop/${domainId}/get-bastion`).then(response => {
          const bastion = response.data
          if (response.data.ssh.enabled || response.data.http.enabled) {
            bastion.enabled = true
          } else {
            bastion.enabled = false
          }
          context.commit('setBastion', bastion)
        }).catch(e => {
          // We can ignore 404, since the first time the bastion
          // won't be created
          if (e.response?.status !== 404) {
            ErrorUtils.handleErrors(e, this._vm.$snotify)
          }
        })
      }
    },
    updateBastion (context, domainId) {
      const config = context.getters.getConfig
      if (config.canUseBastion === true) {
        const bastion = context.getters.getBastion

        bastion.http.http_port = bastion.http.http_port ? parseInt(bastion.http.http_port) : 80
        bastion.http.https_port = bastion.http.https_port ? parseInt(bastion.http.https_port) : 443
        bastion.ssh.port = bastion.ssh.port ? parseInt(bastion.ssh.port) : 22

        axios.put(`${apiV3Segment}/item/desktop/${domainId}/bastion`, bastion).then(response => {
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
      }
    }
  }
}
