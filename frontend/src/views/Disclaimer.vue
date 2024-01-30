<template>
  <b-container
    fluid
    class="disclaimer-container pl-3 pr-3 pl-xl-5 pr-xl-5 pb-5"
  >
    <div
      class="container"
    >
      <div v-html="messageTemplate" />
      <b-button
        variant="danger"
        @click="reject()"
      >
        Reject
      </b-button><b-button
        variant="success"
        @click="accept()"
      >
        Accept
      </b-button>
    </div>
  </b-container>
</template>
<script>
import { onMounted, computed } from '@vue/composition-api'
import { StringUtils } from '../utils/stringUtils'

export default {
  setup (props, context) {
    const $store = context.root.$store
    onMounted(() => {
      if (StringUtils.isNullOrUndefinedOrEmpty(localStorage.token)) {
        $store.dispatch('navigate', 'login')
      } else {
        $store.dispatch('fetchMessageTemplate', 'disclaimer-acknowledgement')
      }
    })
    const messageTemplate = computed(() => $store.getters.getMessageTemplate)

    const accept = () => {
      $store.dispatch('acceptDisclaimer')
    }
    const reject = () => {
      $store.dispatch('logout')
    }
    return {
      messageTemplate,
      accept,
      reject
    }
  }
}
</script>
