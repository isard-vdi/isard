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
import MessageModal from './components/MessageModal.vue'

export default {
  components: { MessageModal },
  beforeMount () {
    if (localStorage.token && this.$route.name !== 'DirectViewer') {
      this.$store.dispatch('setSession', localStorage.token)
      this.$store.dispatch('openSocket', {})
    }
    this.$store.dispatch('watchToken')
  },
  beforeUnmount () {
    this.$store.dispatch('closeSocket')
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
