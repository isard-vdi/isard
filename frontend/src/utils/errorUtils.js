import i18n from '@/i18n'
import { get } from 'lodash'
import router from '@/router'

export class ErrorUtils {
  static getErrorMessageText (errorMessageCode) {
    let errorMessage = ''

    if (errorMessageCode) {
      errorMessage = i18n.t(`errors.${errorMessageCode}`)
    } else {
      errorMessage = i18n.t('errors.generic_error')
    }
    return errorMessage
  }

  static showErrorMessage (snotify, error, message = '', title = '', position = 'centerTop') {
    const errorMessage = message.length > 0 ? message : ErrorUtils.getErrorMessageText(get(error, 'response.data.error'))

    snotify.error(errorMessage, {
      timeout: 2000,
      showProgressBar: false,
      closeOnClick: true,
      pauseOnHover: true,
      position: position
    })
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

  static handleErrors (error, snotify) {
    snotify.clear()
    console.log(error)

    if (error.response.status === 503) {
      router.push({ name: 'Maintenance' })
    } else if (error.response.status === 401) {
      router.push({ name: 'ExpiredSession' })
    } else if (error.response.status === 400) {
      ErrorUtils.showErrorMessage(snotify, error,
        i18n.t('errors.bad_request'),
        i18n.t('errors.bad_request_title'))
    } else {
      ErrorUtils.showErrorMessage(snotify, error)
    }
  }
}
