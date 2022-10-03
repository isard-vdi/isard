import i18n from '@/i18n'
import router from '@/router'
import { MediaUtils } from '@/utils/mediaUtils'
import axios from 'axios'
import { orderBy } from 'lodash'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    media: [],
    media_loaded: false,
    sharedMedia: [],
    sharedMedia_loaded: false,
    modalDesktopsShow: false,
    mediaId: '',
    mediaDesktops: []
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getMedia: state => {
      return state.media
    },
    getSharedMedia: state => {
      return state.sharedMedia
    },
    getMediaLoaded: state => {
      return state.media_loaded
    },
    getSharedMediaLoaded: state => {
      return state.sharedMedia_loaded
    },
    getShowDeleteMediaModal: state => {
      return state.modalDesktopsShow
    },
    getMediaId: state => {
      return state.mediaId
    },
    getMediaDesktops: state => {
      return state.mediaDesktops
    }
  },
  mutations: {
    resetMediaState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setMedia: (state, media) => {
      state.media = media
      state.media_loaded = true
    },
    setSharedMedia: (state, media) => {
      state.sharedMedia = media
      state.sharedMedia_loaded = true
    },
    add_media: (state, media) => {
      state.media = [...state.media, media]
    },
    update_media: (state, media) => {
      const item = state.media.find(d => d.id === media.id)
      if (item) {
        Object.assign(item, media)
      }
    },
    remove_media: (state, media) => {
      const mediaIndex = state.media.findIndex(d => d.id === media.id)
      if (mediaIndex !== -1) {
        state.media.splice(mediaIndex, 1)
      }
    },
    setShowDeleteMediaModal: (state, modalShow) => {
      state.modalDesktopsShow = modalShow
    },
    setMediaId: (state, mediaId) => {
      state.mediaId = mediaId
    },
    setMediaDesktops: (state, desktops) => {
      state.mediaDesktops = desktops
    }
  },
  actions: {
    socket_mediaAdd (context, data) {
      const media = MediaUtils.parseMedia(JSON.parse(data))
      context.commit('add_media', media)
    },
    socket_mediaUpdate (context, data) {
      const media = MediaUtils.parseMedia(JSON.parse(data))
      context.commit('update_media', media)
    },
    socket_mediaDelete (context, data) {
      const media = JSON.parse(data)
      context.commit('remove_media', media)
    },
    resetMediaState (context) {
      context.commit('resetMediaState')
    },
    fetchMedia ({ commit }) {
      axios.get(`${apiV3Segment}/media`).then(response => {
        commit(
          'setMedia',
          MediaUtils.parseMediaList(orderBy(response.data, ['desc']))
        )
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchSharedMedia ({ commit }) {
      axios.get(`${apiV3Segment}/media_allowed`).then(response => {
        commit(
          'setSharedMedia',
          MediaUtils.parseMediaList(orderBy(response.data, ['desc']))
        )
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    createNewMedia (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-media'), '', true, 1000)

      axios.post(`${apiV3Segment}/media`, payload).then(response => {
        router.push({ name: 'media' })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchMediaDesktops (context, data) {
      axios.get(`${apiV3Segment}/media/desktops/${data.mediaId}`).then(response => {
        if (response.data.length > 0) {
          context.commit('setMediaDesktops', MediaUtils.parseMediaDesktops(response.data))
          context.commit('setMediaId', data.mediaId)
          context.dispatch('showDeleteMediaModal', true)
        } else {
          const yesAction = () => {
            context.dispatch('deleteMedia', data.mediaId)
            this._vm.$snotify.clear()
          }

          const noAction = (toast) => {
            this._vm.$snotify.clear()
          }

          this._vm.$snotify.prompt(`${i18n.t('messages.confirmation.delete-media', { name: data.name })}`, {
            position: 'centerTop',
            buttons: [
              { text: `${i18n.t('messages.yes')}`, action: yesAction, bold: true },
              { text: `${i18n.t('messages.no')}`, action: noAction }
            ],
            placeholder: ''
          })
        }
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    showDeleteMediaModal (context, show) {
      context.commit('setShowDeleteMediaModal', show)
    },
    deleteMedia (_, mediaId) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-media'))

      axios.delete(`${apiV3Segment}/media/${mediaId}`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    downloadMedia (_, mediaId) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.downloading-media'))

      axios.post(`${apiV3Segment}/media/download/${mediaId}`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    stopMediaDownload (_, mediaId) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.stopping-download'))

      axios.post(`${apiV3Segment}/media/abort/${mediaId}`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    checkCreateMediaQuota (context, data) {
      const config = context.getters.getConfig
      if (!config.quota) {
        context.dispatch('navigate', 'medianew')
      } else {
        axios.get(`${apiV3Segment}/media/count`).then(response => {
          if (response.data.count < config.quota.isos) {
            context.dispatch('navigate', 'medianew')
          } else {
            ErrorUtils.showErrorNotification(this._vm.$snotify, i18n.t('errors.iso_creation_user_quota_exceeded'))
          }
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
      }
    }
  }
}
