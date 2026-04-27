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
    templateDerivatives: {
      domains: [],
      deployments: [],
      pending: false,
      cross_category: false,
      is_duplicated: false
    },
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
    add_template: (state, template) => {
      // Insert the new template at the front of the list so the user
      // sees it immediately while the apiv4 task chain creates it.
      // ``setTemplates`` re-fetches will canonicalise the order on the
      // next page load.
      const exists = state.templates.some(t => t.id === template.id)
      if (!exists) {
        state.templates = [template, ...state.templates]
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
      axios.get(`${apiV3Segment}/items/templates`).then(response => {
        commit('setTemplates', DesktopUtils.parseTemplates(orderBy(response.data.templates, ['editable'], ['desc'])))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchAllowedTemplates ({ commit }, kind) {
      axios.get(`${apiV3Segment}/items/templates/allowed/${kind}`).then(response => {
        const mutation = kind === 'all' ? 'setTemplates' : 'setSharedTemplates'
        commit(mutation, DesktopUtils.parseTemplates(orderBy(response.data, ['editable'], ['desc'])))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    toggleEnabled (context, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t(payload.enabled ? 'messages.info.disable-template' : 'messages.info.enable-template'), '', true, 1000)
      axios.put(`${apiV3Segment}/item/template/${payload.id}/set-enabled`, { enabled: payload.enabled }).then(response => {
        this._vm.$snotify.clear()
        context.commit('update_templates', DesktopUtils.parseTemplate({ ...payload }))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    setTemplatesLoaded (context, templatesLoaded) {
      context.commit('setTemplatesLoaded', templatesLoaded)
    },
    deleteTemplate (_, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.deleting-template'))
      axios.delete(`${apiV3Segment}/item/template/${state.templateId}`).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    fetchTemplateDerivatives (context, data) {
      axios.get(`${apiV3Segment}/item/template/${data.id}/get-tree`).then(response => {
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
    socket_templateAdd (context, data) {
      // change-handler emits ``template_add`` (full row payload) when
      // apiv4 inserts a new template row. Without this handler the
      // user would only see the template after a manual refresh.
      const template = DesktopUtils.parseTemplate(JSON.parse(data))
      context.commit('add_template', template)
    },
    socket_templateUpdate (context, data) {
      // change-handler emits ``template_update`` on every row change,
      // including the periodic ``progress`` writes the move() task
      // makes during the rsync branch of the template-creation chain.
      // Forwarding the payload keeps the progress bar live.
      const template = DesktopUtils.parseTemplate(JSON.parse(data))
      context.commit('update_templates', template)
    },
    fetchConvertToDesktop (context, data) {
      axios.get(`${apiV3Segment}/item/template/${data.template.id}/get-tree`).then(response => {
        context.commit('setTemplateDerivatives', response.data)
        context.commit('setTemplateId', data.template.id)
        context.commit('setTemplateName', data.template.name)
        context.commit('setShowConvertToDesktopModal', true)
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
        throw e
      })
    },
    convertToDesktop (context, data) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.converting-template'))
      axios.post(`${apiV3Segment}/item/template/${data.templateId}/convert-to-desktop`, { name: data.name }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      }).then(() => {
        context.dispatch('fetchTemplates')
      })
    }
  }
}
