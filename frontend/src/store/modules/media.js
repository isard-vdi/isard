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
    sharedMedia_loaded: false
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
    }
  }
}
