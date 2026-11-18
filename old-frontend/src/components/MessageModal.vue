<template>
  <b-modal
    id="messageModal"
    v-model="showMessageModal"
    size="xl"
    centered
    :header-bg-variant="type"
    :header-text-variant="textColor"
    :body-bg-variant="type"
    :body-text-variant="textColor"
    :footer-bg-variant="type"
    :footer-text-variant="textColor"
    content-class="text-center"
    :hide-footer="!single || !canExtend(single)"
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
    <div
      v-if="single"
      class="ml-4 mr-4"
    >
      <h5>
        {{ single.message }}
      </h5>
    </div>
    <div
      v-for="message in (single ? [] : messages)"
      :key="message.key"
      class="ml-4 mr-4 mb-3 d-flex align-items-center justify-content-between text-left"
    >
      <h5 class="mb-0 mr-3">
        {{ message.message }}
      </h5>
      <b-button
        v-if="canExtend(message)"
        variant="success"
        class="flex-shrink-0"
        :disabled="extending !== null"
        @click="extendTimeout(message)"
      >
        <b-spinner
          v-if="extending === message.key"
          small
          class="mr-1"
        />
        {{ $t('message-modal.extend-time', { minutes: message.extendTime }) }}
      </b-button>
    </div>
    <template
      v-if="single && canExtend(single)"
      #modal-footer
    >
      <b-button
        variant="success"
        :disabled="extending !== null"
        @click="extendTimeout(single)"
      >
        <b-spinner
          v-if="extending !== null"
          small
          class="mr-1"
        />
        {{ $t('message-modal.extend-time', { minutes: single.extendTime }) }}
      </b-button>
    </template>
  </b-modal>
</template>
<script>
import { computed, ref } from '@vue/composition-api'
import { MessageUtils } from '@/utils/messageUtils'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const messages = computed(() => $store.getters.getMessageModal.messages)
    const single = computed(() => messages.value.length === 1 ? messages.value[0] : null)
    const type = computed(() => MessageUtils.highestType(messages.value))
    const textColor = computed(() => MessageUtils.textColor(type.value))
    const extending = ref(null)

    const showMessageModal = computed({
      get: () => $store.getters.getMessageModal.show,
      set: (value) => $store.commit('setShowMessageModal', value)
    })

    const canExtend = (message) => {
      return message.msgCode === 'desktop-time-limit' &&
        message.extendEnabled &&
        message.desktopId
    }

    const closeMessageModal = () => {
      $store.dispatch('showMessageModal', false)
    }

    const extendTimeout = async (message) => {
      extending.value = message.key
      try {
        const extended = await $store.dispatch('extendDesktopTimeout', message.desktopId)
        if (extended) {
          $store.commit('removeMessage', message.key)
          // The clicked button leaves the DOM with its row; without focus the modal stops answering Escape.
          context.root.$nextTick(() => {
            const content = document.querySelector('#messageModal .modal-content')
            if (content) content.focus()
          })
        }
      } finally {
        extending.value = null
      }
    }

    return { messages, single, type, textColor, showMessageModal, closeMessageModal, canExtend, extending, extendTimeout }
  }
}
</script>
