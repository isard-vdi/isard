import axios from 'axios'
import { DesktopUtils } from '@/utils/desktopsUtils'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'

export default {
  state: {
    templates: [],
    templates_loaded: false
  },
  getters: {
    getTemplates: state => {
      return state.templates
    },
    getTemplatesLoaded: state => {
      return state.templates_loaded
    }
  },
  mutations: {
    setTemplates: (state, templates) => {
      state.templates = templates
      state.templates_loaded = true
    }
  },
  actions: {
    fetchTemplates ({ commit }) {
      axios.get(`${apiV3Segment}/user/templates`).then(response => {
        commit('setTemplates', DesktopUtils.parseTemplates(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    }
  }
}
