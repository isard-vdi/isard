<template>
  <Dropdown
    v-model="state.lang"
    :options="state.langs"
    option-label="name"
    :placeholder="`🌐  ${
      state.langs.filter((l) => l.code == state.lang)[0].name
    }`"
    @change="changeLanguage"
  />
</template>

<script>
import * as cookies from 'tiny-cookie';
import { useI18n } from 'vue-i18n';

import { defineComponent, reactive, ref } from 'vue';
import { usePrimeVue } from 'primevue/config';

export default defineComponent({
  setup() {
    const i18n = useI18n();
    const primevue = usePrimeVue();
    if (i18n.messages.value[i18n.locale.value]) {
      primevue.config.locale =
        i18n.messages.value[i18n.locale.value]['primevue'];
    }

    let state = reactive({
      lang: ref(i18n.locale),
      langs: [
        { name: 'Castellano', code: 'es' },
        { name: 'Català', code: 'ca' },
        { name: 'Deutsch', code: 'de' },
        { name: 'English', code: 'en' },
        { name: 'Euskara', code: 'eu' },
        { name: 'Français', code: 'fr' },
        { name: 'Русский', code: 'ru' }
      ]
    });
    const changeLanguage = () => {
      cookies.setCookie('language', state.lang.code);
      i18n.locale.value = state.lang.code;
      if (i18n.messages.value[i18n.locale.value]) {
        primevue.config.locale =
          i18n.messages.value[i18n.locale.value]['primevue'];
      }
    };
    return {
      state,
      changeLanguage
    };
  }
});
</script>
