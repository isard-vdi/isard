import i18n from '@/i18n'
import axios from 'axios'
import { apiV3Segment, schedulerSegment } from '../../shared/constants'
import { RecycleBinUtils } from '../../utils/recycleBinUtils'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    recycleBins: [],
    recycleBinsLoaded: false,
    recycleBin: {
      agentId: '',
      desktops: [],
      templates: [],
      deployments: [],
      storages: []
    },
    recycleBinLoaded: false,
    recycleBinModal: {
      show: false,
      type: 'delete',
      item: {
        id: ''
      }
    },
    maxTime: false,
    itemsInRecycleBin: 0
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getRecycleBins: state => {
      return state.recycleBins
    },
    getRecycleBinsLoaded: state => {
      return state.recycleBinsLoaded
    },
    getRecycleBin: state => {
      return state.recycleBin
    },
    getRecycleBinLoaded: state => {
      return state.recycleBinLoaded
    },
    getRecycleBinModal: state => {
      return state.recycleBinModal
    },
    getMaxTime: state => {
      return state.maxTime
    },
    getItemsInRecycleBin: state => {
      return state.itemsInRecycleBin
    }
  },
  mutations: {
    resetRecycleBinState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setRecycleBins: (state, recycleBins) => {
      state.recycleBins = recycleBins
      state.recycleBinsLoaded = true
    },
    setRecycleBin: (state, recycleBin) => {
      state.recycleBin = recycleBin
      state.recycleBinLoaded = true
    },
    setRecycleBinModal: (state, recycleBinModal) => {
      state.recycleBinModal = recycleBinModal
    },
    setMaxTime: (state, maxTime) => {
      state.maxTime = maxTime
    },
    setItemsInRecycleBin: (state, itemsInRecycleBin) => {
      state.itemsInRecycleBin = itemsInRecycleBin
    },
    addRecycleBinsItem: (state, recycleBin) => {
      state.recycleBins = [...state.recycleBins, recycleBin]
      state.itemsInRecycleBin = state.itemsInRecycleBin + 1
    },
    updateRecycleBinsItem: (state, recycleBin) => {
      const item = state.recycleBins.find(d => d.id === recycleBin.id)
      if (item) {
        Object.assign(item, recycleBin)
      }
    },
    removeRecycleBinsItem: (state, recycleBinsListItem) => {
      const recycleBinIndex = state.recycleBins.findIndex(d => d.id === recycleBinsListItem.id)
      if (recycleBinIndex !== -1) {
        state.recycleBins.splice(recycleBinIndex, 1)
        state.itemsInRecycleBin = state.itemsInRecycleBin - 1
      }
    }
  },
  actions: {
    socket_addRecycleBin (context, data) {
      const recycleBinsListItem = RecycleBinUtils.parseRecycleBinListItem(data)
      context.commit('addRecycleBinsItem', recycleBinsListItem)
    },
    socket_updateRecycleBin (context, data) {
      const recycleBinsListItem = RecycleBinUtils.parseRecycleBinListItem(data)
      if (['restored', 'deleting', 'deleted'].includes(data.status)) {
        context.commit('removeRecycleBinsItem', recycleBinsListItem)
      } else {
        context.commit('updateRecycleBinsItem', recycleBinsListItem)
      }
    },
    socket_deleteRecycleBin (context, data) {
      const recycleBinsListItem = RecycleBinUtils.parseRecycleBinListItem(data)
      context.commit('removeRecycleBinsItem', recycleBinsListItem)
    },
    updateRecycleBinModal (context, data) {
      context.commit('setRecycleBinModal', data)
    },
    resetRecycleBinModal (context) {
      context.commit('setRecycleBinModal', {
        show: false,
        type: '',
        item: {
          id: ''
        }
      })
    },
    fetchRecycleBins (context) {
      axios.get(`${apiV3Segment}/recycle_bin/item_count/user`).then(response => {
        context.commit('setRecycleBins', RecycleBinUtils.parseRecycleBinList(response.data))
      })
    },
    fetchRecycleBin (context, data) {
      axios.get(`${apiV3Segment}/recycle_bin/${data.id}`).then(response => {
        context.commit('setRecycleBin', RecycleBinUtils.parseRecycleBin(response.data))
      })
    },
    fetchMaxTime (context, data) {
      axios.get(`${schedulerSegment}/recycle_bin_delete/max_time`).then(response => {
        context.commit('setMaxTime', RecycleBinUtils.parseMaxTime(response.data))
      }).catch(e => {
      })
    },
    fetchItemsInRecycleBin (context) {
      axios.get(`${apiV3Segment}/recycle_bin/count`).then(response => {
        context.commit('setItemsInRecycleBin', response.data)
      })
    },
    restoreRecycleBin (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.restoring-recycle-bin'), '', true, 1000)
      return axios.get(`${apiV3Segment}/recycle_bin/restore/${data.id}`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    deleteRecycleBin (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-recycle-bin'), '', true, 1000)
      return axios.delete(`${apiV3Segment}/recycle_bin/delete/${data.id}`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    emptyRecycleBin (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-recycle-bin'), '', true, 1000)
      return axios.delete(`${apiV3Segment}/recycle_bin/empty`).then(response => {
        this._vm.$snotify.clear()
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    }
  }
}
