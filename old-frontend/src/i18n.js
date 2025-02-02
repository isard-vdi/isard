import Vue from 'vue'
import VueI18n from 'vue-i18n'
import { StringUtils } from './utils/stringUtils'

Vue.use(VueI18n)

function loadLocaleMessages () {
  const locales = require.context('./locales', true, /[A-Za-z0-9-_,\s]+\.json$/i)
  const messages = {}
  locales.keys().forEach(key => {
    const matched = key.match(/([A-Za-z0-9-_]+)\./i)
    if (matched && matched.length > 1) {
      const locale = matched[1]
      messages[locale] = locales(key)
    }
  })
  return messages
}

const NewLocaleToOldLocale = {
  en: 'en-US',
  ca: 'ca-ES',
  eu: 'eu-ES',
  es: 'es-ES',
  fr: 'fr-FR'
}

export function getLocaleCode (locale) {
  return NewLocaleToOldLocale[locale] || locale
}

export default new VueI18n({
  locale: getLocale(),
  fallbackLocale: 'en',
  messages: loadLocaleMessages()
})

function getLocale () {
  const sessionCookie = localStorage.language ? localStorage.language.split('_')[0].split('-')[0] : undefined
  if (StringUtils.isNullOrUndefinedOrEmpty(sessionCookie)) {
    const lang = navigator.language || navigator.browserLanguage || (navigator.languages || ['en'])[0]
    return lang.split('_')[0].split('-')[0]
  }

  return sessionCookie
}
