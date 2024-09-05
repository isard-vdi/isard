import { ErrorUtils } from '../../utils/errorUtils'

export default {
  state: {},
  getters: {},
  mutations: {},
  actions: {
    showNotification (_, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, data.message)
    }
  }
}
