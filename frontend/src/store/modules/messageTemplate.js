import axios from 'axios'
import { apiV3Segment, authenticationSegment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'
import store from '@/store/index.js'

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
        const disclaimerAxios = axios.create()
        disclaimerAxios.interceptors.request.use(config => {
          config.headers.Authorization = `Bearer ${localStorage.token}`
          return config
        })
        disclaimerAxios.get(`${apiV3Segment}/message-template/` + messageTemplateId).then(response => {
          context.commit(
            'setMessageTemplate',
            response.data.message
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
    acceptDisclaimer (context) {
      const disclaimerAxios = axios.create()
      disclaimerAxios.interceptors.request.use(config => {
        config.headers.Authorization = `Bearer ${localStorage.token}`
        return config
      })
      return disclaimerAxios.post(`${authenticationSegment}/disclaimer`).then(response => {
        store.dispatch('loginSuccess', response.data)
      }).catch(e => {
        ErrorUtils.handleAuthErrors(e, this._vm.$snotify)
      })
    }
  }
}
