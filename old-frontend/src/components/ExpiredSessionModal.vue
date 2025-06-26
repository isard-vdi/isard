<template>
  <b-modal
    v-model="expiredSessionModal.show"
    size="lg"
    :title="$t(`components.expired-modal.${expiredSessionModal.kind}.title`)"
    centered
    header-class="bg-red text-white"
    no-close-on-backdrop
    hide-header-close
    hide-footer
  >
    <div class="w-100">
      <p>{{ $t(`components.expired-modal.${expiredSessionModal.kind}.description`) }}</p>
      <b-button
        :pill="true"
        variant="outline-primary"
        size="sm"
        @click="buttonClick"
      >
        {{ $t(`components.expired-modal.${expiredSessionModal.kind}.button`) }}
      </b-button>
    </div>
  </b-modal>
</template>

<script>
import { computed } from '@vue/composition-api'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const expiredSessionModal = computed(() => $store.getters.getExpiredSessionModal)

    const buttonClick = () => {
      if (expiredSessionModal.value.kind === 'renew') {
        $store.dispatch('renew', true)
      } else {
        $store.dispatch('logout', true)
      }
    }

    return { expiredSessionModal, buttonClick }
  }
}
</script>
