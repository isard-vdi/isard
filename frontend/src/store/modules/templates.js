import i18n from '@/i18n'
import router from '@/router'
import { DesktopUtils } from '@/utils/desktopsUtils'
import axios from 'axios'
import { orderBy } from 'lodash'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    templates: [],
    templates_loaded: false,
    templateNewItemId: ''
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
    },
    getTemplateNewItemId: state => {
      return state.templateNewItemId
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
    setTemplateNewItemId: (state, desktopId) => {
      state.templateNewItemId = desktopId
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
    goToNewTemplate (context, desktopId) {
      context.commit('setTemplateNewItemId', desktopId)
      context.dispatch('navigate', 'templatenew')
    },
    createNewTemplate (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-template'), '', true, 1000)

      axios.post(`${apiV3Segment}/template`, payload).then(response => {
        router.push({ name: 'desktops' })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
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
