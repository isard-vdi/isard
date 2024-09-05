<template>
  <b-container
    fluid
    class="disclaimer-container"
  >
    <b-row
      id="disclaimer-card"
      class="justify-content-center"
    >
      <b-form class="w-75">
        <div
          id="new-logo-wrapper"
          class="mb-4"
        >
          <Logo />
        </div>
        <h2
          class="p-2 my-3 ml-3"
          style="color: #44403C !important"
        >
          <strong>{{ messageTemplate.title }}</strong>
        </h2>
        <div style="color: #57534E !important;">
          <!-- eslint-disable -->
          <div
            class="p-2 mb-2 mt-2 ml-3"
            v-html="messageTemplate.body"
          />
          <hr>
          <div
            v-if="messageTemplate.footer"
            class="p-2 mb-2 mt-2 ml-3"
            v-html="messageTemplate.footer"
          />
          <!-- eslint-enable -->
          <b-button
            size="md"
            variant="success"
            style="background-color: #114954 !important; border-radius: .5rem !important; border: none !important; font-weight: 600 !important;"
            class="float-right m-1 mb-4"
            @click="accept()"
          >
            {{ $t('views.disclaimer.accept') }}
          </b-button>
          <b-button
            size="md"
            variant="danger"
            style="background-color: #993a3b !important; border-radius: .5rem !important; border: none !important; font-weight: 600 !important;"
            class="float-right m-1 mb-4"
            @click="logout()"
          >
            {{ $t('views.disclaimer.reject') }}
          </b-button>
        </div>
      </b-form>
    </b-row>
    <b-img
      id="bottom-right-mountains"
      src="@/assets/img/mountains.svg"
    />
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

<style>
#disclaimer-card {
  height: calc(100% - 8rem);
  background-color: #ffffff !important;
  margin: 4rem;
  padding-top: 4rem;
  overflow-y: scroll;
  position: relative;
  border-radius: 1.5rem;
  border: 1px solid #D7D3D0;
  z-index: 2;
  box-shadow: 0px 24px 48px -12px rgba(16, 24, 40, 0.18);
  text-align: justify;
}

#bottom-right-mountains {
  position: absolute;
  bottom: 0;
  right: 0;
  z-index: 1;
}
</style>
