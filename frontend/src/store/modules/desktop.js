import axios from 'axios'
import { orderBy } from 'lodash'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'
import { ImageUtils } from '../../utils/imageUtils'

const getDefaultState = () => {
  return {
    images: [],
    imagesListItemId: ''
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getImages: state => {
      return state.images
    },
    getImagesListItemId: state => {
      return state.imagesListItemId
    }
  },
  mutations: {
    resetDesktopState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setImages: (state, images) => {
      state.images = images
    },
    setImagesListItemId: (state, payload) => {
      state.imagesListItemId = payload.itemId
      state.imagesListReturnPage = payload.returnPage
    }
  },
  actions: {
    resetDesktopState (context) {
      context.commit('resetDesktopState')
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
    }
  }
}
