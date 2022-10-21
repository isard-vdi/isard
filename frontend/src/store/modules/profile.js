import axios from 'axios'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'
import { ProfileUtils } from '../../utils/profileUtils'

const getDefaultState = () => {
  return {
    profile: {
      quota: {},
      used: {}
    },
    modalShow: false,
    password: '',
    passwordConfirmation: '',
    profile_loaded: false
  }
}

const state = getDefaultState()

export default {
  state,
  getters: {
    getProfile: state => {
      return state.profile
    },
    getProfileLoaded: state => {
      return state.profile_loaded
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
    resetProfileState: (state) => {
      Object.assign(state, getDefaultState())
    },
    resetPasswordState: state => {
      state.password = ''
      state.passwordConfirmation = ''
    },
    setProfile (state, profile) {
      state.profile = profile
      state.profile_loaded = true
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
    resetProfileState (context) {
      context.commit('resetProfileState')
    },
    fetchProfile (context) {
      axios
        .get(`${apiV3Segment}/user`)
        .then(response => {
          context.commit('setProfile', ProfileUtils.parseProfile(response.data))
        })
        .catch(e => {
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
