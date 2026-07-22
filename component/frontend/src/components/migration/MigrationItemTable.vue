<script setup lang="ts">
import { defineProps } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/icon/Icon.vue'

const { t } = useI18n()

interface Props {
  items: {
    id: string
    name: string
  }[]
  title?: string
  icon?: string
  loading?: boolean
}

const props = defineProps<Props>()
</script>

<template>
  <div
    class="w-full overflow-hidden rounded-xl border border-gray-warm-200 bg-base-white shadow-xs"
  >
    <div class="flex items-center gap-2 border-b border-gray-warm-200 bg-gray-warm-50 px-4 py-2.5">
      <Icon v-if="props.icon" :name="props.icon" class="h-4 w-4" stroke-color="gray-warm-500" />
      <span class="text-xs font-semibold uppercase tracking-wide text-gray-warm-600">
        {{ props.title || t('components.migration.migration-item-table.name') }}
      </span>
      <span
        class="ml-auto rounded-full bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-700"
      >
        {{ props.items.length }}
      </span>
    </div>

    <ul class="max-h-[30vh] divide-y divide-gray-warm-100 overflow-y-auto">
      <li
        v-for="item in props.items"
        :key="item.id"
        class="truncate px-4 py-2 text-sm text-gray-warm-800 transition-colors hover:bg-gray-warm-50"
        :title="item.name"
      >
        {{ item.name }}
      </li>
    </ul>
  </div>
</template>
