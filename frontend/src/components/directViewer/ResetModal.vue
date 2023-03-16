<template>
  <b-modal
    id="visibilityModal"
    v-model="modal.show"
    size="lg"
    :title="$t('views.direct-viewer.reset-modal.title')"
    centered
    hide-footer
    header-class="
    bg-red
    text-white"
    @hidden="closeModal"
  >
    <b-row
      class="ml-2 my-2 pr-3"
    >
      <b-col
        cols="9"
        class="mt-2"
      >
        <p>
          {{ $t(`views.direct-viewer.reset-modal.option.reset-desktop`) }}
        </p>
      </b-col>
      <b-col
        cols="3"
        class="mt-2 text-center"
      >
        <b-button
          :pill="true"
          variant="outline-danger"
          block
          size="sm"
          @click="resetDesktop()"
        >
          {{ $t(`views.direct-viewer.reset-modal.confirmation.reset-desktop`) }}
        </b-button>
      </b-col>
    </b-row>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'

export default {
  setup (_, context) {
    const $store = context.root.$store
    const modal = computed(() => $store.getters.getResetModal)
    const resetDesktop = () => {
      $store.dispatch('resetDesktop', {
        token: modal.value.item.token,
        action: modal.value.item.action
      }).then(() => {
        closeModal()
      })
    }
    const closeModal = () => {
      $store.dispatch('resetResetModal')
    }
    return {
      closeModal,
      modal,
      resetDesktop
    }
  }
}
</script>
