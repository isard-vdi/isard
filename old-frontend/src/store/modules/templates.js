import i18n from '@/i18n'
import { DesktopUtils } from '@/utils/desktopsUtils'
import axios from 'axios'
import { orderBy } from 'lodash'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    templates: [],
    templates_loaded: false,
    sharedTemplates: [],
    sharedTemplates_loaded: false,
    templateDerivatives: {},
    templateId: '',
    templateName: '',
    modalDerivativesShow: {
      delete: false,
      convert: false
    },
    modalDerivativesView: 'list'
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getTemplates: state => {
      return state.templates
    },
    getSharedTemplates: state => {
      return state.sharedTemplates
    },
    getTemplatesLoaded: state => {
      return state.templates_loaded
    },
    getSharedTemplatesLoaded: state => {
      return state.sharedTemplates_loaded
    },
    getTemplateDerivatives: state => {
      return state.templateDerivatives
    },
    getShowDeleteTemplateModal: state => {
      return state.modalDerivativesShow.delete
    },
    getShowConvertToDesktopModal: state => {
      return state.modalDerivativesShow.convert
    },
    getTemplateId: state => {
      return state.templateId
    },
    getTemplateName: state => {
      return state.templateName
    },
    getDerivativesView: state => {
      return state.modalDerivativesView
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
    setSharedTemplates: (state, templates) => {
      state.sharedTemplates = templates
      state.sharedTemplates_loaded = true
    },
    update_templates: (state, template) => {
      const item = state.templates.find(t => t.id === template.id)
      if (item) {
        Object.assign(item, template)
      }
    },
    setTemplatesLoaded: (state, templatesLoaded) => {
      state.templates_loaded = templatesLoaded
    },
    setTemplateDerivatives: (state, templateDerivatives) => {
      state.templateDerivatives = templateDerivatives
    },
    setShowDeleteTemplateModal: (state, modalShow) => {
      state.modalDerivativesShow.delete = modalShow
    },
    setShowConvertToDesktopModal: (state, modalShow) => {
      state.modalDerivativesShow.convert = modalShow
    },
    setTemplateId: (state, templateId) => {
      state.templateId = templateId
    },
    setTemplateName: (state, templateName) => {
      state.templateName = templateName
    },
    remove_template: (state, template) => {
      const templateIndex = state.templates.findIndex(d => d.id === template.id)
      if (templateIndex !== -1) {
        state.templates.splice(templateIndex, 1)
      }
    },
    setDerivativesView: (state, view) => {
      state.modalDerivativesView = view
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
    fetchAllowedTemplates ({ commit }, kind) {
      axios.get(`${apiV3Segment}/user/templates/allowed/${kind}`).then(response => {
        const mutation = kind === 'all' ? 'setTemplates' : 'setSharedTemplates'
        commit(mutation, DesktopUtils.parseTemplates(orderBy(response.data, ['editable'], ['desc'])))
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
    },
    deleteTemplate (_, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-template'))
      axios.delete(`${apiV3Segment}/template/${state.templateId}`).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchTemplateDerivatives (context, data) {
      axios.get(`${apiV3Segment}/template/tree/${data.id}`).then(response => {
        context.commit('setTemplateDerivatives', response.data)
        context.commit('setTemplateId', data.id)
        context.dispatch('showDeleteTemplateModal', true)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
        throw e
      })
    },
    showDeleteTemplateModal (context, show) {
      context.commit('setShowDeleteTemplateModal', show)
    },
    socket_templateDelete (context, data) {
      const template = JSON.parse(data)
      context.commit('remove_template', template)
    },
    fetchConvertToDesktop (context, data) {
      axios.get(`${apiV3Segment}/template/tree/${data.template.id}`).then(response => {
        context.commit('setTemplateDerivatives', response.data)
        context.commit('setTemplateId', data.template.id)
        context.commit('setTemplateName', data.template.name)
        context.commit('setShowConvertToDesktopModal', true)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
        throw e
      })
    },
    ConvertToDesktop (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.converting-template'))
      axios.post(`${apiV3Segment}/template/to/desktop`, { template_id: data.templateId, name: data.name }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      }).then(() => {
        context.dispatch('fetchTemplates')
      })
    }
  }
}
