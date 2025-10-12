<template>
  <div
    id="app"
    :class="{ guacamole: $route.name === 'Rdp' }"
  >
    <router-view />
    <vue-snotify />
    <MessageModal />
    <NotificationModal />
    <ExpiredSessionModal />
  </div>
</template>

<script>
import { onBeforeMount, onBeforeUnmount } from '@vue/composition-api'
import MessageModal from './components/MessageModal.vue'
import NotificationModal from './components/NotificationModal.vue'
import ExpiredSessionModal from './components/ExpiredSessionModal.vue'
import { listenCookieChange } from '@/helpers/cookies'
import { sessionCookieName } from '@/shared/constants'
import { getCookie } from 'tiny-cookie'

export default {
  components: { MessageModal, NotificationModal, ExpiredSessionModal },
  setup (_, context) {
    const $store = context.root.$store
    const viewsNotRedirected = ['VerifyEmail', 'ResetPassword', 'ForgotPassword']
    let syncTimeout = null

    onBeforeMount(() => {
      listenCookieChange(({ oldValue, newValue }) => {
        if (!getCookie(sessionCookieName)) {
          // Session cookie was removed - handle logout
          $store.dispatch('logout', !viewsNotRedirected.includes(context.root.$route.name))
        } else if (oldValue && newValue && oldValue !== newValue) {
          console.log('Session cookie changed, syncing session...')
          console.log('Old Value:', oldValue)
          console.log('New Value:', newValue)
          // Debounce session sync to prevent rapid successive calls
          if (syncTimeout) {
            clearTimeout(syncTimeout)
          }
          syncTimeout = setTimeout(() => {
            // Session cookie changed (renewed in another tab) - sync the session
            $store.dispatch('syncSessionFromCookie', newValue)
          }, 100) // 100ms debounce
        }
      }, sessionCookieName, 1000)
    })
    onBeforeUnmount(() => {
      // Clear any pending sync timeout
      if (syncTimeout) {
        clearTimeout(syncTimeout)
      }
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
