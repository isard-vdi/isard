import i18n from '@/i18n'
import router from '@/router'
import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'

const getDefaultState = () => {
  return {
    templateNewItemId: ''
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getTemplateNewItemId: state => {
      return state.templateNewItemId
    }
  },
  mutations: {
    resetTemplateState: (state) => {
      Object.assign(state, getDefaultState())
    },
    setTemplateNewItemId: (state, desktopId) => {
      state.templateNewItemId = desktopId
    }
  },
  actions: {
    createNewTemplate (_, payload) {
      ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.creating-template'), '', true, 1000)

      axios.post(`${apiV3Segment}/template`, payload).then(response => {
        router.push({ name: 'desktops' })
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    resetTemplateState (context) {
      context.commit('resetTemplateState')
    },
    checkCreateTemplateQuota (context, desktopId) {
      context.commit('setTemplateNewItemId', desktopId)
      const config = context.getters.getConfig
      if (!config.quota) {
        context.dispatch('navigate', 'templatenew')
      } else {
        axios.get(`${apiV3Segment}/templates/count`).then(response => {
          if (response.data.count < config.quota.templates) {
            context.dispatch('navigate', 'templatenew')
          } else {
            ErrorUtils.showErrorNotification(this._vm.$snotify, i18n.t('errors.template_new_user_quota_exceeded'))
          }
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
      }
    }
  }
}
