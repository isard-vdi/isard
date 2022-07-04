import axios from 'axios'
import { ProfileUtils } from '../../utils/profileUtils'
import { ErrorUtils } from '../../utils/errorUtils'
import { apiV3Segment } from '../../shared/constants'

const getDefaultState = () => {
  return {
    profile: {
      quota: {
      }
    },
    modalShow: false,
    password: '',
    passwordConfirmation: ''
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getProfile: state => {
      return state.profile
    },
    getPassword: state => {
      return state.password
    },
    getPasswordConfirmation: state => {
      return state.passwordConfirmation
    },
    getShowPasswordModal: state => {
      return state.modalShow
    }
  },
  mutations: {
    resetPasswordState: (state) => {
      state.password = ''
      state.passwordConfirmation = ''
    },
    setProfile (state, profile) {
      state.profile = profile
    },
    setPassword (state, password) {
      state.password = password
    },
    setPasswordConfirmation (state, passwordConfirmation) {
      state.passwordConfirmation = passwordConfirmation
    },
    setShowPasswordModal: (state, modalShow) => {
      state.modalShow = modalShow
    }
  },
  actions: {
    fetchProfile (context) {
      axios.get(`${apiV3Segment}/user`).then(response => {
        context.commit('setProfile', ProfileUtils.parseProfile(response.data))
      }).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    updatePassword (context, data) {
      return axios.put(`${apiV3Segment}/user`, data).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    showPasswordModal (context, show) {
      context.commit('setShowPasswordModal', show)
    },
    resetPasswordState (context) {
      context.commit('resetPasswordState')
    }
  }
}
