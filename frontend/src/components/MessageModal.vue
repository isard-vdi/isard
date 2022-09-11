<template>
  <b-modal
    id="messageModal"
    v-model="showMessageModal"
    size="xl"
    centered
    :hide-footer="true"
    :header-bg-variant="messageModal.type"
    :header-text-variant="messageModal.textColor"
    :body-bg-variant="messageModal.type"
    :body-text-variant="messageModal.textColor"
    content-class="text-center"
    @hidden="closeMessageModal"
  >
    <template #modal-title>
      <h4>
        <b-icon
          icon="exclamation-triangle-fill"
        />
        {{ $t('message-modal.title') }}
      </h4>
    </template>
    <div class="ml-4 mr-4">
      <h5>
        {{ messageModal.message }}
      </h5>
    </div>
  </b-modal>
</template>
<script>
import { computed } from '@vue/composition-api'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const messageModal = computed(() => $store.getters.getMessageModal)

    const showMessageModal = computed({
      get: () => $store.getters.getMessageModal.show,
      set: (value) => $store.commit('setShowMessageModal', value)
    })

    const closeMessageModal = () => {
      $store.dispatch('showMessageModal', false)
    }

    return { messageModal, showMessageModal, closeMessageModal }
  }
}
</script>
