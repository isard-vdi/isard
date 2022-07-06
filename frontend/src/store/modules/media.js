import axios from 'axios'
import { MediaUtils } from '@/utils/mediaUtils'
import { orderBy } from 'lodash'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    media: [],
    media_loaded: false
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getMedia: state => {
      return state.media
    },
    getMediaLoaded: state => {
      return state.media_loaded
    }
  },
  mutations: {
    resetMediaState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setMedia: (state, media) => {
      state.media = media
      state.media_loaded = true
    }
  },
  actions: {
    fetchMedia ({ commit }) {
      axios.get(`${apiV3Segment}/media`).then(response => {
        commit(
          'setMedia',
          MediaUtils.parseMediaList(orderBy(response.data, ['desc']))
        )
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    }
  }
}
