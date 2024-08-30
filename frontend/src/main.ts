import './assets/index.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import { client } from './gen/oas/authentication'
import App from './App.vue'
import router from './router'
import { i18n, setBrowserLocale } from './lib/i18n'
import { VueQueryPlugin } from '@tanstack/vue-query'

// Configure Authentication OAS client
client.setConfig({
  baseUrl: '/authentication'
})

setBrowserLocale(i18n)

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(VueQueryPlugin)

app.mount('#app')
