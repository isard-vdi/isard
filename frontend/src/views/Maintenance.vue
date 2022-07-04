<template>
  <b-container
    fluid
    class="vh-100"
  >
    <b-row class="h-100 d-flex justify-content-center align-items-center">
      <b-col md="1" />
      <b-col md="10">
        <transition-group
          appear
          name="fade"
        >
          <b-img
            key="img"
            fluid
            style="max-width: 12rem; max
          -height: 16rem;"
            class="mt-n4"
            src="../assets/logo.svg"
          />
          <h1
            key="title"
            class="mt-2"
          >
            {{ $t('views.maintenance.title') }}
          </h1>
          <h2 key="text">
            {{ $t('views.maintenance.the-service') }}
          </h2>
          <h2 key="text2">
            {{ $t('views.maintenance.sorry') }}
          </h2>
          <br key="space">
          <b-button
            key="loginlink"
            @click="navigate('Login')"
          >
            {{ $t('views.maintenance.go-login') }}
          </b-button>
        </transition-group>
      </b-col>
      <b-col md="1" />
    </b-row>
  </b-container>
</template>

<script>
import { mapActions } from 'vuex'

// @ is an alias to /src

export default {
  methods: {
    ...mapActions([
      'navigate'
    ])
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
