<script setup lang="ts">
import { defineProps, defineEmits } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/icon/Icon.vue'

const { t } = useI18n()

interface Props {
  title: string
  count: number
  icon?: string
  warning?: boolean
  active?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits(['click'])
</script>

<template>
  <button
    type="button"
    class="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-all duration-200 focus:outline-none"
    :class="
      props.active
        ? 'border-brand-300 bg-brand-50 text-brand-700 shadow-xs'
        : 'border-gray-warm-200 bg-base-white text-gray-warm-700 hover:border-brand-200 hover:bg-gray-warm-50'
    "
    :title="
      props.warning
        ? t('components.migration.migration-item-box.quota_exceeded', {
            type: props.title.toLowerCase()
          })
        : undefined
    "
    @click="emit('click')"
  >
    <Icon
      v-if="props.icon"
      :name="props.icon"
      class="h-4 w-4"
      :stroke-color="props.active ? 'brand-600' : 'gray-warm-500'"
    />
    <span>{{ props.title }}</span>
    <span
      class="rounded-full px-2 py-0.5 text-xs font-semibold"
      :class="props.active ? 'bg-brand-100 text-brand-700' : 'bg-gray-warm-100 text-gray-warm-700'"
    >
      {{ props.count }}
    </span>
    <Icon v-if="props.warning" name="alert-triangle" class="h-4 w-4" stroke-color="warning-600" />
  </button>
</template>
