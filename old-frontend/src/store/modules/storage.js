
import axios from 'axios'
import i18n from '@/i18n'
import { apiV3Segment } from '../../shared/constants'
import { StorageUtils } from '../../utils/storageUtils'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    storage: [],
    storage_loaded: false,
    increaseModalShow: false,
    increaseItem: {}
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getStorage: state => {
      return state.storage
    },
    getStorageLoaded: state => {
      return state.storage_loaded
    },
    getShowIncreaseModal: state => {
      return state.increaseModalShow
    },
    getIncreaseItem: state => {
      return state.increaseItem
    }
  },
  mutations: {
    resetStorageState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setStorage: (state, storage) => {
      state.storage = storage
      state.storage_loaded = true
    },
    setShowIncreaseModal: (state, show) => {
      state.increaseModalShow = show
    },
    setIncreaseItem: (state, item) => {
      state.increaseItem = item
    },
    updateStorage: (state, storage) => {
      const item = state.storage.find(stg => stg.id === storage.id)
      if (item) {
        item.virtualSize = storage.size
        delete item.size
        Object.assign(item, storage)
      }
    }
  },
  actions: {
    fetchStorage (context) {
      axios.get(`${apiV3Segment}/items/storage/ready`).then(response => {
        context.commit('setStorage', StorageUtils.parseStorageList(response.data))
      })
    },
    showIncreaseModal (context, data) {
      context.commit('setIncreaseItem', data.item)
      context.commit('setShowIncreaseModal', data.show)
    },
    updateIncrease (context, data) {
      return axios.put(`${apiV3Segment}/item/storage/${data.id}/priority/${data.priority}/increase/${data.increment}`).then(() => {
        ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.increasing-storage'))
      }).catch(e => {
        if (e.response && e.response.data && e.response.data.description_code) {
          ErrorUtils.showErrorMessage(this._vm.$snotify, e, i18n.t(`errors.increase_${e.response.data.description_code}`))
        } else {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        }
      })
    },
    socket_updateStorage (context, data) {
      context.commit('updateStorage', data)
    }
  }
}
