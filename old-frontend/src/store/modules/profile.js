import axios from 'axios'
import i18n from '@/i18n'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'
import { ProfileUtils } from '../../utils/profileUtils'

const getDefaultState = () => {
  return {
    profile: {
      quota: {},
      used: {},
      userStorage: {
        tokenWeb: false,
        providerQuota: false
      }
    },
    modalShow: false,
    modalEmailShow: false,
    password: '',
    passwordConfirmation: '',
    profile_loaded: false,
    lang: '',
    passwordPolicy: '',
    currentPassword: '',
    emailAddress: ''
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
    },
    getShowEmailVerificationModal: state => {
      return state.modalEmailShow
    },
    getLang: state => {
      return state.lang
    },
    getPasswordPolicy: state => {
      return state.passwordPolicy
    },
    getCurrentPassword: state => {
      return state.currentPassword
    },
    getEmailAddress: state => {
      return state.emailAddress
    }

  },
  mutations: {
    resetProfileState: (state) => {
      Object.assign(state, getDefaultState())
    },
    resetPasswordState: state => {
      state.password = ''
      state.passwordConfirmation = ''
      state.currentPassword = ''
    },
    resetEmailAddressState: state => {
      state.emailAddress = ''
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
    },
    setShowEmailVerificationModal: (state, modalEmailShow) => {
      state.modalEmailShow = modalEmailShow
    },
    setLang (state, lang) {
      state.lang = lang
    },
    setPasswordPolicy (state, passwordPolicy) {
      state.passwordPolicy = passwordPolicy
    },
    setCurrentPassword (state, currentPassword) {
      state.currentPassword = currentPassword
    },
    setEmailAddress (state, emailAddress) {
      state.emailAddress = emailAddress
    },
    update_profile: (state, profile) => {
      state.profile = { ...state.profile, ...profile }
    }
  },
  actions: {
    socket_usersData (context, data) {
      const userData = JSON.parse(data)
      const profile = { email: userData.email, emailVerified: userData.email_verified }
      context.commit('update_profile', profile)
    },
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
    updateEmail (context, data) {
      return axios.put(`${apiV3Segment}/user`, data).catch(e => {
        ErrorUtils.handleErrors(e, this._vm.$snotify)
      })
    },
    showPasswordModal (context, show) {
      context.commit('setShowPasswordModal', show)
    },
    showEmailVerificationModal (context, show) {
      context.commit('setShowEmailVerificationModal', show)
    },
    resetPasswordState (context) {
      context.commit('resetPasswordState')
    },
    saveNewLanguage (context) {
      const lang = context.getters.getLang
      if (lang) {
        axios.put(`${apiV3Segment}/user/language/${lang}`, {}, { timeout: 25000 }).catch(e => {
          console.error(e)
        })
      }
    },
    fetchPasswordPolicy (context) {
      return axios.get(`${apiV3Segment}/user/password-policy`)
        .then(response => {
          context.commit('setPasswordPolicy', response.data)
        })
        .catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
    },
    resetEmailAddressState (context) {
      context.commit('resetEmailAddressState')
    },
    resetVPN (context, userId) {
      axios.put(`${apiV3Segment}/user/reset-vpn`)
        .then(response => {
          ErrorUtils.showInfoMessage(this._vm.$snotify, i18n.t('messages.info.reset-vpn'))
        })
        .catch(e => {
          ErrorUtils.handleErrors(e, this._vm.$snotify)
        })
    }
  }
}
