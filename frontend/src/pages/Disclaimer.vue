<template>
  <b-container
    fluid
    class="disclaimer-container pl-3 pr-3 pb-5"
  >
    <b-row class="justify-content-center">
      <b-form class="w-75">
        <div
          id="logo-wrapper"
          class="mb-4"
        >
          <Logo />
        </div>
        <h2 class="my-3 ml-2">
          <strong>{{ messageTemplate.title }}</strong>
        </h2>
        <div>
          <b-alert
            :show="dismissCountDown"
            variant="warning"
            @dismissed="dismissCountDown=0"
            @dismiss-count-down="countDownChanged"
          >
            {{ $t('views.disclaimer.disclaimer-accepted', { seconds: dismissCountDown }) }}
          </b-alert>
          <b-button
            v-show="dismissCountDown"
            size="md"
            class="btn-red rounded-pill mt-2"
            @click="logout()"
          >
            {{ $t(`views.maintenance.go-login`) }}
          </b-button>
        </div>
        <div
          v-show="showUpdateDisclaimerText"
        >
          <!-- eslint-disable -->
          <div
            class="p-2 mb-2 mt-2 ml-3"
            v-html="messageTemplate.body"
          />
          <hr>
          <div
            class="p-2 mb-2 mt-2 ml-3"
            v-html="messageTemplate.footer"
          />
          <!-- eslint-enable -->
          <b-button
            size="md"
            variant="success"
            class="rounded-pill float-right m-1"
            @click="accept()"
          >
            {{ $t('views.disclaimer.accept') }}
          </b-button>
          <b-button
            size="md"
            variant="danger"
            class="rounded-pill float-right m-1"
            @click="logout()"
          >
            {{ $t('views.disclaimer.reject') }}
          </b-button>
        </div>
      </b-form>
    </b-row>
  </b-container>
</template>

<script>
import Logo from '@/components/Logo.vue'
import { onMounted, computed, ref } from '@vue/composition-api'
import { StringUtils } from '../utils/stringUtils'

export default {
  components: { Logo },
  setup (_, context) {
    const $store = context.root.$store
    onMounted(() => {
      if (StringUtils.isNullOrUndefinedOrEmpty(localStorage.token)) {
        $store.dispatch('navigate', 'login')
      } else {
        $store.dispatch('fetchMessageTemplate', 'disclaimer-acknowledgement')
      }
    })
    const showUpdateDisclaimerText = ref(true)
    const messageTemplate = computed(() => $store.getters.getMessageTemplate)

    const dismissSecs = ref(10)
    const dismissCountDown = ref(0)

    const countDownChanged = (countDown) => {
      dismissCountDown.value = countDown
      if (countDown === 0) {
        $store.dispatch('logout')
      }
    }
    const showAlert = () => {
      dismissCountDown.value = dismissSecs.value
    }

    const accept = () => {
      $store.dispatch('acknowledgeDisclaimer').then(() => {
        localStorage.removeItem('token')
        showUpdateDisclaimerText.value = false
        showAlert()
      })
    }
    const logout = () => {
      $store.dispatch('logout')
    }
    return {
      messageTemplate,
      accept,
      logout,
      dismissCountDown,
      countDownChanged,
      showAlert,
      showUpdateDisclaimerText
    }
  }
}
</script>
