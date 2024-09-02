import { createI18n } from 'vue-i18n'

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

// TODO: Add type checking for all the other locales
export const i18n = createI18n<[MessageSchema], `${Locale}`, false>({
  legacy: false,
  locale: Locale.English,
  fallbackLocale: [Locale.English],
})
i18n.global.setLocaleMessage(Locale.English, enUS)

const loadLocale = async (locale: Locale) => {
  const messages = await import(`../locales/${locale}.json`)
  return messages.default || messages
}

export const setLocale = async (locale: Locale) => {
  // Load the locales
  const messages = await loadLocale(locale)
  i18n.global.setLocaleMessage(locale, messages)

  // Activate it in i18n
  i18n.global.locale.value = locale

  // Other side-effects
  document.querySelector('html')!.setAttribute('lang', locale)
}

export const setBrowserLocale = async () => {
  for (const lang of navigator.languages) {
    if (isLocale(lang)) {
      await setLocale(lang)
      return
    }

    if (localesWithoutRegion[lang]) {
      await setLocale(localesWithoutRegion[lang])
      return
    }
  }
}
