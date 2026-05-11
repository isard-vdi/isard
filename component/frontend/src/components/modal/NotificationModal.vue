<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Modal } from '@/components/modal'
import { useNotificationModalStore } from '@/stores/notification-modal'
import Icon from '@/components/icon/Icon.vue'

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
    <div class="flex flex-col gap-3">
      <template v-for="notification in store.notifications" :key="notification.id">
        <div
          class="flex flex-col gap-2 p-5 pl-3 bg-base-white border border-gray-warm-300 rounded-lg overflow-hidden transition-transform duration-300 hover:translate-x-2"
        >
          <div class="flex gap-4 items-center">
            <div class="self-stretch border-r border-brand-200 flex items-center pr-3">
              <Icon
                name="bell-01"
                size="lg"
                class="shrink-0 bg-brand-200 p-1 rounded-full"
                stroke-color="brand-700"
              />
            </div>
            <div class="w-full">
              <h5 class="font-bold text-lg text-brand-700">
                {{ notification.title }}
              </h5>
              <div v-if="notification.body" v-html="notification.body" class="text-md mb-2" />
              <footer
                v-if="notification.footer"
                v-html="notification.footer"
                class="w-fit ml-auto border-t border-gray-warm-200 pt-1 pl-7 text-right text-sm font-semibold text-gray-warm-500"
              ></footer>
            </div>
          </div>
        </div>
      </template>
    </div>
  </Modal>
</template>
