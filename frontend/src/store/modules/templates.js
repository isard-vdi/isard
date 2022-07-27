import i18n from '@/i18n'
import { DesktopUtils } from '@/utils/desktopsUtils'
import axios from 'axios'
import { orderBy } from 'lodash'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    templates: [],
    templates_loaded: false
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getTemplates: state => {
      return state.templates
    },
    getTemplatesLoaded: state => {
      return state.templates_loaded
    }
  },
  mutations: {
    resetTemplatesState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setTemplates: (state, templates) => {
      state.templates = templates
      state.templates_loaded = true
    },
    update_templates: (state, template) => {
      const item = state.templates.find(t => t.id === template.id)
      if (item) {
        Object.assign(item, template)
      }
    },
    setTemplatesLoaded: (state, templatesLoaded) => {
      state.templates_loaded = templatesLoaded
    }
  },
  actions: {
    resetTemplatesState (context) {
      context.commit('resetTemplatesState')
    },
    fetchTemplates ({ commit }) {
      axios.get(`${apiV3Segment}/user/templates`).then(response => {
        commit('setTemplates', DesktopUtils.parseTemplates(orderBy(response.data, ['editable'], ['desc'])))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchAllowedTemplates ({ commit }) {
      axios.get(`${apiV3Segment}/user/templates_allowed`).then(response => {
        commit('setTemplates', DesktopUtils.parseTemplates(orderBy(response.data, ['editable'], ['desc'])))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    toggleEnabled (context, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t(payload.enabled ? 'messages.info.disable-template' : 'messages.info.enable-template'), '', true, 1000)
      axios.put(`${apiV3Segment}/template/update`, payload).then(response => {
        this._vm.$snotify.clear()
        context.commit('update_templates', DesktopUtils.parseTemplate(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    setTemplatesLoaded (context, templatesLoaded) {
      context.commit('setTemplatesLoaded', templatesLoaded)
    }
  }
}
