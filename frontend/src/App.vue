<template>
    <div id="app" :class="{ guacamole: this.$route.name === 'Rdp' }">
        <router-view />
        <vue-snotify />
    </div>
</template>

<script>

export default {
  beforeMount () {
    if (sessionStorage.token) {
      this.$store.dispatch('setSession', sessionStorage.token)
    }
    this.$store.dispatch('watchToken')
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
