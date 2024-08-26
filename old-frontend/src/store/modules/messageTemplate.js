import axios from 'axios'
import { apiV3Segment, authenticationSegment, sessionCookieName } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'
import { getCookie } from 'tiny-cookie'

const getDefaultState = () => {
  return {
    messageTemplate: ''
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getMessageTemplate: state => {
      return state.messageTemplate
    }
  },
  mutations: {
    setMessageTemplate: (state, messageTemplate) => {
      state.messageTemplate = messageTemplate
    }
  },
  actions: {
    fetchMessageTemplate (context, messageTemplateId) {
      if (messageTemplateId === 'disclaimer-acknowledgement') {
        axios.get(`${apiV3Segment}/disclaimer`).then(response => {
          context.commit(
            'setMessageTemplate',
            response.data
          )
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
      } else {
        axios.get(`${apiV3Segment}/message-template/` + messageTemplateId).then(response => {
          context.commit(
            'setMessageTemplate',
            response.data.messageTemplate
          )
        }).catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
      }
    },
    acknowledgeDisclaimer (context) {
      const disclaimerAxios = axios.create()
      disclaimerAxios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${getCookie(sessionCookieName)}`
        return config
      })
      disclaimerAxios.post(`${authenticationSegment}/acknowledge-disclaimer`, {}).then((response) => {
        context.dispatch('login')
      })
    }
  }
}
