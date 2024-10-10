<template>
  <b-dropdown
    :text="'🌐 ' + langs[$i18n.locale]"
    size="sm"
    variant="outline-secondary"
  >
    <b-dropdown-item
      v-for="(text, lang) in langs"
      :key="lang"
      href="#"
      :value="lang"
      @click="changeLanguage(lang)"
    >
      {{ langs[lang] }}
    </b-dropdown-item>
  </b-dropdown>
</template>

<script>
import { mapActions } from 'vuex'
import moment from 'moment'
import { getLocaleCode } from '@/i18n'

export default {
  props: {
    saveLanguage: Boolean
  },
  data () {
    return {
      langs: {
        ca: 'Català',
        de: 'Deutsch',
        en: 'English',
        es: 'Castellano',
        eu: 'Euskara',
        fr: 'Français',
        pl: 'Polski',
        ru: 'Русский',
        ko: 'Korean'
      }
    }
  },
  methods: {
    ...mapActions([
      'saveNewLanguage'
    ]),
    changeLanguage (lang) {
      this.$store.commit('setLang', lang)
      if (this.saveLanguage) {
        this.saveNewLanguage()
      }
      localStorage.language = getLocaleCode(lang)
      this.$i18n.locale = lang
      moment.locale(lang)
    }
  }
}
</script>
