
import axios from 'axios'
import i18n from '@/i18n'
import { apiV3Segment } from '../../shared/constants'
import { StorageUtils } from '../../utils/storageUtils'
import { ProfileUtils } from '../../utils/profileUtils'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    storage: [],
    storage_loaded: false,
    quota: {},
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
    getQuota: state => {
      return state.quota
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
    setQuota: (state, quota) => {
      state.quota = quota
    },
    setShowIncreaseModal: (state, show) => {
      state.increaseModalShow = show
    },
    setIncreaseItem: (state, item) => {
      state.increaseItem = item
    }
  },
  actions: {
    fetchStorage (context) {
      axios.get(`${apiV3Segment}/storage/ready`).then(response => {
        context.commit('setStorage', StorageUtils.parseStorageList(response.data))
      })
    },
    fetchAppliedQuota (context) {
      axios.get(`${apiV3Segment}/user/appliedquota`).then(response => {
        context.commit('setQuota', ProfileUtils.parseQuota(response.data.quota))
      })
    },
    showIncreaseModal (context, data) {
      context.commit('setIncreaseItem', data.item)
      context.commit('setShowIncreaseModal', data.show)
    },
    updateIncrease (context, data) {
      return axios.put(`${apiV3Segment}/storage/${data.id}/priority/${data.priority}/increase/${data.increment}`).catch(e => {
        if (e.response.data.description_code) {
          ErrorUtils.showErrorMessage(this._vm.$snotify, e, i18n.t(`errors.increase_${e.response.data.description_code}`))
        } else {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        }
      }).then(response => {
        context.dispatch('fetchStorage')
      })
    }
  }
}
