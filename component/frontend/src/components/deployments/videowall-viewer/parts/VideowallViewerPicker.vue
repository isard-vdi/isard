<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, ChevronDown, Search } from 'lucide-vue-next'

import type { VideowallDesktop } from '@/lib/videowall'
import { cn } from '@/lib/utils'

import { AvatarLabel } from '@/components/avatar-label'
import { Icon } from '@/components/icon'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxTrigger
} from '@/components/ui/combobox'

import { AVATAR_LABEL_TRUNCATE } from '../constants'

interface Props {
  desktops: VideowallDesktop[]
  selectedId: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{ pick: [id: string] }>()

const { t } = useI18n()

const open = ref(false)
const search = ref('')
watch(open, (isOpen) => {
  if (!isOpen) search.value = ''
})
const pickable = computed(() => {
  const needle = search.value.trim().toLowerCase()
  if (!needle) return props.desktops
  return props.desktops.filter(
    (d) => d.user_name.toLowerCase().includes(needle) || d.name.toLowerCase().includes(needle)
  )
})
const pick = (id: string) => {
  emit('pick', id)
  open.value = false
}
</script>

<template>
  <Combobox
    v-model:open="open"
    :model-value="props.selectedId ?? undefined"
    ignore-filter
    :reset-search-term-on-blur="false"
    :reset-search-term-on-select="false"
    @update:model-value="(value) => pick(value as string)"
  >
    <ComboboxAnchor as-child class="w-auto min-w-0">
      <ComboboxTrigger as-child>
        <button
          type="button"
          class="flex h-10 min-w-0 cursor-pointer items-center gap-2 rounded-md border border-gray-warm-300 bg-base-white px-3 text-sm font-medium text-gray-warm-700 outline-hidden hover:bg-gray-warm-50 focus-visible:ring-3 focus-visible:ring-gray"
        >
          <Search class="size-4 shrink-0 text-gray-warm-400" />
          <span class="truncate">{{ t('views.deployment-videowall.viewer.pick') }}</span>
          <ChevronDown class="size-4 shrink-0 text-gray-warm-400" />
        </button>
      </ComboboxTrigger>
    </ComboboxAnchor>
    <ComboboxList inline align="start" class="w-96 p-0">
      <div class="flex items-center border-b border-gray-200 px-3.5 py-2.5">
        <Search class="mr-2 size-5 shrink-0 opacity-50" />
        <ComboboxInput
          v-model="search"
          auto-focus
          :placeholder="t('views.deployment-videowall.filter-placeholder')"
          class="h-auto border-0 p-0 text-md font-medium text-gray-warm-900 shadow-none placeholder:text-gray-warm-500 focus-visible:ring-0"
        />
      </div>
      <div class="max-h-96 overflow-y-auto p-1">
        <p v-if="pickable.length === 0" class="p-2.5 text-sm text-gray-warm-500">
          {{ t('views.deployment-videowall.viewer.not-found') }}
        </p>
        <ComboboxItem
          v-for="option in pickable"
          :key="option.id"
          :value="option.id"
          class="p-2 data-highlighted:cursor-pointer data-highlighted:bg-secondary-2-100"
        >
          <AvatarLabel
            :src="option.user_photo"
            :name="option.user_name"
            size="md"
            :class="AVATAR_LABEL_TRUNCATE"
          >
            <template #sub>
              <span class="flex min-w-0 items-center gap-1 text-gray-warm-600">
                <Icon name="monitor" size="xs" stroke-color="gray-warm-500" class="shrink-0" />
                <span class="truncate">{{ option.name }}</span>
              </span>
            </template>
          </AvatarLabel>
          <Check
            :class="cn('ml-auto', option.id === props.selectedId ? 'opacity-100' : 'opacity-0')"
          />
        </ComboboxItem>
      </div>
    </ComboboxList>
  </Combobox>
</template>
