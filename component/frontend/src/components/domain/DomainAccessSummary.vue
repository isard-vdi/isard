<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Icon } from '@/components/icon'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'

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
  <div
    class="grid grid-cols-1 sm:grid-cols-4 gap-6 bg-gray-warm-50 p-4 rounded-md border border-gray-warm-200"
  >
    <!-- Loading skeleton -->
    <template v-if="props.loading">
      <div class="flex flex-col gap-4">
        <div class="flex items-center gap-2.5">
          <Skeleton class="h-4 w-20" />
          <Skeleton class="flex-1 h-px" />
        </div>
        <div class="flex flex-wrap gap-x-6 gap-y-3">
          <Skeleton class="h-5 w-20" />
          <Skeleton class="h-5 w-16" />
        </div>
      </div>
      <div class="flex flex-col sm:col-span-3 gap-4">
        <div class="flex items-center gap-2.5">
          <Skeleton class="h-4 w-16" />
          <Skeleton class="flex-1 h-px" />
        </div>
        <div class="flex flex-wrap gap-x-6 gap-y-3">
          <Skeleton class="h-5 w-24" />
          <Skeleton class="h-5 w-32" />
        </div>
      </div>
    </template>

    <!-- Content -->
    <template v-else>
      <!-- Credentials -->
      <div class="flex flex-col gap-4">
        <div class="flex items-center gap-2.5">
          <div class="text-sm font-bold text-gray-warm-500">
            {{ t('components.domain-access-summary.credentials.title') }}
          </div>
          <Separator class="flex-1" />
        </div>
        <div class="flex flex-wrap items-center gap-x-8 gap-y-3">
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
      <div class="flex flex-col sm:col-span-3 gap-4">
        <div class="flex items-center gap-2.5">
          <div class="text-sm font-bold text-gray-warm-500">
            {{ t('components.domain-access-summary.viewers.title') }}
          </div>
          <Separator class="flex-1" />
        </div>
        <div class="flex flex-wrap items-center gap-x-6 gap-y-3">
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
    </template>
  </div>
</template>
