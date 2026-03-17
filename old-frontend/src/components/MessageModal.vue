<template>
  <b-modal
    id="messageModal"
    v-model="showMessageModal"
    size="xl"
    centered
    :header-bg-variant="messageModal.type"
    :header-text-variant="messageModal.textColor"
    :body-bg-variant="messageModal.type"
    :body-text-variant="messageModal.textColor"
    :footer-bg-variant="messageModal.type"
    :footer-text-variant="messageModal.textColor"
    content-class="text-center"
    :hide-footer="!canExtend"
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
    <template
      v-if="canExtend"
      #modal-footer
    >
      <b-button
        variant="success"
        :disabled="extending"
        @click="extendTimeout"
      >
        <b-spinner
          v-if="extending"
          small
          class="mr-1"
        />
        {{ $t('message-modal.extend-time', { minutes: messageModal.extendTime }) }}
      </b-button>
    </template>
  </b-modal>
</template>
<script>
import { computed, ref } from '@vue/composition-api'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const messageModal = computed(() => $store.getters.getMessageModal)
    const extending = ref(false)

    const showMessageModal = computed({
      get: () => $store.getters.getMessageModal.show,
      set: (value) => $store.commit('setShowMessageModal', value)
    })

    const canExtend = computed(() => {
      return messageModal.value.msgCode === 'desktop-time-limit' &&
        messageModal.value.extendEnabled &&
        messageModal.value.desktopId
    })

    const closeMessageModal = () => {
      $store.dispatch('showMessageModal', false)
    }

    const extendTimeout = async () => {
      extending.value = true
      try {
        await $store.dispatch('extendDesktopTimeout', messageModal.value.desktopId)
        closeMessageModal()
      } finally {
        extending.value = false
      }
    }

    return { messageModal, showMessageModal, closeMessageModal, canExtend, extending, extendTimeout }
  }
}
</script>
