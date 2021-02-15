import * as cookies from 'tiny-cookie';

import { createI18n } from 'vue-i18n';

const loadMessages = () => {
  const locales = require.context('@/locales', true, /[\w-]+\.json$/i);
  return locales.keys().reduce(
    (locs, loc) => ({
      ...locs,
      [loc.replace(/\.|\/|json/g, '')]: locales(loc)
    }),
    {}
  );
};

function getLocale(): string {
  const sessionCookie = cookies.getCookie('language');
  if (!sessionCookie) {
    const lang = navigator.language || (navigator.languages || ['en'])[0];
    return lang.split('_')[0].split('-')[0];
  }

  return sessionCookie;
}

export default createI18n({
  locale: getLocale(),
  fallbackLocale: 'en',
  messages: loadMessages()
});
