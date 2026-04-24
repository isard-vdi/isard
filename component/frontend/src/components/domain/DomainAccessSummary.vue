<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Icon } from '@/components/icon'
import { Separator } from '@/components/ui/separator'

// interface Bastion

interface Props {
  credentials?: {
    username?: string
    password?: string
  }
  viewers?: string[]
  fullscreen?: boolean
  // bastion?:
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false
})

const { t } = useI18n()
</script>

<template>
  <div class="grid grid-cols-4 gap-6 bg-gray-warm-50 p-4 rounded-md border border-gray-warm-200">
    <!-- Credentials -->
    <div class="flex flex-col gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-access-summary.credentials.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-8">
        <div class="flex items-center gap-2">
          <Icon name="user-03" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{ props.credentials?.username }}</span>
        </div>
        <div class="flex items-center gap-2">
          <Icon name="passcode-lock" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">********</span>
        </div>
      </div>
    </div>

    <!-- Viewers -->
    <div class="flex flex-col col-span-3 gap-4">
      <div class="flex items-center gap-2.5">
        <div class="text-sm font-bold text-gray-warm-500">
          {{ t('components.domain-access-summary.viewers.title') }}
        </div>
        <Separator class="flex-1" />
      </div>
      <div class="flex items-center gap-8">
        <div class="flex items-center gap-2">
          <Icon name="expand-06" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{
            props.fullscreen
              ? t('components.domain-info-modal.fields.viewers.fullscreen-enabled')
              : t('components.domain-info-modal.fields.viewers.fullscreen-disabled')
          }}</span>
        </div>
        <div class="flex items-center gap-2">
          <Icon name="monitor" size="md" stroke-color="gray-warm-700" />
          <span class="text-sm font-semibold">{{
            props.viewers
              ?.map((viewer) => t(`viewers.${viewer.toLowerCase().replace('_', '-')}`))
              .join(', ')
          }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
