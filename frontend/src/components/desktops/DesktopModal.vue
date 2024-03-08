<template>
  <b-modal
    id="recycleBinModal"
    v-model="modal.show"
    size="lg"
    :title="$t(`views.desktop.modal.title.${modal.type}`)"
    centered
    header-class="bg-red text-white"
    @hidden="closeModal"
  >
    <b-row
      v-if="modal.type === 'delete'"
      class="ml-2 my-2 pr-3"
    >
      {{ $t('views.desktop.modal.body.text') }}
    </b-row>
    <b-row
      v-if="modal.type === 'delete'"
      class="ml-2 my-2 pr-3"
    >
      <b-col
        v-if="maxTime !== 0 && (modal.tag == null || !modal.tag)"
        cols="12"
      >
        <b-form-checkbox
          id="sendToRecycleBin"
          v-model="sendToRecycleBin"
          name="sendToRecycleBin"
          :value="true"
          :unchecked-value="false"
        >
          {{ $t('views.desktop.modal.body.send-to-recycle-bin') }}
          <span
            v-if="maxTime !== 'null'"
          >{{ `${$t("components.statusbar.recycle-bins.max-time", { time: maxTime })}` }}</span>
        </b-form-checkbox>
      </b-col>
    </b-row>
    <template #modal-footer>
      <b-button
        squared
        class="float-right"
        size="sm"
        @click="closeModal"
      >
        {{ $t('forms.cancel') }}
      </b-button>
      <b-button
        squared
        variant="outline-danger"
        size="sm"
        @click="deleteDesktop"
      >
        {{ $t(`views.desktop.modal.confirmation.delete`) }}
      </b-button>
    </template>
  </b-modal>
</template>
<script>
import { computed, ref } from '@vue/composition-api'

export default {
  setup (_, context) {
    const $store = context.root.$store
    const modal = computed(() => $store.getters.getDesktopModal)
    const maxTime = computed(() => $store.getters.getMaxTime)
    const sendToRecycleBin = ref(false)
    $store.dispatch('fetchDefaultCheck').then(() => {
      sendToRecycleBin.value = $store.getters.getDefaultCheck
    })

    const closeModal = () => {
      $store.dispatch('resetDesktopModal')
    }
    const deleteDesktop = () => {
      $store.dispatch('deleteDesktop', { id: modal.value.item.id, permanent: !sendToRecycleBin.value }).then(() => {
        sendToRecycleBin.value = $store.getters.getDefaultCheck
        closeModal()
      })
    }
    return {
      closeModal,
      modal,
      sendToRecycleBin,
      deleteDesktop,
      maxTime
    }
  }
}
</script>
