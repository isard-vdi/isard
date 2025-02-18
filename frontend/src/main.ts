import './assets/index.css'

import { computed, createApp } from 'vue'
import { createPinia } from 'pinia'

import { client as authClient } from './gen/oas/authentication'
import { client as apiClient } from './gen/oas/api'

import App from './App.vue'
import router from './router'
import { i18n, setBrowserLocale, setLocale } from './lib/i18n'
import { VueQueryPlugin, type VueQueryPluginOptions } from '@tanstack/vue-query'
import { useCookies as useAuthCookies, getBearer } from './lib/auth'

const cookies = useAuthCookies()
const bearer = computed(() => getBearer(cookies))

// Configure Authentication OAS client
authClient.setConfig({
  baseUrl: '/authentication'
})

import { watch } from 'vue'

// Configure API OAS client
watch(
  bearer,
  (newValue) => {
    apiClient.setConfig({
      headers: newValue
        ? {
            Authorization: `Bearer ${newValue}`
          }
        : undefined
    })
  },
  { immediate: true }
)

console.log(bearer)

localStorage.language ? setLocale(localStorage.language) : setBrowserLocale(i18n)

const vueQueryPluginOptions: VueQueryPluginOptions = {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false
      }
    }
  }
}

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(VueQueryPlugin, vueQueryPluginOptions)

app.mount('#app')
