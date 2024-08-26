import * as validators from '@vuelidate/validators'
import I18n from '@/i18n'

export class ValidationLocalizationConfig {
  static getHelper (param) {
    const { createI18nMessage } = validators
    const { t } = I18n.global || I18n
    const withI18nMessage = createI18nMessage({ t })

    return withI18nMessage
  }
}

const helper = ValidationLocalizationConfig.getHelper()
// wrap each validator.
export const required = helper(validators.required)
// validators that expect a parameter should have `{ withArguments: true }` passed as a second parameter, to annotate they should be wrapped
export const minLength = helper(validators.minLength, { withArguments: true })
// or you can provide the param at definition, statically
export const maxLength = helper(validators.maxLength(10))
