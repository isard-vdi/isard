<template>
  <b-container
    fluid
    class="vh-100"
  >
    <b-row class="h-100 d-flex justify-content-center align-items-center">
      <b-col md="1" />
      <b-col
        v-if="!customMaintenanceText.enabled"
        md="10"
      >
        <transition-group
          appear
          name="fade"
        >
          <b-img
            key="img"
            fluid
            style="max-width: 12rem; max-height: 16rem;"
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
            key="loginLink"
            @click="goToLogin()"
          >
            {{ $t('views.maintenance.go-login') }}
          </b-button>
        </transition-group>
      </b-col>
      <b-col
        v-else
        md="10"
      >
        <transition-group
          appear
          name="fade"
        >
          <b-img
            key="img"
            fluid
            style="max-width: 12rem; max-height: 16rem;"
            class="mt-n4"
            src="../assets/logo.svg"
          />
          <h1 key="text">
            {{ customMaintenanceText.title }}
          </h1>
          <h2 key="text2">
            {{ customMaintenanceText.body }}
          </h2>
          <br key="space">
          <b-button
            key="loginLink"
            @click="goToLogin()"
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
// @ is an alias to /src
import { computed, onMounted, ref } from '@vue/composition-api'

export default {
  setup (props, context) {
    const $store = context.root.$store
    const user = computed(() => $store.getters.getUser)

    const customMaintenanceText = ref(false)

    const checkMaintenanceStatus = async () => {
      const status = await $store.dispatch('fetchMaintenanceStatus')
      if (!status) {
        $store.dispatch('navigate', 'desktops')
      }
    }

    onMounted(async () => {
      const data = await $store.dispatch('fetchMaintenanceText')
      customMaintenanceText.value = data

      await checkMaintenanceStatus()
      setInterval(checkMaintenanceStatus, 5000)
    })
    const goToLogin = () => {
      if (user) {
        $store.dispatch('logout')
      } else {
        window.location.pathname = '/login'
      }
    }

    return {
      goToLogin,
      customMaintenanceText
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
  h2 {
        white-space: pre-line;
    }
</style>
