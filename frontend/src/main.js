import Vue from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'

import { BootstrapVue, IconsPlugin } from 'bootstrap-vue'
// Bootstrap dependencies
import 'bootstrap/dist/css/bootstrap.css'
import 'bootstrap-vue/dist/bootstrap-vue.css'
// Custom css
import '@/assets/global.css'

// Vue Snotify dependencies
import Snotify from 'vue-snotify'
import 'vue-snotify/styles/material.css'

// FontAwesome
import { library } from '@fortawesome/fontawesome-svg-core'
import { faWindows, faUbuntu, faFedora, faLinux, faCentos, faGithub, faGoogle } from '@fortawesome/free-brands-svg-icons'
import { faDesktop } from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import i18n from './i18n'

library.add(faDesktop, faWindows, faUbuntu, faFedora, faLinux, faCentos, faGithub, faGoogle)

Vue.component('font-awesome-icon', FontAwesomeIcon)

// Install BootstrapVue and the BootstrapVue icon components plugin
Vue.use(BootstrapVue)
Vue.use(IconsPlugin)
Vue.use(Snotify)

Vue.config.productionTip = false

Vue.mixin({
  methods: {
    isNullOrUndefined (arg) {
      return arg === null || arg === undefined || arg === 'undefined' || arg === ''
    },
    notifySuccess (title, message) {
      this.$snotify.success(message, title, {
        timeout: 5000,
        showProgressBar: true,
        closeOnClick: true,
        pauseOnHover: true
      })
    },
    notifyError (title, message) {
      this.$snotify.error(message, title, {
        timeout: 5000,
        showProgressBar: true,
        closeOnClick: true,
        pauseOnHover: true
      })
    }
  }
})

new Vue({
  router,
  store,
  i18n,
  render: h => h(App)
}).$mount('#app')
