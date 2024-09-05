<template>
  <div
    id="app"
    :class="{ guacamole: $route.name === 'Rdp' }"
  >
    <router-view />
    <vue-snotify />
    <MessageModal />
  </div>
</template>

<script>
import { onBeforeMount, onBeforeUnmount } from '@vue/composition-api'
import MessageModal from './components/MessageModal.vue'
import { listenCookieChange } from '@/helpers/cookies'
import { sessionCookieName } from '@/shared/constants'
import { getCookie } from 'tiny-cookie'

export default {
  components: { MessageModal },
  setup (_, context) {
    const $store = context.root.$store
    const viewsNotRedirected = ['VerifyEmail', 'ResetPassword', 'ForgotPassword']
    onBeforeMount(() => {
      listenCookieChange((_, { oldValue, newValue }) => {
        if (!getCookie(sessionCookieName)) {
          $store.dispatch('logout', !viewsNotRedirected.includes(context.root.$route.name))
        }
      }, sessionCookieName, 1000)
    })
    onBeforeUnmount(() => {
      $store.dispatch('closeSocket')
    })
  }
}

</script>

<style>
#app {
    font-family: Arial, Avenir, Helvetica, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    color: #2c3e50;
    height: 100%;
    overflow-y: hidden;
}

.guacamole {
  overflow: hidden;
  width: 100%;
  height: 100%;
}
</style>
