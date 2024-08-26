import './assets/index.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import { client } from './gen/oas/authentication'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'

// Configure Authentication OAS client
client.setConfig({
  baseUrl: '/authentication'
})

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n)

app.mount('#app')
