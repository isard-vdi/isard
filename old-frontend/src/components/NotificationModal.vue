<template>
  <b-modal
    v-if="showNotificationModal"
    id="notificationModal"
    v-model="showNotificationModal"
    size="xl"
    centered
    :hide-footer="true"
    content-class="text-center"
    @hidden="closeNotificationModal"
  >
    <template #modal-title>
      <h4>
        <b-icon
          icon="exclamation-triangle-fill"
        />
        {{ $t('components.notification-modal.title') }}
      </h4>
    </template>
    <div
      v-for="(notification, index) in notifications"
      :key="index"
      class="ml-4 mr-4 text-left"
    >
      <h5 class="text-center font-weight-bold">
        {{ notification.title }}
      </h5>
      <!-- eslint-disable-next-line vue/no-v-html -->
      <span v-html="notification.body" />
      <hr>
    </div>
  </b-modal>
</template>
<script>

import { computed } from '@vue/composition-api'

export default {
  setup (_, context) {
    const $store = context.root.$store

    const showNotificationModal = computed(() => $store.getters.getShowNotificationModal)
    const notifications = computed(() => $store.getters.getNotifications)

    const closeNotificationModal = () => {
      $store.dispatch('closeNotificationModal')
    }

    return {
      closeNotificationModal,
      notifications,
      showNotificationModal
    }
  }
}

</script>
