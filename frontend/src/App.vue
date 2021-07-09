<template>
    <div id="app" :class="{ guacamole: this.$route.name === 'Rdp' }">
        <router-view />
        <vue-snotify />
    </div>
</template>

<script>

export default {
  beforeMount () {
    if (localStorage.token) {
      this.$store.dispatch('setSession', localStorage.token)
    }
  }
}

</script>

<style>
#app {
    font-family: Arial, Avenir, Helvetica, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    color: #2c3e50;
}

.guacamole {
  overflow: hidden;
  width: 100%;
  height: 100%;
}
</style>
