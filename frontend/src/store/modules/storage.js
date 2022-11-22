
import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { StorageUtils } from '../../utils/storageUtils'
import { ProfileUtils } from '../../utils/profileUtils'

const getDefaultState = () => {
  return {
    storage: [],
    storage_loaded: false,
    quota: {}
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
    }
  }
}
