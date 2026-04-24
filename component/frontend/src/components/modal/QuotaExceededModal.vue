<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { AlertModal } from '@/components/modal'
import { Button } from '@/components/ui/button'

const { t } = useI18n()

defineProps<{
  open: boolean
  title: string
  description: string
  cancelLabel: string
  cancelTo:
    | string
    | { name: string; params?: Record<string, string>; query?: Record<string, string> }
}>()

const emit = defineEmits(['update:open', 'close'])
</script>

<template>
  <AlertModal
    :open="open"
    level="danger"
    size="md"
    :title="title"
    :description="description"
    :close-on-backdrop-click="false"
    :show-close-button="false"
    @close="emit('close')"
    @update:open="emit('update:open', $event)"
  >
    <template #footer>
      <Button hierarchy="link-gray" :as="RouterLink" :to="cancelTo" @click="$emit('close')">
        {{ cancelLabel }}
      </Button>
      <Button
        :as="RouterLink"
        :to="{ name: 'profile', query: { open: 'quota' } }"
        hierarchy="primary"
      >
        {{ t('components.quota-exceeded-modal.go-to-profile') }}
      </Button>
    </template>
  </AlertModal>
</template>
