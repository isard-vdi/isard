<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Modal } from '@/components/modal'
import { useNotificationModalStore } from '@/stores/notification-modal'
import { NotificationList } from '../notification'

const { t } = useI18n()
const store = useNotificationModalStore()
</script>

<template>
  <Modal
    :title="t('components.notification-modal.title')"
    :open="store.open"
    @close="store.close()"
    size="3xl"
  >
    <NotificationList :notifications="store.notifications" heading-level="h3" />
  </Modal>
</template>
