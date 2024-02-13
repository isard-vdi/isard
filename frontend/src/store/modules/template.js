import i18n from '@/i18n'
import router from '@/router'
import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    templateNewItemId: '',
    templateNewOrigin: ''
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getTemplateNewItemId: state => {
      return state.templateNewItemId
    },
    getTemplateNewOrigin: state => {
      return state.templateNewOrigin
    }
  },
  mutations: {
    resetTemplateState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setTemplateNewItemId: (state, desktopId) => {
      state.templateNewItemId = desktopId
    },
    setTemplateNewOrigin: (state, kind) => {
      state.templateNewOrigin = kind
    }
  },
  actions: {
    createNewTemplate (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-template'), '', true, 1000)

      axios.post(`${apiV3Segment}/template/`, payload).then(response => {
        router.push({ name: 'desktops' })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    duplicateTemplate (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-template'), '', true, 1000)
      axios.post(`${apiV3Segment}/template/duplicate/${payload.template_id}`, payload).then(response => {
        router.push({ name: 'desktops' })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    resetTemplateState (context) {
      context.commit('resetTemplateState')
    },
    goToNewTemplate (context, desktopId) {
      context.commit('setTemplateNewItemId', desktopId)
      context.commit('setTemplateNewOrigin', 'desktop')
      context.dispatch('checkHyperAvailableAndQuota', { itemType: 'templates', routeName: 'templatenew' })
    },
    goToDuplicate (context, templateId) {
      context.commit('setTemplateNewItemId', templateId)
      context.commit('setTemplateNewOrigin', 'template')
      context.dispatch('checkHyperAvailableAndQuota', { itemType: 'templates', routeName: 'templateduplicate' })
    }
  }
}
