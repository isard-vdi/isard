import { createI18n, type VueI18n, type I18nMode, type Composer, type I18n } from 'vue-i18n'
import { isRef } from 'vue'

import enUS from '../locales/en-US.json'

type MessageSchema = typeof enUS

export enum Locale {
  English = 'en-US',
  Català = 'ca-ES'
}

const localesWithoutRegion = (() => {
  const result: Record<string, Locale> = {}

  for (const locale in Locale) {
    const value = Locale[locale]

    result[value.split('-')[0]] = Locale[locale]
  }

  return result
})()

const isLocale = (locale: string): locale is Locale =>
  Object.values(Locale).includes(locale as Locale)

export const i18n = createI18n<[MessageSchema]>({
  legacy: false,
  locale: Locale.English,
  fallbackLocale: [Locale.English],
  messages: {
    [Locale.English]: enUS
  }
})

const isComposer = (instance: VueI18n | Composer, mode: I18nMode): instance is Composer => {
  return mode === 'composition' && isRef(instance.locale)
}

const loadLocale = async (locale: Locale) => {
  const messages = await import(`../locales/${locale}.json`)
  return messages.default || messages
}

export const setLocale = async (i18n: I18n, locale: Locale) => {
  // Load the locales
  const messages = await loadLocale(locale)
  i18n.global.setLocaleMessage(locale, messages)

  // Activate it in i18n
  if (isComposer(i18n.global, i18n.mode)) {
    i18n.global.locale.value = locale
  } else {
    i18n.global.locale = locale
  }

  // Other side-effects
  document.querySelector('html')!.setAttribute('lang', locale)
}

export const setBrowserLocale = async (i18n: I18n) => {
  for (const lang of navigator.languages) {
    if (isLocale(lang)) {
      await setLocale(i18n, lang)
      return
    }

    if (localesWithoutRegion[lang]) {
      await setLocale(i18n, localesWithoutRegion[lang])
      return
    }
  }
}
