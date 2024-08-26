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
import { computed } from '@vue/composition-api'

export default {
  components: { Logo },
  setup (_, context) {
    const $store = context.root.$store
    $store.dispatch('fetchMessageTemplate', 'disclaimer-acknowledgement')

    const messageTemplate = computed(() => $store.getters.getMessageTemplate)

    const accept = () => {
      $store.dispatch('acknowledgeDisclaimer')
    }
    const logout = () => {
      $store.dispatch('logout')
    }
    return {
      messageTemplate,
      accept,
      logout
    }
  }
}
</script>
