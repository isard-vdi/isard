import i18n from '@/i18n'
import { get } from 'lodash'
import router from '@/router'

export class ErrorUtils {
  static getErrorMessageText (errorMessageCode, params = {}) {
    let errorMessage = ''

    if (errorMessageCode) {
      errorMessage = i18n.t(`errors.${errorMessageCode}`, params)
    } else {
      errorMessage = i18n.t('errors.generic_error')
    }
    return errorMessage
  }

  static showErrorNotification (snotify, errorMessage, position = 'centerTop', timeout = 2000) {
    snotify.error(errorMessage, {
      timeout,
      showProgressBar: false,
      closeOnClick: true,
      pauseOnHover: true,
      position: position
    })
  }

  static showErrorMessage (snotify, error, message = '', title = '', position = 'centerTop') {
    const errorMessage = message.length > 0 ? message : ErrorUtils.getErrorMessageText(get(error, 'response.data.description_code'), get(error, 'response.data.params'))

    this.showErrorNotification(snotify, errorMessage, position)
  }

  static showInfoMessage (snotify, message, title = '', showProgressBar = true, timeout = 2000, position = 'centerTop') {
    snotify.info(message, {
      title,
      timeout,
      showProgressBar,
      closeOnClick: true,
      pauseOnHover: true,
      position
    })
  }

  static showRedirectMessage (snotify, error, redirectButtons = {}) {
    const errorMessage = ErrorUtils.getErrorMessageText(get(error, 'response.data.description_code'), get(error, 'response.data.params'))
    const config = {
      position: 'centerTop',
      buttons: [
        { text: i18n.t('messages.ok'), action: () => this.closeNotification(snotify), bold: true }
      ]
    }
    config.buttons = config.buttons.concat(redirectButtons)
    snotify.confirm(errorMessage, config)
  }

  static closeNotification (snotify) {
    snotify.clear()
  }

  static goTo (snotify, name) {
    router.push({ name })
    snotify.clear()
  }

  static handleErrors (error, snotify) {
    snotify.clear()
    console.log(error)

    // Errors 401, 500 and 503 are handled through axios interceptors in the axios.js file
    if (![401, 500, 503].includes(error.response.status)) {
      // The quotas errors will show a different notification redirecting to the user profile
      if (error.response.data.description_code.includes('quota')) {
        const buttons = [
          { text: i18n.t('messages.confirmation.go-to-profile'), action: () => this.goTo(snotify, 'profile'), bold: true }
        ]
        ErrorUtils.showRedirectMessage(snotify, error, buttons)
      } else {
        ErrorUtils.showErrorMessage(snotify, error)
      }
    }
  }
}
