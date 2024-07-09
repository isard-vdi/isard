// Bootstrap dependencies
import 'bootstrap/dist/css/bootstrap.css'
import 'bootstrap-vue/dist/bootstrap-vue.css'
import 'vue-select/dist/vue-select.css'
// Custom css
import '@/assets/global.css'
import 'vue-snotify/styles/simple.css'

// Isard styles
import './assets/styles.css'
import './assets/table_styles.css'
import './assets/styles_standard.css'
import './assets/styles_xl.css'
import './assets/styles_small.css'

import VueCompositionAPI from '@vue/composition-api'
import { BootstrapVue, IconsPlugin, VBTooltip } from 'bootstrap-vue'
import { faCentos, faFedora, faGithub, faGoogle, faLinux, faUbuntu, faWindows } from '@fortawesome/free-brands-svg-icons'
import { faDesktop, faPlay, faStop, faTrash, faVideo, faMemory, faMicrochip, faBan, faSave, faCompactDisc, faCubes, faUserCog, faCalendar, faRecycle, faChartLine } from '@fortawesome/free-solid-svg-icons'

import App from './App.vue'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
// Vue Snotify dependencies
import Snotify from 'vue-snotify'
import Vue from 'vue'
import i18n from './i18n'
// FontAwesome
import { library } from '@fortawesome/fontawesome-svg-core'
import router from './router'
import store from './store'

import axiosSetup from './utils/axios'

// Websockets
import VueSocketIOExt from 'vue-socket.io-extended'
import { socket } from './utils/socket-instance'

// FloatingButton component
import VueFab from 'vue-float-action-button'

// Vue Select plugin
import vSelect from 'vue-select'

Vue.component('VSelect', vSelect)

console.log(i18n.locale)

axiosSetup()

library.add(faDesktop, faPlay, faStop, faTrash, faWindows, faUbuntu, faFedora, faLinux, faCentos, faGithub, faGoogle, faVideo, faMemory, faMicrochip, faBan, faSave, faCompactDisc, faCubes, faUserCog, faCalendar, faRecycle, faChartLine)

Vue.component('FontAwesomeIcon', FontAwesomeIcon)

// Install BootstrapVue and the BootstrapVue icon components plugin
Vue.use(BootstrapVue)
Vue.use(IconsPlugin)
Vue.use(Snotify)
Vue.use(VueCompositionAPI)
Vue.use(VueFab)
Vue.use(VueSocketIOExt, socket, { store })

Vue.config.productionTip = false

Vue.filter('truncate', function (value, size) {
  if (!value) return ''
  value = value.toString()

  if (value.length <= size) {
    return value
  }
  return value.substr(0, size) + '...'
})

Vue.directive('b-tooltip', VBTooltip)

new Vue({
  router,
  store,
  i18n,
  render: h => h(App)
}).$mount('#app')
