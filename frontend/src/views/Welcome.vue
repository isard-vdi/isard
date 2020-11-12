<template>
  <b-container fluid class="vh-100">
    <b-row class="h-100 d-flex justify-content-center align-items-center">
      <b-col md="1"/>
      <b-col md="10" class="mt-n4">
        <transition-group appear name="fade">
          <b-img fluid style="max-width: 10rem; max
          -height: 14rem;" key="img" src="../assets/logo.svg"/>
          <h1 key="title">{{ $t('views.welcome.title') }}</h1>
          <b-button class="btn" key="button" variant="primary" size="lg" :href="login_url">
            <b-icon icon="unlock-fill" variant="white"></b-icon>
            {{ $t('views.welcome.button') }}
          </b-button>
        </transition-group>
      </b-col>
      <b-col md="1"/>
    </b-row>
  </b-container>
</template>

<script>
// @ is an alias to /src

export default {
  data () {
    return {
      login_url: window.location.protocol + '//' + window.location.host + '/login'
    }
  }
}
</script>

<style scoped>
  .fade-enter-active, .fade-leave-active {
    transition: opacity 1s;
  }
  .fade-enter, .fade-leave-to {
    opacity: 0;
  }
</style>
