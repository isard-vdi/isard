import i18n from '@/i18n'

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

  static errorMessageDefinition = {
    507: {
      1: 'create_desktop_user_quota',
      2: 'create_desktop_group_quota',
      3: 'create_desktop_category_quota'
    }
  }
}
